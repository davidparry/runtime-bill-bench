package main

import (
	"context"
	"crypto/rand"
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
	"unicode/utf8"
)

// Order represents the core business entity
type Order struct {
	ID         string    `json:"id"`
	CustomerID string    `json:"customerId"`
	Items      []Item    `json:"items"`
	TotalCents int64     `json:"totalCents"`
	CreatedAt  time.Time `json:"createdAt"`
}

// Item represents a line item in an order
type Item struct {
	SKU            string `json:"sku"`
	Quantity       int    `json:"quantity"`
	UnitPriceCents int    `json:"unitPriceCents"`
}

// Store holds orders in memory with concurrency safety
type Store struct {
	mu     sync.RWMutex
	orders map[string]Order
}

// NewStore creates a new in-memory store
func NewStore() *Store {
	return &Store{
		orders: make(map[string]Order),
	}
}

// CreateOrder adds an order to the store
func (s *Store) CreateOrder(order Order) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.orders[order.ID] = order
}

// GetOrder retrieves an order by ID
func (s *Store) GetOrder(id string) (Order, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	order, ok := s.orders[id]
	return order, ok
}

// generateUUID creates a version 4 UUID
func generateUUID() string {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		panic(err)
	}
	// Set version to 4 (0100)
	b[6] = (b[6] & 0x0f) | 0x40
	// Set variant to 10 (10xxxxxx)
	b[8] = (b[8] & 0x3f) | 0x80

	return fmt.Sprintf("%08x-%04x-%04x-%04x-%012x",
		b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}

// validateOrderInput checks the request body against business rules
func validateOrderInput(customerID string, items []Item) error {
	// Validate customerId
	if len(customerID) < 1 || len(customerID) > 64 {
		return fmt.Errorf("customerId must be between 1 and 64 characters")
	}
	if !utf8.ValidString(customerID) {
		return fmt.Errorf("customerId must be valid UTF-8")
	}

	// Validate items
	if len(items) < 1 || len(items) > 50 {
		return fmt.Errorf("items must be between 1 and 50 entries")
	}

	for i, item := range items {
		// Validate SKU
		if len(item.SKU) < 1 || len(item.SKU) > 32 {
			return fmt.Errorf("item[%d].sku must be between 1 and 32 characters", i)
		}
		if !utf8.ValidString(item.SKU) {
			return fmt.Errorf("item[%d].sku must be valid UTF-8", i)
		}

		// Validate Quantity
		if item.Quantity < 1 || item.Quantity > 100 {
			return fmt.Errorf("item[%d].quantity must be between 1 and 100", i)
		}

		// Validate UnitPriceCents
		if item.UnitPriceCents < 1 || item.UnitPriceCents > 1000000 {
			return fmt.Errorf("item[%d].unitPriceCents must be between 1 and 1000000", i)
		}
	}

	return nil
}

// handleCreateOrder handles POST /orders
func handleCreateOrder(store *Store) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "Method not allowed"})
			return
		}

		// Decode body
		var rawRequest map[string]json.RawMessage
		if err := json.NewDecoder(r.Body).Decode(&rawRequest); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid JSON body"})
			return
		}

		// Extract customerId
		customerIDBytes, ok := rawRequest["customerId"]
		if !ok {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Missing required field: customerId"})
			return
		}
		var customerID string
		if err := json.Unmarshal(customerIDBytes, &customerID); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid customerId format"})
			return
		}

		// Extract items
		itemsBytes, ok := rawRequest["items"]
		if !ok {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Missing required field: items"})
			return
		}
		var items []Item
		if err := json.Unmarshal(itemsBytes, &items); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid items format"})
			return
		}

		// Validate input
		if err := validateOrderInput(customerID, items); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": err.Error()})
			return
		}

		// Calculate total
		var totalCents int64
		for _, item := range items {
			totalCents += int64(item.Quantity) * int64(item.UnitPriceCents)
		}

		// Create order
		orderID := generateUUID()
		now := time.Now().UTC()

		order := Order{
			ID:         orderID,
			CustomerID: customerID,
			Items:      items,
			TotalCents: totalCents,
			CreatedAt:  now,
		}

		store.CreateOrder(order)

		// Respond
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("Location", fmt.Sprintf("/orders/%s", orderID))
		w.WriteHeader(http.StatusCreated)
		json.NewEncoder(w).Encode(order)
	}
}

// handleGetOrder handles GET /orders/{id}
func handleGetOrder(store *Store) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "Method not allowed"})
			return
		}

		// Extract ID from path
		id := strings.TrimPrefix(r.URL.Path, "/orders/")
		if id == "" {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Order ID is required"})
			return
		}

		order, found := store.GetOrder(id)
		if !found {
			writeJSON(w, http.StatusNotFound, map[string]string{"error": "Order not found"})
			return
		}

		writeJSON(w, http.StatusOK, order)
	}
}

// handleHealth handles GET /health
func handleHealth() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "Method not allowed"})
			return
		}
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	}
}

// writeJSON writes a JSON response
func writeJSON(w http.ResponseWriter, status int, v interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(v)
}

// loggingMiddleware logs each request
func loggingMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()

		// Wrap response writer to capture status code
		wrapped := &statusResponseWriter{ResponseWriter: w, status: http.StatusOK}

		next.ServeHTTP(wrapped, r)

		duration := time.Since(start)

		logData := map[string]interface{}{
			"method":     r.Method,
			"path":       r.URL.Path,
			"status":     wrapped.status,
			"durationMs": float64(duration.Microseconds()) / 1000.0,
		}

		json.NewEncoder(os.Stdout).Encode(logData)
	})
}

// statusResponseWriter wraps http.ResponseWriter to capture status code
type statusResponseWriter struct {
	http.ResponseWriter
	status int
}

func (w *statusResponseWriter) WriteHeader(status int) {
	w.status = status
	w.ResponseWriter.WriteHeader(status)
}

func main() {
	store := NewStore()

	mux := http.NewServeMux()
	mux.HandleFunc("/orders", handleCreateOrder(store))
	mux.HandleFunc("/orders/", handleGetOrder(store))
	mux.HandleFunc("/health", handleHealth())

	handler := loggingMiddleware(mux)

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	server := &http.Server{
		Addr:         ":" + port,
		Handler:      handler,
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 10 * time.Second,
	}

	// Graceful shutdown
	go func() {
		sigChan := make(chan os.Signal, 1)
		signal.Notify(sigChan, syscall.SIGTERM)
		<-sigChan

		log.Println("Shutting down server...")

		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()

		if err := server.Shutdown(ctx); err != nil {
			log.Printf("Server shutdown error: %v", err)
		}
	}()

	log.Printf("Starting server on port %s", port)
	if err := server.ListenAndServe(); err != http.ErrServerClosed {
		log.Fatalf("Server error: %v", err)
	}

	log.Println("Server exited")
}
