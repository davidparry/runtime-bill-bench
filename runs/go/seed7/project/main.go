package main

import (
	"context"
	"crypto/rand"
	"encoding/json"
	"fmt"
	"io"
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

// Order represents the internal order structure.
type Order struct {
	ID         string      `json:"id"`
	CustomerID string      `json:"customerId"`
	Items      []OrderItem `json:"items"`
	TotalCents int64       `json:"totalCents"`
	CreatedAt  time.Time   `json:"createdAt"`
}

// OrderItem represents an item within an order.
type OrderItem struct {
	SKU            string `json:"sku"`
	Quantity       int    `json:"quantity"`
	UnitPriceCents int    `json:"unitPriceCents"`
}

// CreateOrderRequest represents the incoming JSON for POST /orders.
type CreateOrderRequest struct {
	CustomerID string       `json:"customerId"`
	Items      []OrderItem  `json:"items"`
}

// ErrorResponse represents the error JSON body.
type ErrorResponse struct {
	Error string `json:"error"`
}

// OrderStore manages in-memory orders with concurrency safety.
type OrderStore struct {
	mu     sync.RWMutex
	orders map[string]Order
}

func NewOrderStore() *OrderStore {
	return &OrderStore{
		orders: make(map[string]Order),
	}
}

func (s *OrderStore) Set(order Order) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.orders[order.ID] = order
}

func (s *OrderStore) Get(id string) (Order, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	order, ok := s.orders[id]
	return order, ok
}

// generateUUID generates a random UUID v4.
func generateUUID() string {
	b := make([]byte, 16)
	rand.Read(b)
	b[6] = (b[6] & 0x0f) | 0x40 // Version 4
	b[8] = (b[8] & 0x3f) | 0x80 // Variant 1
	return fmt.Sprintf("%08x-%04x-%04x-%04x-%012x",
		b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}

// validateString checks if s is a non-empty string with length between min and max.
func validateString(s string, min, max int, name string) error {
	if s == "" {
		return fmt.Errorf("%s is required", name)
	}
	l := utf8.RuneCountInString(s)
	if l < min || l > max {
		return fmt.Errorf("%s must be between %d and %d characters", name, min, max)
	}
	return nil
}

// validateOrderRequest validates the incoming request body.
func validateOrderRequest(body []byte) (*CreateOrderRequest, error) {
	// Check for valid JSON first.
	var raw map[string]json.RawMessage
	if err := json.Unmarshal(body, &raw); err != nil {
		return nil, fmt.Errorf("invalid JSON: %v", err)
	}

	// Check for required fields existence.
	if _, hasCustomerID := raw["customerId"]; !hasCustomerID {
		return nil, fmt.Errorf("customerId is required")
	}
	if _, hasItems := raw["items"]; !hasItems {
		return nil, fmt.Errorf("items is required")
	}

	// Decode into struct to validate types and ranges.
	var req CreateOrderRequest
	if err := json.Unmarshal(body, &req); err != nil {
		return nil, fmt.Errorf("invalid request body: %v", err)
	}

	// Validate customerId
	if err := validateString(req.CustomerID, 1, 64, "customerId"); err != nil {
		return nil, err
	}

	// Validate items
	if len(req.Items) < 1 || len(req.Items) > 50 {
		return nil, fmt.Errorf("items must contain between 1 and 50 entries")
	}

	for i, item := range req.Items {
		// Validate SKU
		if err := validateString(item.SKU, 1, 32, fmt.Sprintf("items[%d].sku", i)); err != nil {
			return nil, err
		}

		// Validate Quantity
		if item.Quantity < 1 || item.Quantity > 100 {
			return nil, fmt.Errorf("items[%d].quantity must be between 1 and 100", i)
		}

		// Validate UnitPriceCents
		if item.UnitPriceCents < 1 || item.UnitPriceCents > 1000000 {
			return nil, fmt.Errorf("items[%d].unitPriceCents must be between 1 and 1000000", i)
		}
	}

	return &req, nil
}

func calculateTotal(items []OrderItem) int64 {
	var total int64
	for _, item := range items {
		total += int64(item.Quantity) * int64(item.UnitPriceCents)
	}
	return total
}

func writeJSON(w http.ResponseWriter, status int, data interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(data)
}

func logRequest(r *http.Request, status int, durationMs int64) {
	logEntry := map[string]interface{}{
		"method":     r.Method,
		"path":       r.URL.Path,
		"status":     status,
		"durationMs": durationMs,
	}
	b, err := json.Marshal(logEntry)
	if err != nil {
		log.Printf("Error marshaling log entry: %v", err)
		return
	}
	fmt.Println(string(b))
}

func main() {
	store := NewOrderStore()
	
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	mux := http.NewServeMux()

	// POST /orders
	mux.HandleFunc("POST /orders", func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		
		body, err := io.ReadAll(r.Body)
		if err != nil {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "failed to read body"})
			logRequest(r, http.StatusBadRequest, time.Since(start).Milliseconds())
			return
		}
		defer r.Body.Close()

		req, err := validateOrderRequest(body)
		if err != nil {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: err.Error()})
			logRequest(r, http.StatusBadRequest, time.Since(start).Milliseconds())
			return
		}

		id := generateUUID()
		now := time.Now().UTC()
		
		order := Order{
			ID:         id,
			CustomerID: req.CustomerID,
			Items:      req.Items,
			TotalCents: calculateTotal(req.Items),
			CreatedAt:  now,
		}

		store.Set(order)

		w.Header().Set("Location", fmt.Sprintf("/orders/%s", id))
		writeJSON(w, http.StatusCreated, order)
		logRequest(r, http.StatusCreated, time.Since(start).Milliseconds())
	})

	// GET /orders/{id}
	mux.HandleFunc("GET /orders/{id}", func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()

		path := strings.TrimPrefix(r.URL.Path, "/")
		// Path is /orders/{id}
		parts := strings.Split(path, "/")
		if len(parts) != 2 {
			writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "not found"})
			logRequest(r, http.StatusNotFound, time.Since(start).Milliseconds())
			return
		}
		id := parts[1]

		order, found := store.Get(id)
		if !found {
			writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "order not found"})
			logRequest(r, http.StatusNotFound, time.Since(start).Milliseconds())
			return
		}

		writeJSON(w, http.StatusOK, order)
		logRequest(r, http.StatusOK, time.Since(start).Milliseconds())
	})

	// GET /health
	mux.HandleFunc("GET /health", func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
		logRequest(r, http.StatusOK, time.Since(start).Milliseconds())
	})

	server := &http.Server{
		Addr:    ":" + port,
		Handler: mux,
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

	log.Printf("Orders service starting on port %s", port)
	if err := server.ListenAndServe(); err != http.ErrServerClosed {
		log.Fatalf("Server error: %v", err)
	}
	log.Println("Server exited")
}
