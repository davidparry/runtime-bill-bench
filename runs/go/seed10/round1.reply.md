FILE: go.mod
```go
module orders

go 1.23
```

FILE: main.go
```go
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
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"
	"unicode/utf8"
)

// Order represents the core data structure.
type Order struct {
	ID         string    `json:"id"`
	CustomerID string    `json:"customerId"`
	Items      []OrderItem `json:"items"`
	TotalCents int64     `json:"totalCents"`
	CreatedAt  time.Time `json:"createdAt"`
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

// generateID creates a simple random UUID v4-like string.
// Since we cannot import external libraries, we generate a random hex string.
// Format: xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx
func generateID() string {
	const chars = "0123456789abcdef"
	b := make([]byte, 36)
	for i := range b {
		b[i] = chars[rand.Intn(len(chars))]
	}
	// Set version (4) and variant bits
	b[14] = '4'
	b[19] = chars[(rand.Intn(4)+8)] // 8, 9, a, or b
	return string(b)
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
	ctx, cancel := context.WithCancel(context.Background())
	go func() {
		sigCh := make(chan os.Signal, 1)
		signal.Notify(sigCh, syscall.SIGTERM, syscall.SIGINT)
		sig := <-sigCh
		log.Printf("Received signal %v, shutting down...", sig)
		cancel()

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
	decoder.DisallowUnknownFields() // Strictly ignore unknown fields by returning error
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
		ID:         generateID(),
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
```

FILE: main_test.go
```go
package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

// TestValidationRules tests the validation logic for the CreateOrderRequest.
func TestValidationRules(t *testing.T) {
	store := NewOrderStore()
	handler := NewOrderHandler(store)

	tests := []struct {
		name       string
		body       interface{}
		wantStatus int
	}{
		{
			name:       "valid order",
			body:       CreateOrderRequest{CustomerID: "c-1", Items: []OrderItem{{SKU: "A-1", Quantity: 2, UnitPriceCents: 1250}}},
			wantStatus: http.StatusCreated,
		},
		{
			name:       "missing customerId",
			body:       CreateOrderRequest{Items: []OrderItem{{SKU: "A-1", Quantity: 2, UnitPriceCents: 1250}}},
			wantStatus: http.StatusBadRequest,
		},
		{
			name:       "customerId too long",
			body:       CreateOrderRequest{CustomerID: string(make([]byte, 65)), Items: []OrderItem{{SKU: "A-1", Quantity: 2, UnitPriceCents: 1250}}},
			wantStatus: http.StatusBadRequest,
		},
		{
			name:       "empty items array",
			body:       CreateOrderRequest{CustomerID: "c-1", Items: []OrderItem{}},
			wantStatus: http.StatusBadRequest,
		},
		{
			name:       "too many items",
			body:       CreateOrderRequest{CustomerID: "c-1", Items: make([]OrderItem, 51)},
			wantStatus: http.StatusBadRequest,
		},
		{
			name:       "invalid quantity (0)",
			body:       CreateOrderRequest{CustomerID: "c-1", Items: []OrderItem{{SKU: "A-1", Quantity: 0, UnitPriceCents: 1250}}},
			wantStatus: http.StatusBadRequest,
		},
		{
			name:       "invalid quantity (101)",
			body:       CreateOrderRequest{CustomerID: "c-1", Items: []OrderItem{{SKU: "A-1", Quantity: 101, UnitPriceCents: 1250}}},
			wantStatus: http.StatusBadRequest,
		},
		{
			name:       "invalid unitPriceCents (0)",
			body:       CreateOrderRequest{CustomerID: "c-1", Items: []OrderItem{{SKU: "A-1", Quantity: 1, UnitPriceCents: 0}}},
			wantStatus: http.StatusBadRequest,
		},
		{
			name:       "invalid unitPriceCents (1000001)",
			body:       CreateOrderRequest{CustomerID: "c-1", Items: []OrderItem{{SKU: "A-1", Quantity: 1, UnitPriceCents: 1000001}}},
			wantStatus: http.StatusBadRequest,
		},
		{
			name:       "invalid sku length (0)",
			body:       CreateOrderRequest{CustomerID: "c-1", Items: []OrderItem{{SKU: "", Quantity: 1, UnitPriceCents: 100}}},
			wantStatus: http.StatusBadRequest,
		},
		{
			name:       "invalid sku length (33)",
			body:       CreateOrderRequest{CustomerID: "c-1", Items: []OrderItem{{SKU: string(make([]byte, 33)), Quantity: 1, UnitPriceCents: 100}}},
			wantStatus: http.StatusBadRequest,
		},
		{
			name:       "unknown fields ignored",
			body:       map[string]interface{}{"customerId": "c-1", "items": []map[string]interface{}{{"sku": "A-1", "quantity": 1, "unitPriceCents": 100, "extra": "field"}}, "extraRoot": "field"},
			wantStatus: http.StatusCreated,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			bodyBytes, err := json.Marshal(tt.body)
			if err != nil {
				t.Fatalf("failed to marshal test body: %v", err)
			}

			req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewReader(bodyBytes))
			req.Header.Set("Content-Type", "application/json")
			w := httptest.NewRecorder()

			handler.HandleOrders(w, req)

			if w.Code != tt.wantStatus {
				t.Errorf("got status %d, want %d. Body: %s", w.Code, tt.wantStatus, w.Body.String())
			}
		})
	}
}

// TestNotFound tests the 404 case for GET /orders/{id}.
func TestNotFound(t *testing.T) {
	store := NewOrderStore()
	handler := NewOrderHandler(store)

	req := httptest.NewRequest(http.MethodGet, "/orders/non-existent-id", nil)
	w := httptest.NewRecorder()

	handler.HandleOrderByID(w, req)

	if w.Code != http.StatusNotFound {
		t.Errorf("got status %d, want %d", w.Code, http.StatusNotFound)
	}

	var resp ErrorResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}
	if resp.Error == "" {
		t.Error("expected error message in response body")
	}
}

// TestHealth checks the health endpoint.
func TestHealth(t *testing.T) {
	store := NewOrderStore()
	handler := NewOrderHandler(store)

	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	w := httptest.NewRecorder()

	handler.HandleHealth(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("got status %d, want %d", w.Code, http.StatusOK)
	}

	var resp map[string]string
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}
	if resp["status"] != "ok" {
		t.Errorf("got status %s, want 'ok'", resp["status"])
	}
}
```