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

// Order represents the core data structure.
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

// CreateOrderRequest represents the incoming JSON for creating an order.
type CreateOrderRequest struct {
	CustomerID string       `json:"customerId"`
	Items      []OrderItem `json:"items"`
}

// ErrorResponse represents a JSON error response.
type ErrorResponse struct {
	Error string `json:"error"`
}

// OrderStore handles concurrent access to orders in memory.
type OrderStore struct {
	mu      sync.RWMutex
	orders  map[string]Order
	counter int64
}

func NewOrderStore() *OrderStore {
	return &OrderStore{
		orders: make(map[string]Order),
	}
}

func (s *OrderStore) CreateOrder(o Order) (Order, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if _, exists := s.orders[o.ID]; exists {
		return Order{}, fmt.Errorf("order with id %s already exists", o.ID)
	}

	s.orders[o.ID] = o
	return o, nil
}

func (s *OrderStore) GetOrder(id string) (Order, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	o, exists := s.orders[id]
	return o, exists
}

// generateUUID creates a valid UUID v4 string.
func generateUUID() string {
	uuid := make([]byte, 16)
	_, err := rand.Read(uuid)
	if err != nil {
		// Fallback to crypto/rand or panic if rand fails (unlikely)
		panic(err)
	}

	// Set version 4
	uuid[6] = (uuid[6] & 0x0f) | 0x40

	// Set variant 1 (RFC 4122)
	uuid[8] = (uuid[8] & 0x3f) | 0x80

	return fmt.Sprintf("%x-%x-%x-%x-%x",
		uuid[0:4], uuid[4:6], uuid[6:8], uuid[8:10], uuid[10:16])
}

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	store := NewOrderStore()
	handler := NewOrderHandler(store)

	mux := http.NewServeMux()
	mux.HandleFunc("/orders", handler.HandleOrders)
	mux.HandleFunc("/orders/", handler.HandleOrderByID)
	mux.HandleFunc("/health", handler.HandleHealth)

	// Wrap handler to add logging and error handling
	var server *http.Server
	server = &http.Server{
		Addr:         ":" + port,
		Handler:      loggingMiddleware(mux),
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 10 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	// Graceful shutdown
	go func() {
		sigCh := make(chan os.Signal, 1)
		signal.Notify(sigCh, syscall.SIGTERM, syscall.SIGINT)
		sig := <-sigCh
		log.Printf("Received signal %v, shutting down...", sig)

		// Create a deadline for shutdown (10 seconds)
		shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer shutdownCancel()

		if err := server.Shutdown(shutdownCtx); err != nil {
			log.Printf("HTTP server Shutdown: %v", err)
		}
	}()

	log.Printf("Starting server on port %s", port)
	if err := server.ListenAndServe(); err != http.ErrServerClosed {
		log.Fatalf("HTTP server error: %v", err)
	}
	
	log.Println("Server stopped gracefully.")
}

// loggingMiddleware logs every request in JSON format.
func loggingMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		
		// Wrap the ResponseWriter to capture status code
		wrapped := &statusResponseWriter{ResponseWriter: w, statusCode: http.StatusOK}
		
		next.ServeHTTP(wrapped, r)
		
		duration := time.Since(start).Milliseconds()
		
		logLine := map[string]interface{}{
			"method":    r.Method,
			"path":      r.URL.Path,
			"status":    wrapped.statusCode,
			"durationMs": duration,
			"timestamp": time.Now().UTC().Format(time.RFC3339),
		}
		
		// Encode log line
		logBytes, err := json.Marshal(logLine)
		if err != nil {
			log.Printf("Failed to marshal log: %v", err)
		} else {
			fmt.Fprintln(os.Stdout, string(logBytes))
		}
	})
}

// statusResponseWriter wraps http.ResponseWriter to capture the status code.
type statusResponseWriter struct {
	http.ResponseWriter
	statusCode int
}

func (w *statusResponseWriter) WriteHeader(code int) {
	w.statusCode = code
	w.ResponseWriter.WriteHeader(code)
}

// OrderHandler handles HTTP requests for orders.
type OrderHandler struct {
	store *OrderStore
}

func NewOrderHandler(store *OrderStore) *OrderHandler {
	return &OrderHandler{store: store}
}

func (h *OrderHandler) HandleHealth(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (h *OrderHandler) HandleOrders(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodPost:
		h.createOrder(w, r)
	default:
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
	}
}

func (h *OrderHandler) HandleOrderByID(w http.ResponseWriter, r *http.Request) {
	// Extract ID from path /orders/{id}
	path := r.URL.Path
	if !strings.HasPrefix(path, "/orders/") {
		writeError(w, http.StatusNotFound, "not found")
		return
	}
	id := strings.TrimPrefix(path, "/orders/")
	
	if id == "" {
		writeError(w, http.StatusBadRequest, "invalid order ID")
		return
	}

	if r.Method == http.MethodGet {
		h.getOrder(w, r, id)
	} else {
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
	}
}

func (h *OrderHandler) createOrder(w http.ResponseWriter, r *http.Request) {
	var req CreateOrderRequest
	decoder := json.NewDecoder(r.Body)
	// Do not use DisallowUnknownFields. We want to ignore them.
	if err := decoder.Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, fmt.Sprintf("invalid JSON: %v", err))
		return
	}
	defer r.Body.Close()

	// Validate CustomerID
	if err := validateCustomerID(req.CustomerID); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	// Validate Items
	if err := validateItems(req.Items); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	// Calculate Total
	totalCents := int64(0)
	for _, item := range req.Items {
		totalCents += int64(item.Quantity) * int64(item.UnitPriceCents)
	}

	// Create Order Object
	order := Order{
		ID:         generateUUID(),
		CustomerID: req.CustomerID,
		Items:      req.Items,
		TotalCents: totalCents,
		CreatedAt:  time.Now().UTC(),
	}

	// Store Order
	storedOrder, err := h.store.CreateOrder(order)
	if err != nil {
		// Should not happen unless ID collision, which is extremely rare with UUIDs
		writeError(w, http.StatusInternalServerError, "failed to store order")
		return
	}

	// Respond
	w.Header().Set("Location", fmt.Sprintf("/orders/%s", storedOrder.ID))
	writeJSON(w, http.StatusCreated, storedOrder)
}

func (h *OrderHandler) getOrder(w http.ResponseWriter, r *http.Request, id string) {
	order, exists := h.store.GetOrder(id)
	if !exists {
		writeError(w, http.StatusNotFound, fmt.Sprintf("order %s not found", id))
		return
	}
	writeJSON(w, http.StatusOK, order)
}

// Validation Helpers

func validateCustomerID(id string) error {
	if id == "" {
		return fmt.Errorf("customerId is required")
	}
	n := utf8.RuneCountInString(id)
	if n < 1 || n > 64 {
		return fmt.Errorf("customerId must be between 1 and 64 characters")
	}
	return nil
}

func validateItems(items []OrderItem) error {
	if items == nil {
		return fmt.Errorf("items is required")
	}
	if len(items) < 1 || len(items) > 50 {
		return fmt.Errorf("items must contain between 1 and 50 entries")
	}

	for i, item := range items {
		if err := validateItem(item, i); err != nil {
			return err
		}
	}
	return nil
}

func validateItem(item OrderItem, index int) error {
	sku := item.SKU
	if sku == "" {
		return fmt.Errorf("items[%d].sku is required", index)
	}
	n := utf8.RuneCountInString(sku)
	if n < 1 || n > 32 {
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

// JSON Helpers

func writeJSON(w http.ResponseWriter, status int, data interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(data)
}

func writeError(w http.ResponseWriter, status int, message string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(ErrorResponse{Error: message})
}
