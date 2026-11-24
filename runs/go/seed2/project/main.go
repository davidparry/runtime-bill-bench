package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"sync"
	"syscall"
	"time"
)

// Order represents the order entity stored in memory.
type Order struct {
	ID         string    `json:"id"`
	CustomerID string    `json:"customerId"`
	Items      []Item    `json:"items"`
	TotalCents int64     `json:"totalCents"`
	CreatedAt  time.Time `json:"createdAt"`
}

// Item represents a line item in an order.
type Item struct {
	SKU            string `json:"sku"`
	Quantity       int    `json:"quantity"`
	UnitPriceCents int    `json:"unitPriceCents"`
}

// CreateOrderRequest represents the incoming JSON payload for creating an order.
type CreateOrderRequest struct {
	CustomerID string `json:"customerId"`
	Items      []Item `json:"items"`
}

// ErrorResponse represents a JSON error response.
type ErrorResponse struct {
	Error string `json:"error"`
}

// InMemoryStore handles concurrent access to orders.
type InMemoryStore struct {
	mu     sync.RWMutex
	orders map[string]Order
}

func NewInMemoryStore() *InMemoryStore {
	return &InMemoryStore{
		orders: make(map[string]Order),
	}
}

func (s *InMemoryStore) Create(order Order) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.orders[order.ID] = order
}

func (s *InMemoryStore) Get(id string) (Order, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	order, ok := s.orders[id]
	return order, ok
}

func (s *InMemoryStore) Delete(id string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.orders, id)
}

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	store := NewInMemoryStore()

	// Define handlers
	healthHandler := func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
	}

	createOrderHandler := func(w http.ResponseWriter, r *http.Request) {
		handleCreateOrder(w, r, store)
	}

	getOrderHandler := func(w http.ResponseWriter, r *http.Request) {
		// Extract ID from path
		id := strings.TrimPrefix(r.URL.Path, "/orders/")
		handleGetOrder(w, r, id, store)
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/health", healthHandler)
	mux.HandleFunc("/orders", createOrderHandler)
	mux.HandleFunc("/orders/", getOrderHandler)

	// Wrap handlers with logging middleware
	var handler http.Handler = http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()

		// Create a response writer that captures status code
		wrappedWriter := &statusCapturingWriter{
			ResponseWriter: w,
			status:         http.StatusOK,
		}

		mux.ServeHTTP(wrappedWriter, r)

		duration := time.Since(start)

		logLine := map[string]interface{}{
			"method":     r.Method,
			"path":       r.URL.Path,
			"status":     wrappedWriter.status,
			"durationMs": duration.Milliseconds(),
		}

		jsonLog, err := json.Marshal(logLine)
		if err != nil {
			log.Printf("Failed to marshal log line: %v", err)
		} else {
			fmt.Println(string(jsonLog))
		}
	})

	server := &http.Server{
		Addr:    ":" + port,
		Handler: handler,
	}

	// Graceful shutdown
	go func() {
		sigChan := make(chan os.Signal, 1)
		signal.Notify(sigChan, syscall.SIGTERM, syscall.SIGINT)
		sig := <-sigChan
		log.Printf("Received signal %v, shutting down...", sig)

		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()

		if err := server.Shutdown(ctx); err != nil {
			log.Printf("HTTP server shutdown error: %v", err)
		}
	}()

	log.Printf("Orders service starting on port %s", port)
	if err := server.ListenAndServe(); err != http.ErrServerClosed {
		log.Fatalf("HTTP server error: %v", err)
	}

	log.Println("Orders service stopped.")
}

// statusCapturingWriter wraps http.ResponseWriter to capture the status code.
type statusCapturingWriter struct {
	http.ResponseWriter
	status int
}

func (w *statusCapturingWriter) WriteHeader(code int) {
	w.status = code
	w.ResponseWriter.WriteHeader(code)
}

func handleCreateOrder(w http.ResponseWriter, r *http.Request, store *InMemoryStore) {
	var req CreateOrderRequest
	
	// Decode JSON, ignoring unknown fields as per specification
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields() // This will cause an error if unknown fields are present

	if err := decoder.Decode(&req); err != nil {
		// If we hit an unknown field error, we should still return 400 but potentially
		// different message or just standard validation. The prompt says "Ignore unknown fields".
		// However, json.Decoder doesn't have a direct "ignore unknown" option that doesn't error.
		// We can use a map first to discard unknown fields, then unmarshal into struct.
		
		// Re-decode using map to ignore unknown fields
		var rawReq map[string]json.RawMessage
		if err := json.NewDecoder(r.Body).Decode(&rawReq); err != nil {
			writeError(w, http.StatusBadRequest, fmt.Sprintf("Invalid JSON: %v", err))
			return
		}

		// Marshal back to JSON to re-decode into struct, effectively ignoring unknown fields
		jsonData, err := json.Marshal(rawReq)
		if err != nil {
			writeError(w, http.StatusBadRequest, fmt.Sprintf("Error processing request: %v", err))
			return
		}

		if err := json.Unmarshal(jsonData, &req); err != nil {
			writeError(w, http.StatusBadRequest, fmt.Sprintf("Invalid JSON: %v", err))
			return
		}
	}

	if err := validateCreateOrder(req); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	// Calculate total
	var totalCents int64
	for _, item := range req.Items {
		totalCents += int64(item.Quantity) * int64(item.UnitPriceCents)
	}

	// Generate UUID
	id := generateUUID()

	order := Order{
		ID:         id,
		CustomerID: req.CustomerID,
		Items:      req.Items,
		TotalCents: totalCents,
		CreatedAt:  time.Now().UTC(),
	}

	store.Create(order)

	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Location", fmt.Sprintf("/orders/%s", id))
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(order)
}

func handleGetOrder(w http.ResponseWriter, r *http.Request, id string, store *InMemoryStore) {
	order, found := store.Get(id)
	if !found {
		writeError(w, http.StatusNotFound, fmt.Sprintf("Order %s not found", id))
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(order)
}

func validateCreateOrder(req CreateOrderRequest) error {
	if req.CustomerID == "" {
		return fmt.Errorf("customerId is required")
	}
	if len(req.CustomerID) < 1 || len(req.CustomerID) > 64 {
		return fmt.Errorf("customerId must be between 1 and 64 characters")
	}

	if len(req.Items) < 1 || len(req.Items) > 50 {
		return fmt.Errorf("items must contain between 1 and 50 entries")
	}

	for i, item := range req.Items {
		if item.SKU == "" {
			return fmt.Errorf("items[%d].sku is required", i)
		}
		if len(item.SKU) < 1 || len(item.SKU) > 32 {
			return fmt.Errorf("items[%d].sku must be between 1 and 32 characters", i)
		}
		if item.Quantity < 1 || item.Quantity > 100 {
			return fmt.Errorf("items[%d].quantity must be between 1 and 100", i)
		}
		if item.UnitPriceCents < 1 || item.UnitPriceCents > 1000000 {
			return fmt.Errorf("items[%d].unitPriceCents must be between 1 and 1000000", i)
		}
	}

	return nil
}

func writeError(w http.ResponseWriter, status int, message string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(ErrorResponse{Error: message})
}
