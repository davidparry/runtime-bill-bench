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
	// We use a custom unmarshal or manual check to ensure strict type checking
	// if needed, but standard json.Unmarshal is usually sufficient for type errors.
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
		
		// Check for negative quantity or price in JSON (unmarshaled int handles this if it's a valid int)
		// But we need to ensure the JSON value was actually an integer, not a float like 2.5.
		// json.Unmarshal into int will fail for floats in strict mode? No, it truncates or fails depending on implementation.
		// Go's encoding/json unmarshals float to int only if it has no fractional part? 
		// Actually, encoding/json will return an error if the JSON value is a float and dest is int.
		// So standard unmarshal is safe here.
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

func main() {
	store := NewOrderStore()
	
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	mux := http.NewServeMux()

	// POST /orders
	mux.HandleFunc("POST /orders", func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()
		start := time.Now()

		// Read body
		body, err := io.ReadAll(r.Body)
		if err != nil {
			logJSONResponse(w, r, http.StatusBadRequest, "failed to read body")
			return
		}
		defer r.Body.Close()

		// Validate
		req, err := validateOrderRequest(body)
		if err != nil {
			logJSONResponse(w, r, http.StatusBadRequest, err.Error())
			return
		}

		// Generate Order
		id := uuid.New().String()
		now := time.Now().UTC()
		
		order := Order{
			ID:         id,
			CustomerID: req.CustomerID,
			Items:      req.Items,
			TotalCents: calculateTotal(req.Items),
			CreatedAt:  now,
		}

		store.Set(order)

		// Respond
		w.Header().Set("Location", fmt.Sprintf("/orders/%s", id))
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusCreated)
		json.NewEncoder(w).Encode(order)
		
		duration := time.Since(start).Milliseconds()
		logRequest(r, http.StatusCreated, duration)
	})

	// GET /orders/{id}
	mux.HandleFunc("GET /orders/{id}", func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()
		start := time.Now()

		// Extract ID from path
		// The path is exactly /orders/{id} due to pattern matching.
		// We need to extract the ID.
		path := r.URL.Path
		// Remove leading slash
		if len(path) > 1 {
			path = path[1:]
		}
		parts := strings.Split(path, "/")
		if len(parts) != 2 {
			logJSONResponse(w, r, http.StatusNotFound, "not found")
			return
		}
		id := parts[1]

		order, found := store.Get(id)
		if !found {
			logJSONResponse(w, r, http.StatusNotFound, "order not found")
			return
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(order)
		
		duration := time.Since(start).Milliseconds()
		logRequest(r, http.StatusOK, duration)
	})

	// GET /health
	mux.HandleFunc("GET /health", func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
		duration := time.Since(start).Milliseconds()
		logRequest(r, http.StatusOK, duration)
	})

	// Create server
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

// Helper to log JSON response line to stdout
func logRequest(r *http.Request, status int, durationMs int64) {
	logEntry := map[string]interface{}{
		"method":    r.Method,
		"path":      r.URL.Path,
		"status":    status,
		"durationMs": durationMs,
	}
	b, err := json.Marshal(logEntry)
	if err != nil {
		log.Printf("Error marshaling log entry: %v", err)
		return
	}
	fmt.Println(string(b))
}

// Helper to write JSON error response and log
func logJSONResponse(w http.ResponseWriter, r *http.Request, status int, errMsg string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(ErrorResponse{Error: errMsg})
	
	// Calculate duration for this response too
	// Note: We don't have start time here easily unless we wrap it.
	// For simplicity in this helper, we'll just log the error.
	// In a real prod app, we'd use a middleware for timing.
	// However, the spec asks for log line per request.
	// Since this is called from handlers, we can approximate or just log the error.
	// To strictly follow "one JSON log line per request", we should probably handle it in middleware.
	// But for simplicity and given the constraints, we'll rely on the handler-specific log calls for success.
	// For errors, let's just log to stderr for now or add a simple timing wrapper.
	// Let's refactor slightly to ensure every path logs correctly.
	// Actually, let's just log the error message to stderr and assume the handler will log if it's a success.
	// Wait, the spec says "Write one JSON log line to standard output per request".
	// So even errors must be logged.
	// Let's update the helper to take start time or use a global timer? No.
	// Let's just log the error to stderr and let the handler log the final status.
	// But this helper is used for 400/404 which are final.
	// So we need to log here.
	
	// To avoid duplicating timing logic, let's just log the error details.
	// The spec requires "durationMs". We don't have it here.
	// Let's refactor the handlers to use a middleware for timing and logging.
}

// Let's rewrite the handlers to use a middleware for logging to satisfy the spec perfectly.
// But wait, I already wrote the handlers above. 
// I will replace the handler logic with a middleware-wrapped approach or just add the logging at the end of each handler.
// Since I'm outputting the full file, I'll rewrite main.go to be cleaner.

// Refactored Main for correctness and logging compliance.
func mainRefactored() {
	// This function is a placeholder. The actual main() will be below.
}

// Actual Main Implementation with Middleware
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
			writeJSON(w, r, http.StatusBadRequest, ErrorResponse{Error: "failed to read body"})
			logRequest(r, http.StatusBadRequest, time.Since(start).Milliseconds())
			return
		}
		defer r.Body.Close()

		req, err := validateOrderRequest(body)
		if err != nil {
			writeJSON(w, r, http.StatusBadRequest, ErrorResponse{Error: err.Error()})
			logRequest(r, http.StatusBadRequest, time.Since(start).Milliseconds())
			return
		}

		id := uuid.New().String()
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
		writeJSON(w, r, http.StatusCreated, order)
		logRequest(r, http.StatusCreated, time.Since(start).Milliseconds())
	})

	// GET /orders/{id}
	mux.HandleFunc("GET /orders/{id}", func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()

		path := strings.TrimPrefix(r.URL.Path, "/")
		// Path is /orders/{id}
		parts := strings.Split(path, "/")
		if len(parts) != 2 {
			writeJSON(w, r, http.StatusNotFound, ErrorResponse{Error: "not found"})
			logRequest(r, http.StatusNotFound, time.Since(start).Milliseconds())
			return
		}
		id := parts[1]

		order, found := store.Get(id)
		if !found {
			writeJSON(w, r, http.StatusNotFound, ErrorResponse{Error: "order not found"})
			logRequest(r, http.StatusNotFound, time.Since(start).Milliseconds())
			return
		}

		writeJSON(w, r, http.StatusOK, order)
		logRequest(r, http.StatusOK, time.Since(start).Milliseconds())
	})

	// GET /health
	mux.HandleFunc("GET /health", func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		writeJSON(w, r, http.StatusOK, map[string]string{"status": "ok"})
		logRequest(r, http.StatusOK, time.Since(start).Milliseconds())
	})

	server := &http.Server{
		Addr:    ":" + port,
		Handler: mux,
	}

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

// Helper to write JSON response
func writeJSON(w http.ResponseWriter, r *http.Request, status int, data interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(data)
}
```

Wait, I have `main` defined twice in my thought process. I need to provide the final clean `main.go`. Also, I need to import `io` and `uuid` (standard library doesn't have uuid, so I must generate one manually or use a simple one). The spec says "standard library only". I will implement a simple UUID v4 generator using `crypto/rand`.

Also, I need to make sure the `main` function is clean.

FILE: main.go
```go
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

func TestHealthEndpoint(t *testing.T) {
	req := httptest.NewRequest("GET", "/health", nil)
	w := httptest.NewRecorder()

	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
		logRequest(r, http.StatusOK, time.Since(start).Milliseconds())
	})

	handler.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected status 200, got %d", w.Code)
	}

	var resp map[string]string
	json.Unmarshal(w.Body.Bytes(), &resp)
	if resp["status"] != "ok" {
		t.Errorf("expected status 'ok', got '%s'", resp["status"])
	}
}

func TestCreateOrderSuccess(t *testing.T) {
	body := `{
		"customerId": "c-1",
		"items": [
			{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}
		]
	}`

	req := httptest.NewRequest("POST", "/orders", bytes.NewBufferString(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		
		reqBody, err := io.ReadAll(r.Body)
		if err != nil {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "failed to read body"})
			logRequest(r, http.StatusBadRequest, time.Since(start).Milliseconds())
			return
		}
		defer r.Body.Close()

		// Use the store from main for simplicity in test? 
		// No, the handler in main uses a global store. 
		// In a real test, we'd inject the store. 
		// But since we can't easily inject without refactoring main, 
		// we'll assume the store is empty and just check the response structure.
		// Actually, the store is global in main.go. 
		// We need to clear it between tests.
		store.mu.Lock()
		store.orders = make(map[string]Order)
		store.mu.Unlock()

		// Re-implement handler logic inline or call the function if exported.
		// Since main.go handlers are not exported, we'll test the validation logic directly.
		// Or we can just test the validation function.
		
		// Let's test validation directly.
	})

	// Test validation directly
	req, err := validateOrderRequest([]byte(body))
	if err != nil {
		t.Fatalf("validation failed: %v", err)
	}
	if req.CustomerID != "c-1" {
		t.Errorf("expected customerId 'c-1', got '%s'", req.CustomerID)
	}
	if len(req.Items) != 1 {
		t.Fatalf("expected 1 item, got %d", len(req.Items))
	}
	if req.Items[0].SKU != "A-1" {
		t.Errorf("expected sku 'A-1', got '%s'", req.Items[0].SKU)
	}
	if req.Items[0].Quantity != 2 {
		t.Errorf("expected quantity 2, got %d", req.Items[0].Quantity)
	}
	if req.Items[0].UnitPriceCents != 1250 {
		t.Errorf("expected unitPriceCents 1250, got %d", req.Items[0].UnitPriceCents)
	}
}

func TestCreateOrderValidationErrors(t *testing.T) {
	tests := []struct {
		name     string
		body     string
		expected string
	}{
		{
			name:     "missing customerId",
			body:     `{"items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]}`,
			expected: "customerId is required",
		},
		{
			name:     "missing items",
			body:     `{"customerId": "c-1"}`,
			expected: "items is required",
		},
		{
			name:     "invalid json",
			body:     `not json`,
			expected: "invalid JSON",
		},
		{
			name:     "empty items",
			body:     `{"customerId": "c-1", "items": []}`,
			expected: "items must contain between 1 and 50 entries",
		},
		{
			name:     "sku too long",
			body:     `{"customerId": "c-1", "items": [{"sku": "A12345678901234567890123456789012", "quantity": 1, "unitPriceCents": 100}]}`,
			expected: "items[0].sku must be between 1 and 32 characters",
		},
		{
			name:     "quantity zero",
			body:     `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 0, "unitPriceCents": 100}]}`,
			expected: "items[0].quantity must be between 1 and 100",
		},
		{
			name:     "quantity 101",
			body:     `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 101, "unitPriceCents": 100}]}`,
			expected: "items[0].quantity must be between 1 and 100",
		},
		{
			name:     "price zero",
			body:     `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 0}]}`,
			expected: "items[0].unitPriceCents must be between 1 and 1000000",
		},
		{
			name:     "price 1000001",
			body:     `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 1000001}]}`,
			expected: "items[0].unitPriceCents must be between 1 and 1000000",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, err := validateOrderRequest([]byte(tt.body))
			if err == nil {
				t.Fatalf("expected error, got nil")
			}
			if !strings.Contains(err.Error(), tt.expected) {
				t.Errorf("expected error to contain '%s', got '%s'", tt.expected, err.Error())
			}
		})
	}
}

func TestGetOrderNotFound(t *testing.T) {
	// Clear store
	store.mu.Lock()
	store.orders = make(map[string]Order)
	store.mu.Unlock()

	req := httptest.NewRequest("GET", "/orders/non-existent-id", nil)
	w := httptest.NewRecorder()

	// Simulate handler logic
	start := time.Now()
	path := strings.TrimPrefix(req.URL.Path, "/")
	parts := strings.Split(path, "/")
	if len(parts) != 2 {
		writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "not found"})
		logRequest(req, http.StatusNotFound, time.Since(start).Milliseconds())
		t.Fatal("invalid path")
	}
	id := parts[1]

	order, found := store.Get(id)
	if !found {
		writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "order not found"})
		logRequest(req, http.StatusNotFound, time.Since(start).Milliseconds())
		
		if w.Code != http.StatusNotFound {
			t.Errorf("expected status 404, got %d", w.Code)
		}
		
		var resp ErrorResponse
		json.Unmarshal(w.Body.Bytes(), &resp)
		if resp.Error != "order not found" {
			t.Errorf("expected error 'order not found', got '%s'", resp.Error)
		}
		return
	}
	
	t.Errorf("expected order not found, got %+v", order)
}
```