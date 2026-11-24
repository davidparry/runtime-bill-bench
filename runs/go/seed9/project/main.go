package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"math/rand"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"sync"
	"syscall"
	"time"
)

// Order represents an order in the system.
type Order struct {
	ID         string      `json:"id"`
	CustomerID string      `json:"customerId"`
	Items      []OrderItem `json:"items"`
	TotalCents int64       `json:"totalCents"`
	CreatedAt  time.Time   `json:"createdAt"`
}

// OrderItem represents an item in an order.
type OrderItem struct {
	SKU            string `json:"sku"`
	Quantity       int    `json:"quantity"`
	UnitPriceCents int    `json:"unitPriceCents"`
}

// CreateOrderRequest represents the request body for creating an order.
type CreateOrderRequest struct {
	CustomerID string       `json:"customerId"`
	Items      []OrderItem  `json:"items"`
}

// ErrorResponse represents an error response.
type ErrorResponse struct {
	Error string `json:"error"`
}

// OrderStore manages orders in memory.
type OrderStore struct {
	mu      sync.RWMutex
	orders  map[string]Order
	counter int
}

func NewOrderStore() *OrderStore {
	return &OrderStore{
		orders: make(map[string]Order),
	}
}

func (s *OrderStore) CreateOrder(customerID string, items []OrderItem) (Order, error) {
	// Validate inputs
	if err := validateCustomerID(customerID); err != nil {
		return Order{}, err
	}
	if err := validateItems(items); err != nil {
		return Order{}, err
	}

	// Calculate total
	var totalCents int64
	for _, item := range items {
		totalCents += int64(item.Quantity) * int64(item.UnitPriceCents)
	}

	// Check total limit
	if totalCents > 5000000000 {
		return Order{}, fmt.Errorf("total price exceeds maximum allowed")
	}

	// Generate ID
	orderID := generateUUID()

	order := Order{
		ID:         orderID,
		CustomerID: customerID,
		Items:      items,
		TotalCents: totalCents,
		CreatedAt:  time.Now().UTC(),
	}

	s.mu.Lock()
	s.orders[orderID] = order
	s.mu.Unlock()

	return order, nil
}

func (s *OrderStore) GetOrder(id string) (Order, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	order, ok := s.orders[id]
	return order, ok
}

// validateCustomerID checks if the customer ID is valid.
func validateCustomerID(customerID string) error {
	if customerID == "" {
		return fmt.Errorf("customerId is required")
	}
	if len(customerID) < 1 || len(customerID) > 64 {
		return fmt.Errorf("customerId must be between 1 and 64 characters")
	}
	return nil
}

// validateItems checks if the items array is valid.
func validateItems(items []OrderItem) error {
	if len(items) == 0 {
		return fmt.Errorf("items is required")
	}
	if len(items) > 50 {
		return fmt.Errorf("items must have between 1 and 50 entries")
	}

	for i, item := range items {
		if err := validateItem(item, i); err != nil {
			return err
		}
	}
	return nil
}

// validateItem checks if a single item is valid.
func validateItem(item OrderItem, index int) error {
	sku := item.SKU
	if sku == "" {
		return fmt.Errorf("items[%d].sku is required", index)
	}
	if len(sku) < 1 || len(sku) > 32 {
		return fmt.Errorf("items[%d].sku must be between 1 and 32 characters", index)
	}

	if item.Quantity < 1 || item.Quantity > 100 {
		return fmt.Errorf("items[%d].quantity must be between 1 and 100", index)
	}

	if item.UnitPriceCents < 1 || item.UnitPriceCents > 1000000 {
		return fmt.Errorf("items[%d].unitPriceCents must be between 1 and 1000000", index)
	}

	return nil
}

// generateUUID generates a UUID v4 string.
func generateUUID() string {
	// Simple UUID v4 generator
	uuid := make([]byte, 16)
	rand.Read(uuid)
	uuid[6] = (uuid[6] & 0x0f) | 0x40 // Version 4
	uuid[8] = (uuid[8] & 0x3f) | 0x80 // Variant 1
	return fmt.Sprintf("%x-%x-%x-%x-%x", uuid[0:4], uuid[4:6], uuid[6:8], uuid[8:10], uuid[10:16])
}

// OrderHandler handles HTTP requests for orders.
type OrderHandler struct {
	store *OrderStore
}

func NewOrderHandler(store *OrderStore) *OrderHandler {
	return &OrderHandler{store: store}
}

// handleCreateOrder handles POST /orders
func (h *OrderHandler) handleCreateOrder(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, "Method not allowed")
		return
	}

	// Parse request body
	var req CreateOrderRequest
	
	// json.Unmarshal ignores unknown fields by default, which satisfies the requirement.
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, fmt.Sprintf("Invalid JSON: %v", err))
		return
	}

	// Validate
	if err := validateCustomerID(req.CustomerID); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	if err := validateItems(req.Items); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	// Create order
	order, err := h.store.CreateOrder(req.CustomerID, req.Items)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	// Respond
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Location", fmt.Sprintf("/orders/%s", order.ID))
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(order)
}

// handleGetOrder handles GET /orders/{id}
func (h *OrderHandler) handleGetOrder(w http.ResponseWriter, r *http.Request, id string) {
	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, "Method not allowed")
		return
	}

	order, found := h.store.GetOrder(id)
	if !found {
		writeError(w, http.StatusNotFound, fmt.Sprintf("Order %s not found", id))
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(order)
}

// handleHealth handles GET /health
func (h *OrderHandler) handleHealth(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, "Method not allowed")
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
}

// writeError writes a JSON error response.
func writeError(w http.ResponseWriter, status int, message string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(ErrorResponse{Error: message})
}

// loggingMiddleware logs each request.
func loggingMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		
		// Wrap the ResponseWriter to capture status code
		wrappedWriter := &statusCodeResponseWriter{ResponseWriter: w, statusCode: http.StatusOK}
		
		next.ServeHTTP(wrappedWriter, r)
		
		duration := time.Since(start).Milliseconds()
		
		logEntry := map[string]interface{}{
			"method":    r.Method,
			"path":      r.URL.Path,
			"status":    wrappedWriter.statusCode,
			"durationMs": duration,
		}
		
		logJSON(logEntry)
	})
}

// statusCodeResponseWriter wraps http.ResponseWriter to capture status code.
type statusCodeResponseWriter struct {
	http.ResponseWriter
	statusCode int
}

func (w *statusCodeResponseWriter) WriteHeader(statusCode int) {
	w.statusCode = statusCode
	w.ResponseWriter.WriteHeader(statusCode)
}

// logJSON logs a JSON line to stdout.
func logJSON(entry map[string]interface{}) {
	data, err := json.Marshal(entry)
	if err != nil {
		log.Printf("Failed to marshal log entry: %v", err)
		return
	}
	fmt.Println(string(data))
}

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	store := NewOrderStore()
	handler := NewOrderHandler(store)

	mux := http.NewServeMux()
	
	// Register routes
	mux.HandleFunc("/orders", handler.handleCreateOrder)
	mux.HandleFunc("/orders/", func(w http.ResponseWriter, r *http.Request) {
		// Extract ID from path
		id := strings.TrimPrefix(r.URL.Path, "/orders/")
		if id == "" {
			writeError(w, http.StatusBadRequest, "Order ID is required")
			return
		}
		handler.handleGetOrder(w, r, id)
	})
	mux.HandleFunc("/health", handler.handleHealth)

	// Apply logging middleware
	server := &http.Server{
		Addr:    ":" + port,
		Handler: loggingMiddleware(mux),
	}

	// Graceful shutdown
	go func() {
		sigChan := make(chan os.Signal, 1)
		signal.Notify(sigChan, syscall.SIGTERM)
		<-sigChan
		
		log.Println("Shutting down gracefully...")
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		
		if err := server.Shutdown(ctx); err != nil {
			log.Printf("Server shutdown error: %v", err)
		}
	}()

	log.Printf("Server starting on port %s", port)
	if err := server.ListenAndServe(); err != http.ErrServerClosed {
		log.Fatalf("Server error: %v", err)
	}
	
	log.Println("Server stopped")
}
