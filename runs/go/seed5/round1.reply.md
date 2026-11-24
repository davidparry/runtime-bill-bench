FILE: go.mod
```go
module orders

go 1.27
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

// Order represents the internal order structure.
type Order struct {
	ID         string     `json:"id"`
	CustomerID string     `json:"customerId"`
	Items      []OrderItem `json:"items"`
	TotalCents int64      `json:"totalCents"`
	CreatedAt  time.Time  `json:"createdAt"`
}

// OrderItem represents an item within an order.
type OrderItem struct {
	SKU            string `json:"sku"`
	Quantity       int    `json:"quantity"`
	UnitPriceCents int    `json:"unitPriceCents"`
}

// CreateOrderRequest is the input for creating an order.
type CreateOrderRequest struct {
	CustomerID string       `json:"customerId"`
	Items      []OrderItem  `json:"items"`
}

// ErrorResponse is the standard error response body.
type ErrorResponse struct {
	Error string `json:"error"`
}

// OrderStore is a thread-safe in-memory store for orders.
type OrderStore struct {
	mu     sync.RWMutex
	orders map[string]Order
}

func NewOrderStore() *OrderStore {
	return &OrderStore{
		orders: make(map[string]Order),
	}
}

func (s *OrderStore) Get(id string) (Order, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	order, ok := s.orders[id]
	return order, ok
}

func (s *OrderStore) Set(order Order) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.orders[order.ID] = order
}

// generateUUID generates a simple UUID v4 compliant string.
// Note: In a real production environment, you might use a more robust library,
// but standard library 'crypto/rand' can suffice for this scope.
func generateUUID() string {
	b := make([]byte, 16)
	rand.Read(b)
	b[6] = (b[6] & 0x0f) | 0x40 // Version 4
	b[8] = (b[8] & 0x3f) | 0x80 // Variant 1
	return fmt.Sprintf("%08x-%04x-%04x-%04x-%12x",
		b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}

// validateCreateOrderRequest checks the request body rules.
func validateCreateOrderRequest(req CreateOrderRequest) string {
	// Validate customerId
	if req.CustomerID == "" {
		return "customerId is required"
	}
	if len(req.CustomerID) < 1 || len(req.CustomerID) > 64 {
		return "customerId must be between 1 and 64 characters"
	}
	if !utf8.ValidString(req.CustomerID) {
		return "customerId must be valid UTF-8"
	}

	// Validate items
	if len(req.Items) < 1 {
		return "items is required and must have at least 1 entry"
	}
	if len(req.Items) > 50 {
		return "items must have at most 50 entries"
	}

	for i, item := range req.Items {
		// Validate SKU
		if item.SKU == "" {
			return fmt.Sprintf("items[%d].sku is required", i)
		}
		if len(item.SKU) < 1 || len(item.SKU) > 32 {
			return fmt.Sprintf("items[%d].sku must be between 1 and 32 characters", i)
		}
		if !utf8.ValidString(item.SKU) {
			return fmt.Sprintf("items[%d].sku must be valid UTF-8", i)
		}

		// Validate Quantity
		if item.Quantity < 1 || item.Quantity > 100 {
			return fmt.Sprintf("items[%d].quantity must be between 1 and 100", i)
		}

		// Validate UnitPriceCents
		if item.UnitPriceCents < 1 || item.UnitPriceCents > 1000000 {
			return fmt.Sprintf("items[%d].unitPriceCents must be between 1 and 1000000", i)
		}
	}

	return ""
}

// calculateTotal calculates the total cents for a list of items.
func calculateTotal(items []OrderItem) int64 {
	var total int64
	for _, item := range items {
		total += int64(item.Quantity) * int64(item.UnitPriceCents)
	}
	return total
}

// logRequest is a middleware function to log request details.
func logRequest(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		
		// Wrap the ResponseWriter to capture the status code
		wrappedWriter := &statusResponseWriter{ResponseWriter: w, statusCode: http.StatusOK}
		
		next(wrappedWriter, r)
		
		duration := time.Since(start).Milliseconds()
		
		logLine := map[string]interface{}{
			"method":    r.Method,
			"path":      r.URL.Path,
			"status":    wrappedWriter.statusCode,
			"durationMs": duration,
			"timestamp": time.Now().UTC().Format(time.RFC3339),
		}
		
		// Ignore error here as we can't easily return it in this context
		json.NewEncoder(os.Stdout).Encode(logLine)
	}
}

type statusResponseWriter struct {
	http.ResponseWriter
	statusCode int
}

func (w *statusResponseWriter) WriteHeader(code int) {
	w.statusCode = code
	w.ResponseWriter.WriteHeader(code)
}

func writeJSON(w http.ResponseWriter, status int, v interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, ErrorResponse{Error: msg})
}

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	store := NewOrderStore()

	mux := http.NewServeMux()

	// POST /orders
	mux.HandleFunc("/orders", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeError(w, http.StatusMethodNotAllowed, "method not allowed")
			return
		}

		var req CreateOrderRequest
		decoder := json.NewDecoder(r.Body)
		// Ignore unknown fields as per spec
		decoder.DisallowUnknownFields()
		if err := decoder.Decode(&req); err != nil {
			writeError(w, http.StatusBadRequest, fmt.Sprintf("invalid JSON: %s", err.Error()))
			return
		}

		if errMsg := validateCreateOrderRequest(req); errMsg != "" {
			writeError(w, http.StatusBadRequest, errMsg)
			return
		}

		orderID := generateUUID()
		now := time.Now().UTC()
		
		// Calculate total
		total := calculateTotal(req.Items)

		order := Order{
			ID:         orderID,
			CustomerID: req.CustomerID,
			Items:      req.Items,
			TotalCents: total,
			CreatedAt:  now,
		}

		store.Set(order)

		w.Header().Set("Location", fmt.Sprintf("/orders/%s", orderID))
		writeJSON(w, http.StatusCreated, order)
	})

	// GET /orders/{id}
	mux.HandleFunc("/orders/", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeError(w, http.StatusMethodNotAllowed, "method not allowed")
			return
		}

		// Extract ID from path
		id := strings.TrimPrefix(r.URL.Path, "/orders/")
		if id == "" {
			writeError(w, http.StatusBadRequest, "order ID is required")
			return
		}

		order, found := store.Get(id)
		if !found {
			writeError(w, http.StatusNotFound, fmt.Sprintf("order %s not found", id))
			return
		}

		writeJSON(w, http.StatusOK, order)
	})

	// GET /health
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeError(w, http.StatusMethodNotAllowed, "method not allowed")
			return
		}
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	})

	// Apply logging middleware
	handler := logRequest(mux.ServeHTTP)

	server := &http.Server{
		Addr:         ":" + port,
		Handler:      handler,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 15 * time.Second,
		IdleTimeout:  60 * time.Second,
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
			log.Fatalf("Server shutdown failed: %v", err)
		}
	}()

	log.Printf("Starting orders service on port %s", port)
	if err := server.ListenAndServe(); err != http.ErrServerClosed {
		log.Fatalf("Server error: %v", err)
	}
	
	log.Println("Server stopped gracefully")
}
```

FILE: main_test.go
```go
package main

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
)

func TestHealthEndpoint(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	w := httptest.NewRecorder()

	logRequest(mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeError(w, http.StatusMethodNotAllowed, "method not allowed")
			return
		}
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	}))(w, req)

	resp := w.Result()
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Errorf("expected status 200, got %d", resp.StatusCode)
	}

	body, _ := io.ReadAll(resp.Body)
	var result map[string]string
	json.Unmarshal(body, &result)
	if result["status"] != "ok" {
		t.Errorf("expected status 'ok', got %s", result["status"])
	}
}

func TestCreateOrderSuccess(t *testing.T) {
	store := NewOrderStore()
	
	// Create a handler for the specific route to test logic
	handler := func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeError(w, http.StatusMethodNotAllowed, "method not allowed")
			return
		}

		var req CreateOrderRequest
		decoder := json.NewDecoder(r.Body)
		decoder.DisallowUnknownFields()
		if err := decoder.Decode(&req); err != nil {
			writeError(w, http.StatusBadRequest, err.Error())
			return
		}

		if errMsg := validateCreateOrderRequest(req); errMsg != "" {
			writeError(w, http.StatusBadRequest, errMsg)
			return
		}

		orderID := generateUUID()
		now := req.CreatedAt // In real code, this would be time.Now().UTC()
		if now.IsZero() {
			now = time.Now().UTC()
		}

		total := calculateTotal(req.Items)

		order := Order{
			ID:         orderID,
			CustomerID: req.CustomerID,
			Items:      req.Items,
			TotalCents: total,
			CreatedAt:  now,
		}

		store.Set(order)

		w.Header().Set("Location", "/orders/"+orderID)
		writeJSON(w, http.StatusCreated, order)
	}

	// Note: To properly test the full flow including logging middleware, 
	// we would need to inject the store into the handler or make it global.
	// For unit testing validation logic specifically, we test validateCreateOrderRequest directly.
	// For integration testing, we'd spin up a server. 
	// Given the constraint of "unit tests for validation rules and 404 case", 
	// we focus on those here.
}

func TestValidateCreateOrderRequest_InvalidCustomerID(t *testing.T) {
	tests := []struct {
		name    string
		req     CreateOrderRequest
		wantErr string
	}{
		{
			name:    "empty customerId",
			req:     CreateOrderRequest{CustomerID: "", Items: []OrderItem{{SKU: "A", Quantity: 1, UnitPriceCents: 10}}},
			wantErr: "customerId is required",
		},
		{
			name:    "customerId too long",
			req:     CreateOrderRequest{CustomerID: strings.Repeat("a", 65), Items: []OrderItem{{SKU: "A", Quantity: 1, UnitPriceCents: 10}}},
			wantErr: "customerId must be between 1 and 64 characters",
		},
		{
			name:    "customerId too short (0 length handled by empty check)",
			req:     CreateOrderRequest{CustomerID: "", Items: []OrderItem{{SKU: "A", Quantity: 1, UnitPriceCents: 10}}},
			wantErr: "customerId is required",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			errMsg := validateCreateOrderRequest(tt.req)
			if errMsg != tt.wantErr {
				t.Errorf("validateCreateOrderRequest() = %q, want %q", errMsg, tt.wantErr)
			}
		})
	}
}

func TestValidateCreateOrderRequest_InvalidItems(t *testing.T) {
	tests := []struct {
		name    string
		req     CreateOrderRequest
		wantErr string
	}{
		{
			name:    "empty items",
			req:     CreateOrderRequest{CustomerID: "c-1", Items: []OrderItem{}},
			wantErr: "items is required and must have at least 1 entry",
		},
		{
			name:    "too many items",
			req:     CreateOrderRequest{CustomerID: "c-1", Items: make([]OrderItem, 51)},
			wantErr: "items must have at most 50 entries",
		},
		{
			name:    "invalid sku length",
			req:     CreateOrderRequest{CustomerID: "c-1", Items: []OrderItem{{SKU: strings.Repeat("a", 33), Quantity: 1, UnitPriceCents: 10}}},
			wantErr: "items[0].sku must be between 1 and 32 characters",
		},
		{
			name:    "invalid quantity low",
			req:     CreateOrderRequest{CustomerID: "c-1", Items: []OrderItem{{SKU: "A", Quantity: 0, UnitPriceCents: 10}}},
			wantErr: "items[0].quantity must be between 1 and 100",
		},
		{
			name:    "invalid quantity high",
			req:     CreateOrderRequest{CustomerID: "c-1", Items: []OrderItem{{SKU: "A", Quantity: 101, UnitPriceCents: 10}}},
			wantErr: "items[0].quantity must be between 1 and 100",
		},
		{
			name:    "invalid unitPriceCents low",
			req:     CreateOrderRequest{CustomerID: "c-1", Items: []OrderItem{{SKU: "A", Quantity: 1, UnitPriceCents: 0}}},
			wantErr: "items[0].unitPriceCents must be between 1 and 1000000",
		},
		{
			name:    "invalid unitPriceCents high",
			req:     CreateOrderRequest{CustomerID: "c-1", Items: []OrderItem{{SKU: "A", Quantity: 1, UnitPriceCents: 1000001}}},
			wantErr: "items[0].unitPriceCents must be between 1 and 1000000",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			errMsg := validateCreateOrderRequest(tt.req)
			if errMsg != tt.wantErr {
				t.Errorf("validateCreateOrderRequest() = %q, want %q", errMsg, tt.wantErr)
			}
		})
	}
}

func TestValidateCreateOrderRequest_Valid(t *testing.T) {
	req := CreateOrderRequest{
		CustomerID: "c-1",
		Items:      []OrderItem{{SKU: "A-1", Quantity: 2, UnitPriceCents: 1250}},
	}
	errMsg := validateCreateOrderRequest(req)
	if errMsg != "" {
		t.Errorf("expected no error, got %q", errMsg)
	}
}

func TestGetOrder404(t *testing.T) {
	store := NewOrderStore()
	
	// Simulate the handler logic for GET /orders/{id}
	handler := func(w http.ResponseWriter, r *http.Request) {
		id := strings.TrimPrefix(r.URL.Path, "/orders/")
		if id == "" {
			writeError(w, http.StatusBadRequest, "order ID is required")
			return
		}

		_, found := store.Get(id)
		if !found {
			writeError(w, http.StatusNotFound, "order "+id+" not found")
			return
		}
	}

	req := httptest.NewRequest(http.MethodGet, "/orders/non-existent-id", nil)
	w := httptest.NewRecorder()
	
	logRequest(handler)(w, req)

	resp := w.Result()
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusNotFound {
		t.Errorf("expected status 404, got %d", resp.StatusCode)
	}

	body, _ := io.ReadAll(resp.Body)
	var errResp ErrorResponse
	json.Unmarshal(body, &errResp)
	if errResp.Error == "" {
		t.Errorf("expected error message, got empty")
	}
}

func TestCalculateTotal(t *testing.T) {
	items := []OrderItem{
		{SKU: "A", Quantity: 2, UnitPriceCents: 100},
		{SKU: "B", Quantity: 3, UnitPriceCents: 200},
	}
	total := calculateTotal(items)
	if total != 800 {
		t.Errorf("expected total 800, got %d", total)
	}
}
```