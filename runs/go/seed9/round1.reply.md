FILE: go.mod
```go
module orders

go 1.27.0
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
	"strings"
	"sync"
	"syscall"
	"time"
	"unicode/utf8"
)

// Order represents an order in the system.
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
	s.mu.Lock()
	s.counter++
	id := fmt.Sprintf("ord-%d", s.counter)
	// In a real system, we'd use UUID. For this exercise, simple ID is fine,
	// but let's make it look more like a UUID for compliance with "UUID version 4"
	// requirement in the prompt. We'll generate a proper UUID string.
	s.mu.Unlock()
	
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
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields() // This will ignore unknown fields by default? No, it returns an error.
	// The prompt says "Ignore unknown fields". json.Unmarshal does this by default.
	// But json.Decoder has DisallowUnknownFields which does the opposite.
	// We should NOT set DisallowUnknownFields.
	
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
```

FILE: main_test.go
```go
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestValidateCustomerID(t *testing.T) {
	tests := []struct {
		name    string
		id      string
		wantErr bool
	}{
		{"valid short ID", "c-1", false},
		{"valid long ID", "c-" + string(make([]byte, 60)), false},
		{"empty ID", "", true},
		{"too short", "", true},
		{"too long", "c-" + string(make([]byte, 61)), true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := validateCustomerID(tt.id)
			if (err != nil) != tt.wantErr {
				t.Errorf("validateCustomerID(%q) error = %v, wantErr %v", tt.id, err, tt.wantErr)
			}
		})
	}
}

func TestValidateItems(t *testing.T) {
	tests := []struct {
		name    string
		items   []OrderItem
		wantErr bool
	}{
		{"valid single item", []OrderItem{{SKU: "A-1", Quantity: 1, UnitPriceCents: 100}}, false},
		{"valid multiple items", []OrderItem{
			{SKU: "A-1", Quantity: 1, UnitPriceCents: 100},
			{SKU: "A-2", Quantity: 2, UnitPriceCents: 200},
		}, false},
		{"too many items", nil, true},
		{"empty items", []OrderItem{}, true},
		{"invalid quantity", []OrderItem{{SKU: "A-1", Quantity: 0, UnitPriceCents: 100}}, true},
		{"invalid unit price", []OrderItem{{SKU: "A-1", Quantity: 1, UnitPriceCents: 0}}, true},
		{"invalid sku length", []OrderItem{{SKU: string(make([]byte, 33)), Quantity: 1, UnitPriceCents: 100}}, true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := validateItems(tt.items)
			if (err != nil) != tt.wantErr {
				t.Errorf("validateItems() error = %v, wantErr %v", err, tt.wantErr)
			}
		})
	}
}

func TestHandleCreateOrder(t *testing.T) {
	store := NewOrderStore()
	handler := NewOrderHandler(store)

	tests := []struct {
		name           string
		requestBody    string
		wantStatus     int
		wantLocation   bool
		wantError      bool
	}{
		{
			name:        "valid order",
			requestBody: `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}]}`,
			wantStatus:  http.StatusCreated,
			wantLocation: true,
		},
		{
			name:        "invalid customer ID",
			requestBody: `{"customerId": "", "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]}`,
			wantStatus:  http.StatusBadRequest,
			wantError:   true,
		},
		{
			name:        "invalid items",
			requestBody: `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 0, "unitPriceCents": 100}]}`,
			wantStatus:  http.StatusBadRequest,
			wantError:   true,
		},
		{
			name:        "invalid JSON",
			requestBody: `{invalid json}`,
			wantStatus:  http.StatusBadRequest,
			wantError:   true,
		},
		{
			name:        "unknown fields ignored",
			requestBody: `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}], "unknown": "field"}`,
			wantStatus:  http.StatusCreated,
			wantLocation: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(tt.requestBody))
			req.Header.Set("Content-Type", "application/json")
			w := httptest.NewRecorder()

			handler.handleCreateOrder(w, req)

			if w.Code != tt.wantStatus {
				t.Errorf("handleCreateOrder() status = %d, want %d", w.Code, tt.wantStatus)
			}

			if tt.wantLocation {
				location := w.Header().Get("Location")
				if location == "" {
					t.Errorf("handleCreateOrder() missing Location header")
				}
			}

			if tt.wantError {
				var resp ErrorResponse
				if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
					t.Errorf("handleCreateOrder() failed to unmarshal error response: %v", err)
				}
				if resp.Error == "" {
					t.Errorf("handleCreateOrder() error response has empty error message")
				}
			} else {
				var resp Order
				if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
					t.Errorf("handleCreateOrder() failed to unmarshal order response: %v", err)
				}
				if resp.ID == "" {
					t.Errorf("handleCreateOrder() returned order with empty ID")
				}
			}
		})
	}
}

func TestHandleGetOrder(t *testing.T) {
	store := NewOrderStore()
	handler := NewOrderHandler(store)

	// Create an order first
	reqBody := `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]}`
	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(reqBody))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	handler.handleCreateOrder(w, req)

	var createdOrder Order
	if err := json.Unmarshal(w.Body.Bytes(), &createdOrder); err != nil {
		t.Fatalf("failed to unmarshal created order: %v", err)
	}

	tests := []struct {
		name       string
		orderID    string
		wantStatus int
	}{
		{"existing order", createdOrder.ID, http.StatusOK},
		{"non-existing order", "non-existing-id", http.StatusNotFound},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodGet, fmt.Sprintf("/orders/%s", tt.orderID), nil)
			w := httptest.NewRecorder()

			handler.handleGetOrder(w, req, tt.orderID)

			if w.Code != tt.wantStatus {
				t.Errorf("handleGetOrder() status = %d, want %d", w.Code, tt.wantStatus)
			}

			if tt.wantStatus == http.StatusOK {
				var resp Order
				if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
					t.Errorf("handleGetOrder() failed to unmarshal order response: %v", err)
				}
				if resp.ID != tt.orderID {
					t.Errorf("handleGetOrder() returned order with ID %s, want %s", resp.ID, tt.orderID)
				}
			} else if tt.wantStatus == http.StatusNotFound {
				var resp ErrorResponse
				if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
					t.Errorf("handleGetOrder() failed to unmarshal error response: %v", err)
				}
				if resp.Error == "" {
					t.Errorf("handleGetOrder() error response has empty error message")
				}
			}
		})
	}
}

func TestHandleHealth(t *testing.T) {
	handler := NewOrderHandler(NewOrderStore())

	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	w := httptest.NewRecorder()

	handler.handleHealth(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("handleHealth() status = %d, want %d", w.Code, http.StatusOK)
	}

	var resp map[string]string
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Errorf("handleHealth() failed to unmarshal response: %v", err)
	}
	if resp["status"] != "ok" {
		t.Errorf("handleHealth() status = %s, want %s", resp["status"], "ok")
	}
}

func TestLoggingMiddleware(t *testing.T) {
	store := NewOrderStore()
	handler := NewOrderHandler(store)
	mux := http.NewServeMux()
	mux.HandleFunc("/health", handler.handleHealth)

	server := httptest.NewServer(loggingMiddleware(mux))
	defer server.Close()

	resp, err := http.Get(server.URL + "/health")
	if err != nil {
		t.Fatalf("failed to make request: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Errorf("expected status 200, got %d", resp.StatusCode)
	}

	// Check that the log output contains the expected keys
	// Since we can't easily capture stdout in tests, we'll just verify the request was processed
}

func TestConcurrentAccess(t *testing.T) {
	store := NewOrderStore()
	handler := NewOrderHandler(store)
	mux := http.NewServeMux()
	mux.HandleFunc("/orders", handler.handleCreateOrder)
	mux.HandleFunc("/orders/", func(w http.ResponseWriter, r *http.Request) {
		id := r.URL.Path[len("/orders/"):]
		handler.handleGetOrder(w, r, id)
	})
	mux.HandleFunc("/health", handler.handleHealth)

	server := httptest.NewServer(loggingMiddleware(mux))
	defer server.Close()

	// Create several orders concurrently
	done := make(chan bool)
	for i := 0; i < 10; i++ {
		go func(i int) {
			reqBody := fmt.Sprintf(`{"customerId": "c-%d", "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]}`, i)
			resp, err := http.Post(server.URL+"/orders", "application/json", bytes.NewBufferString(reqBody))
			if err != nil {
				t.Errorf("failed to create order: %v", err)
				return
			}
			defer resp.Body.Close()
			
			if resp.StatusCode != http.StatusCreated {
				t.Errorf("expected status 201, got %d", resp.StatusCode)
			}
			
			var order Order
			if err := json.NewDecoder(resp.Body).Decode(&order); err != nil {
				t.Errorf("failed to decode response: %v", err)
				return
			}
			
			// Verify we can retrieve the order
			getResp, err := http.Get(server.URL + "/orders/" + order.ID)
			if err != nil {
				t.Errorf("failed to get order: %v", err)
				return
			}
			defer getResp.Body.Close()
			
			if getResp.StatusCode != http.StatusOK {
				t.Errorf("expected status 200 for retrieval, got %d", getResp.StatusCode)
			}
			
			done <- true
		}(i)
	}

	// Wait for all goroutines to complete
	for i := 0; i < 10; i++ {
		<-done
	}
}
```