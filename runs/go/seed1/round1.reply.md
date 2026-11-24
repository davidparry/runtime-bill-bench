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
	"net/http"
	"os"
	"os/signal"
	"strings"
	"sync"
	"syscall"
	"time"
	"unicode/utf8"
	"uuid"
)

// Order represents the order entity stored in memory.
type Order struct {
	ID         string    `json:"id"`
	CustomerID string    `json:"customerId"`
	Items      []OrderItem `json:"items"`
	TotalCents int64     `json:"totalCents"`
	CreatedAt  time.Time `json:"createdAt"`
}

// OrderItem represents an item within an order.
type OrderItem struct {
	SKU            string `json:"sku"`
	Quantity       int    `json:"quantity"`
	UnitPriceCents int    `json:"unitPriceCents"`
}

// CreateOrderRequest represents the incoming request body for creating an order.
type CreateOrderRequest struct {
	CustomerID string         `json:"customerId"`
	Items      []OrderItemIn `json:"items"`
}

// OrderItemIn represents an item in the incoming request.
// We use a separate struct to handle validation before populating the final OrderItem.
type OrderItemIn struct {
	SKU            *string `json:"sku"`
	Quantity       *int    `json:"quantity"`
	UnitPriceCents *int    `json:"unitPriceCents"`
}

// ErrorResponse is the JSON structure for error responses.
type ErrorResponse struct {
	Error string `json:"error"`
}

// In-memory store for orders.
type OrderStore struct {
	mu    sync.RWMutex
	orders map[string]Order
}

func NewOrderStore() *OrderStore {
	return &OrderStore{
		orders: make(map[string]Order),
	}
}

func (s *OrderStore) Create(order Order) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, exists := s.orders[order.ID]; exists {
		return fmt.Errorf("order %s already exists", order.ID)
	}
	s.orders[order.ID] = order
	return nil
}

func (s *OrderStore) Get(id string) (Order, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	order, exists := s.orders[id]
	return order, exists
}

// LoggerMiddleware logs each request with method, path, status, and duration.
func LoggerMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		
		// Wrap the response writer to capture the status code
		wrappedWriter := &statusResponseWriter{ResponseWriter: w, status: http.StatusOK}
		
		next.ServeHTTP(wrappedWriter, r)
		
		duration := time.Since(start)
		
		logEntry := map[string]interface{}{
			"method":     r.Method,
			"path":       r.URL.Path,
			"status":     wrappedWriter.status,
			"durationMs": duration.Milliseconds(),
		}
		
		if r.RemoteAddr != "" {
			logEntry["remoteAddr"] = r.RemoteAddr
		}
		
		logJSON(logEntry)
	})
}

type statusResponseWriter struct {
	http.ResponseWriter
	status int
}

func (w *statusResponseWriter) WriteHeader(code int) {
	w.status = code
	w.ResponseWriter.WriteHeader(code)
}

func logJSON(v interface{}) {
	b, err := json.Marshal(v)
	if err != nil {
		// If we can't marshal the log, fall back to printing the error
		// This is unlikely to fail but good practice
		log.Printf("Failed to marshal log entry: %v", err)
		return
	}
	fmt.Println(string(b))
}

func validateCustomerID(customerID string) error {
	if customerID == "" {
		return fmt.Errorf("customerId is required")
	}
	if len(customerID) < 1 || len(customerID) > 64 {
		return fmt.Errorf("customerId must be between 1 and 64 characters")
	}
	return nil
}

func validateItems(items []OrderItemIn) ([]OrderItem, error) {
	if len(items) < 1 {
		return nil, fmt.Errorf("items is required and must have at least 1 entry")
	}
	if len(items) > 50 {
		return nil, fmt.Errorf("items must have at most 50 entries")
	}

	var validatedItems []OrderItem
	for i, item := range items {
		if item.SKU == nil {
			return nil, fmt.Errorf("items[%d].sku is required", i)
		}
		if *item.SKU == "" {
			return nil, fmt.Errorf("items[%d].sku must not be empty", i)
		}
		if utf8.RuneCountInString(*item.SKU) < 1 || utf8.RuneCountInString(*item.SKU) > 32 {
			return nil, fmt.Errorf("items[%d].sku must be between 1 and 32 characters", i)
		}

		if item.Quantity == nil {
			return nil, fmt.Errorf("items[%d].quantity is required", i)
		}
		if *item.Quantity < 1 || *item.Quantity > 100 {
			return nil, fmt.Errorf("items[%d].quantity must be between 1 and 100", i)
		}

		if item.UnitPriceCents == nil {
			return nil, fmt.Errorf("items[%d].unitPriceCents is required", i)
		}
		if *item.UnitPriceCents < 1 || *item.UnitPriceCents > 1000000 {
			return nil, fmt.Errorf("items[%d].unitPriceCents must be between 1 and 1000000", i)
		}

		validatedItems = append(validatedItems, OrderItem{
			SKU:            *item.SKU,
			Quantity:       *item.Quantity,
			UnitPriceCents: *item.UnitPriceCents,
		})
	}

	return validatedItems, nil
}

func calculateTotal(items []OrderItem) int64 {
	var total int64
	for _, item := range items {
		total += int64(item.Quantity) * int64(item.UnitPriceCents)
	}
	return total
}

func writeJSON(w http.ResponseWriter, status int, v interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, status int, message string) {
	writeJSON(w, status, ErrorResponse{Error: message})
}

func handleCreateOrder(store *OrderStore) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeError(w, http.StatusMethodNotAllowed, "method not allowed")
			return
		}

		var req CreateOrderRequest
		decoder := json.NewDecoder(r.Body)
		// Use strict decoding to catch unknown fields if needed, though spec says ignore.
		// Standard json.Decoder ignores unknown fields by default.
		if err := decoder.Decode(&req); err != nil {
			writeError(w, http.StatusBadRequest, fmt.Sprintf("invalid JSON: %s", err.Error()))
			return
		}

		// Validate CustomerID
		if err := validateCustomerID(req.CustomerID); err != nil {
			writeError(w, http.StatusBadRequest, err.Error())
			return
		}

		// Validate Items
		validatedItems, err := validateItems(req.Items)
		if err != nil {
			writeError(w, http.StatusBadRequest, err.Error())
			return
		}

		// Generate Order
		id := uuid.New().String()
		totalCents := calculateTotal(validatedItems)
		now := time.Now().UTC()

		order := Order{
			ID:         id,
			CustomerID: req.CustomerID,
			Items:      validatedItems,
			TotalCents: totalCents,
			CreatedAt:  now,
		}

		// Store Order
		if err := store.Create(order); err != nil {
			// This should theoretically not happen in a fresh store unless UUID collision occurs
			writeError(w, http.StatusInternalServerError, "failed to create order")
			return
		}

		// Respond
		w.Header().Set("Location", fmt.Sprintf("/orders/%s", id))
		writeJSON(w, http.StatusCreated, order)
	}
}

func handleGetOrder(store *OrderStore) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeError(w, http.StatusMethodNotAllowed, "method not allowed")
			return
		}

		// Extract ID from path /orders/{id}
		path := r.URL.Path
		if !strings.HasPrefix(path, "/orders/") {
			writeError(w, http.StatusNotFound, "order not found")
			return
		}
		id := strings.TrimPrefix(path, "/orders/")
		if id == "" {
			writeError(w, http.StatusBadRequest, "order ID is required")
			return
		}

		order, exists := store.Get(id)
		if !exists {
			writeError(w, http.StatusNotFound, "order not found")
			return
		}

		writeJSON(w, http.StatusOK, order)
	}
}

func handleHealth() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeError(w, http.StatusMethodNotAllowed, "method not allowed")
			return
		}
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	}
}

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	store := NewOrderStore()

	mux := http.NewServeMux()
	
	// Register endpoints
	mux.HandleFunc("/orders", handleCreateOrder(store))
	mux.HandleFunc("/orders/", handleGetOrder(store))
	mux.HandleFunc("/health", handleHealth())

	// Wrap with logger
	handler := LoggerMiddleware(mux)

	server := &http.Server{
		Addr:    ":" + port,
		Handler: handler,
	}

	// Graceful shutdown setup
	ctx, cancel := context.WithCancel(context.Background())
	
	go func() {
		sigChan := make(chan os.Signal, 1)
		signal.Notify(sigChan, syscall.SIGTERM, syscall.SIGINT)
		sig := <-sigChan
		log.Printf("Received signal %v, shutting down...", sig)
		cancel() // Cancel context to signal shutdown
	}()

	go func() {
		log.Printf("Listening on :%s", port)
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("Server error: %v", err)
		}
	}()

	// Wait for cancellation
	<-ctx.Done()

	// Shutdown server with timeout
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer shutdownCancel()

	if err := server.Shutdown(shutdownCtx); err != nil {
		log.Fatalf("Server forced to shutdown: %v", err)
	}

	log.Println("Server exited gracefully")
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

func TestHandleCreateOrder(t *testing.T) {
	store := NewOrderStore()
	handler := handleCreateOrder(store)

	tests := []struct {
		name          string
		payload       interface{}
		expectedStatus int
	}{
		{
			name: "valid order",
			payload: map[string]interface{}{
				"customerId": "c-1",
				"items": []map[string]interface{}{
					{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250},
				},
			},
			expectedStatus: http.StatusCreated,
		},
		{
			name: "invalid JSON",
			payload: []byte("not json"),
			expectedStatus: http.StatusBadRequest,
		},
		{
			name: "missing customerId",
			payload: map[string]interface{}{
				"items": []map[string]interface{}{
					{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250},
				},
			},
			expectedStatus: http.StatusBadRequest,
		},
		{
			name: "customerId too long",
			payload: map[string]interface{}{
				"customerId": "a",
				"items": []map[string]interface{}{
					{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250},
				},
			},
			expectedStatus: http.StatusBadRequest,
		},
		{
			name: "items empty",
			payload: map[string]interface{}{
				"customerId": "c-1",
				"items":      []map[string]interface{}{},
			},
			expectedStatus: http.StatusBadRequest,
		},
		{
			name: "items too many",
			payload: map[string]interface{}{
				"customerId": "c-1",
				"items": func() []map[string]interface{} {
					items := make([]map[string]interface{}, 51)
					for i := 0; i < 51; i++ {
						items[i] = map[string]interface{}{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}
					}
					return items
				}(),
			},
			expectedStatus: http.StatusBadRequest,
		},
		{
			name: "item sku missing",
			payload: map[string]interface{}{
				"customerId": "c-1",
				"items": []map[string]interface{}{
					{"quantity": 2, "unitPriceCents": 1250},
				},
			},
			expectedStatus: http.StatusBadRequest,
		},
		{
			name: "item sku too long",
			payload: map[string]interface{}{
				"customerId": "c-1",
				"items": []map[string]interface{}{
					{"sku": "a", "quantity": 2, "unitPriceCents": 1250},
				},
			},
			expectedStatus: http.StatusBadRequest,
		},
		{
			name: "item quantity zero",
			payload: map[string]interface{}{
				"customerId": "c-1",
				"items": []map[string]interface{}{
					{"sku": "A-1", "quantity": 0, "unitPriceCents": 1250},
				},
			},
			expectedStatus: http.StatusBadRequest,
		},
		{
			name: "item quantity too high",
			payload: map[string]interface{}{
				"customerId": "c-1",
				"items": []map[string]interface{}{
					{"sku": "A-1", "quantity": 101, "unitPriceCents": 1250},
				},
			},
			expectedStatus: http.StatusBadRequest,
		},
		{
			name: "item unitPriceCents zero",
			payload: map[string]interface{}{
				"customerId": "c-1",
				"items": []map[string]interface{}{
					{"sku": "A-1", "quantity": 2, "unitPriceCents": 0},
				},
			},
			expectedStatus: http.StatusBadRequest,
		},
		{
			name: "item unitPriceCents too high",
			payload: map[string]interface{}{
				"customerId": "c-1",
				"items": []map[string]interface{}{
					{"sku": "A-1", "quantity": 2, "unitPriceCents": 1000001},
				},
			},
			expectedStatus: http.StatusBadRequest,
		},
		{
			name: "unknown fields ignored",
			payload: map[string]interface{}{
				"customerId": "c-1",
				"items": []map[string]interface{}{
					{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250, "extra": "field"},
				},
				"extraTop": "field",
			},
			expectedStatus: http.StatusCreated,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var body []byte
			var err error
			switch p := tt.payload.(type) {
			case []byte:
				body = p
			default:
				body, err = json.Marshal(p)
				if err != nil {
					t.Fatalf("failed to marshal payload: %v", err)
				}
			}

			req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewReader(body))
			rec := httptest.NewRecorder()

			handler.ServeHTTP(rec, req)

			if rec.Code != tt.expectedStatus {
				t.Errorf("expected status %d, got %d. Body: %s", tt.expectedStatus, rec.Code, rec.Body.String())
			}
		})
	}
}

func TestHandleGetOrder(t *testing.T) {
	store := NewOrderStore()
	handler := handleGetOrder(store)

	// Create a valid order first
	validOrder := Order{
		ID:         "test-id-123",
		CustomerID: "c-1",
		Items:      []OrderItem{{SKU: "A-1", Quantity: 2, UnitPriceCents: 1250}},
		TotalCents: 2500,
		CreatedAt:  timeNow(),
	}
	store.Create(validOrder)

	tests := []struct {
		name          string
		path          string
		expectedStatus int
	}{
		{
			name:          "valid order",
			path:          "/orders/test-id-123",
			expectedStatus: http.StatusOK,
		},
		{
			name:          "non-existent order",
			path:          "/orders/non-existent",
			expectedStatus: http.StatusNotFound,
		},
		{
			name:          "invalid path",
			path:          "/orders",
			expectedStatus: http.StatusBadRequest,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodGet, tt.path, nil)
			rec := httptest.NewRecorder()

			handler.ServeHTTP(rec, req)

			if rec.Code != tt.expectedStatus {
				t.Errorf("expected status %d, got %d. Body: %s", tt.expectedStatus, rec.Code, rec.Body.String())
			}
		})
	}
}

func TestHandleHealth(t *testing.T) {
	handler := handleHealth()
	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Errorf("expected status %d, got %d", http.StatusOK, rec.Code)
	}

	var resp map[string]string
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}

	if resp["status"] != "ok" {
		t.Errorf("expected status 'ok', got '%s'", resp["status"])
	}
}

// Helper to get current time for testing since we can't easily mock time.Now() without changing main logic
func timeNow() time.Time {
	return time.Now().UTC()
}
```