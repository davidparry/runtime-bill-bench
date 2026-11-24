FILE: go.mod
```go
module orders

go 1.21
```

FILE: main.go
```go
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
```

FILE: main_test.go
```go
package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestValidateOrderInput(t *testing.T) {
	tests := []struct {
		name        string
		customerID  string
		items       []Item
		expectError bool
		errorMsg    string
	}{
		{
			name:        "valid order",
			customerID:  "c-1",
			items:       []Item{{SKU: "A-1", Quantity: 2, UnitPriceCents: 1250}},
			expectError: false,
		},
		{
			name:        "customerId too short",
			customerID:  "",
			items:       []Item{{SKU: "A-1", Quantity: 2, UnitPriceCents: 1250}},
			expectError: true,
			errorMsg:    "customerId must be between 1 and 64 characters",
		},
		{
			name:        "customerId too long",
			customerID:  strings.Repeat("a", 65),
			items:       []Item{{SKU: "A-1", Quantity: 2, UnitPriceCents: 1250}},
			expectError: true,
			errorMsg:    "customerId must be between 1 and 64 characters",
		},
		{
			name:        "empty items",
			customerID:  "c-1",
			items:       []Item{},
			expectError: true,
			errorMsg:    "items must be between 1 and 50 entries",
		},
		{
			name:        "too many items",
			customerID:  "c-1",
			items:       make([]Item, 51),
			expectError: true,
			errorMsg:    "items must be between 1 and 50 entries",
		},
		{
			name:        "sku too short",
			customerID:  "c-1",
			items:       []Item{{SKU: "", Quantity: 2, UnitPriceCents: 1250}},
			expectError: true,
			errorMsg:    "item[0].sku must be between 1 and 32 characters",
		},
		{
			name:        "sku too long",
			customerID:  "c-1",
			items:       []Item{{SKU: strings.Repeat("a", 33), Quantity: 2, UnitPriceCents: 1250}},
			expectError: true,
			errorMsg:    "item[0].sku must be between 1 and 32 characters",
		},
		{
			name:        "quantity too low",
			customerID:  "c-1",
			items:       []Item{{SKU: "A-1", Quantity: 0, UnitPriceCents: 1250}},
			expectError: true,
			errorMsg:    "item[0].quantity must be between 1 and 100",
		},
		{
			name:        "quantity too high",
			customerID:  "c-1",
			items:       []Item{{SKU: "A-1", Quantity: 101, UnitPriceCents: 1250}},
			expectError: true,
			errorMsg:    "item[0].quantity must be between 1 and 100",
		},
		{
			name:        "unitPriceCents too low",
			customerID:  "c-1",
			items:       []Item{{SKU: "A-1", Quantity: 2, UnitPriceCents: 0}},
			expectError: true,
			errorMsg:    "item[0].unitPriceCents must be between 1 and 1000000",
		},
		{
			name:        "unitPriceCents too high",
			customerID:  "c-1",
			items:       []Item{{SKU: "A-1", Quantity: 2, UnitPriceCents: 1000001}},
			expectError: true,
			errorMsg:    "item[0].unitPriceCents must be between 1 and 1000000",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := validateOrderInput(tt.customerID, tt.items)
			if tt.expectError {
				if err == nil {
					t.Errorf("expected error but got nil")
				} else if err.Error() != tt.errorMsg {
					t.Errorf("expected error message '%s' but got '%s'", tt.errorMsg, err.Error())
				}
			} else {
				if err != nil {
					t.Errorf("expected no error but got '%s'", err.Error())
				}
			}
		})
	}
}

func TestGetOrder404(t *testing.T) {
	store := NewStore()
	handler := handleGetOrder(store)

	req := httptest.NewRequest(http.MethodGet, "/orders/non-existent-id", nil)
	w := httptest.NewRecorder()

	handler.ServeHTTP(w, req)

	if w.Code != http.StatusNotFound {
		t.Errorf("expected status 404, got %d", w.Code)
	}

	var response map[string]string
	if err := json.Unmarshal(w.Body.Bytes(), &response); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}

	if response["error"] != "Order not found" {
		t.Errorf("expected error message 'Order not found', got '%s'", response["error"])
	}
}

func TestCreateOrderSuccess(t *testing.T) {
	store := NewStore()
	handler := handleCreateOrder(store)

	body := `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}]}`
	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	handler.ServeHTTP(w, req)

	if w.Code != http.StatusCreated {
		t.Errorf("expected status 201, got %d", w.Code)
	}

	location := w.Header().Get("Location")
	if location == "" {
		t.Error("expected Location header")
	}

	var response Order
	if err := json.Unmarshal(w.Body.Bytes(), &response); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}

	if response.ID == "" {
		t.Error("expected non-empty ID")
	}
	if response.CustomerID != "c-1" {
		t.Errorf("expected customerId 'c-1', got '%s'", response.CustomerID)
	}
	if len(response.Items) != 1 {
		t.Errorf("expected 1 item, got %d", len(response.Items))
	}
	if response.TotalCents != 2500 {
		t.Errorf("expected totalCents 2500, got %d", response.TotalCents)
	}
}

func TestCreateOrderInvalidJSON(t *testing.T) {
	store := NewStore()
	handler := handleCreateOrder(store)

	body := `{"invalid json`
	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	handler.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected status 400, got %d", w.Code)
	}
}

func TestCreateOrderMissingFields(t *testing.T) {
	store := NewStore()
	handler := handleCreateOrder(store)

	tests := []struct {
		name string
		body string
	}{
		{
			name: "missing customerId",
			body: `{"items": [{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}]}`,
		},
		{
			name: "missing items",
			body: `{"customerId": "c-1"}`,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(tt.body))
			req.Header.Set("Content-Type", "application/json")
			w := httptest.NewRecorder()

			handler.ServeHTTP(w, req)

			if w.Code != http.StatusBadRequest {
				t.Errorf("expected status 400, got %d", w.Code)
			}
		})
	}
}

func TestHealthEndpoint(t *testing.T) {
	handler := handleHealth()

	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	w := httptest.NewRecorder()

	handler.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected status 200, got %d", w.Code)
	}

	var response map[string]string
	if err := json.Unmarshal(w.Body.Bytes(), &response); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}

	if response["status"] != "ok" {
		t.Errorf("expected status 'ok', got '%s'", response["status"])
	}
}
```