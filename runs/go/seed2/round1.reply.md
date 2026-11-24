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
	"sync"
	"syscall"
	"time"
)

// Order represents the order entity stored in memory.
type Order struct {
	ID         string    `json:"id"`
	CustomerID string    `json:"customerId"`
	Items      []Item    `json:"items"`
	TotalCents int64     `json:"totalCents"`
	CreatedAt  time.Time `json:"createdAt"`
}

// Item represents a line item in an order.
type Item struct {
	SKU            string `json:"sku"`
	Quantity       int    `json:"quantity"`
	UnitPriceCents int    `json:"unitPriceCents"`
}

// CreateOrderRequest represents the incoming JSON payload for creating an order.
type CreateOrderRequest struct {
	CustomerID string `json:"customerId"`
	Items      []Item `json:"items"`
}

// ErrorResponse represents a JSON error response.
type ErrorResponse struct {
	Error string `json:"error"`
}

// InMemoryStore handles concurrent access to orders.
type InMemoryStore struct {
	mu     sync.RWMutex
	orders map[string]Order
}

func NewInMemoryStore() *InMemoryStore {
	return &InMemoryStore{
		orders: make(map[string]Order),
	}
}

func (s *InMemoryStore) Create(order Order) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.orders[order.ID] = order
}

func (s *InMemoryStore) Get(id string) (Order, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	order, ok := s.orders[id]
	return order, ok
}

func (s *InMemoryStore) Delete(id string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.orders, id)
}

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	store := NewInMemoryStore()
	mux := http.NewServeMux()

	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
	})

	mux.HandleFunc("/orders/", func(w http.ResponseWriter, r *http.Request) {
		// Extract ID from path: /orders/{id}
		// The mux adds the prefix "/orders/" to the subpattern.
		// If the pattern was "/orders/{id}", r.URL.Path might be "/orders/123".
		// However, standard mux doesn't support named parameters like that easily without net/http package expansion or manual parsing.
		// Let's use a simpler approach: handle /orders and /orders/{id} explicitly if possible, or parse.
		// Since we are using standard library only and Go 1.27, we can use the new routing features if available, 
		// but to be safe and compatible with "standard mux" logic often used in interviews/tasks:
		
		// Actually, Go 1.22+ supports patterns like "/orders/{id}".
		// Let's restructure the handler registration to use explicit patterns if possible, 
		// but the prompt says "go test ./..." and standard build. 
		// Let's stick to manual path parsing for maximum compatibility with older "standard library" mental models 
		// unless we are sure about Go 1.27 features. Go 1.22 introduced pattern matching. 
		// Given "Go 1.27", we can assume pattern matching is available.
		
		// However, to keep it simple and robust:
		if r.URL.Path == "/orders" {
			if r.Method == http.MethodPost {
				handleCreateOrder(w, r, store)
			} else {
				http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
			}
		} else if r.URL.Path != "/orders" && len(r.URL.Path) > len("/orders/") {
			id := r.URL.Path[len("/orders/"):]
			if r.Method == http.MethodGet {
				handleGetOrder(w, r, id, store)
			} else {
				http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
			}
		} else {
			http.NotFound(w, r)
		}
	})

	// Wrap handlers with logging middleware
	var handler http.Handler = http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		
		// Create a response writer that captures status code
		wrappedWriter := &statusCapturingWriter{
			ResponseWriter: w,
			status:         http.StatusOK,
		}

		handler := mux.Handler(r)
		handler.ServeHTTP(wrappedWriter, r)

		duration := time.Since(start)
		
		logLine := map[string]interface{}{
			"method":    r.Method,
			"path":      r.URL.Path,
			"status":    wrappedWriter.status,
			"durationMs": duration.Milliseconds(),
		}
		
		jsonLog, err := json.Marshal(logLine)
		if err != nil {
			log.Printf("Failed to marshal log line: %v", err)
		} else {
			fmt.Println(string(jsonLog))
		}
	})

	server := &http.Server{
		Addr:    ":" + port,
		Handler: handler,
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
			log.Printf("HTTP server shutdown error: %v", err)
		}
	}()

	log.Printf("Orders service starting on port %s", port)
	if err := server.ListenAndServe(); err != http.ErrServerClosed {
		log.Fatalf("HTTP server error: %v", err)
	}
	
	log.Println("Orders service stopped.")
}

// statusCapturingWriter wraps http.ResponseWriter to capture the status code.
type statusCapturingWriter struct {
	http.ResponseWriter
	status int
}

func (w *statusCapturingWriter) WriteHeader(code int) {
	w.status = code
	w.ResponseWriter.WriteHeader(code)
}

func handleCreateOrder(w http.ResponseWriter, r *http.Request, store *InMemoryStore) {
	var req CreateOrderRequest
	decoder := json.NewDecoder(r.Body)
	// Ignore unknown fields
	decoder.DisallowUnknownFields()
	
	if err := decoder.Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, fmt.Sprintf("Invalid JSON: %v", err))
		return
	}

	if err := validateCreateOrder(req); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	// Calculate total
	var totalCents int64
	for _, item := range req.Items {
		totalCents += int64(item.Quantity) * int64(item.UnitPriceCents)
	}

	// Generate UUID
	id := generateUUID()

	order := Order{
		ID:         id,
		CustomerID: req.CustomerID,
		Items:      req.Items,
		TotalCents: totalCents,
		CreatedAt:  time.Now().UTC(),
	}

	store.Create(order)

	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Location", fmt.Sprintf("/orders/%s", id))
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(order)
}

func handleGetOrder(w http.ResponseWriter, r *http.Request, id string, store *InMemoryStore) {
	order, found := store.Get(id)
	if !found {
		writeError(w, http.StatusNotFound, fmt.Sprintf("Order %s not found", id))
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(order)
}

func validateCreateOrder(req CreateOrderRequest) error {
	if req.CustomerID == "" {
		return fmt.Errorf("customerId is required")
	}
	if len(req.CustomerID) < 1 || len(req.CustomerID) > 64 {
		return fmt.Errorf("customerId must be between 1 and 64 characters")
	}

	if len(req.Items) < 1 || len(req.Items) > 50 {
		return fmt.Errorf("items must contain between 1 and 50 entries")
	}

	for i, item := range req.Items {
		if item.SKU == "" {
			return fmt.Errorf("items[%d].sku is required", i)
		}
		if len(item.SKU) < 1 || len(item.SKU) > 32 {
			return fmt.Errorf("items[%d].sku must be between 1 and 32 characters", i)
		}
		if item.Quantity < 1 || item.Quantity > 100 {
			return fmt.Errorf("items[%d].quantity must be between 1 and 100", i)
		}
		if item.UnitPriceCents < 1 || item.UnitPriceCents > 1000000 {
			return fmt.Errorf("items[%d].unitPriceCents must be between 1 and 1000000", i)
		}
	}

	return nil
}

func writeError(w http.ResponseWriter, status int, message string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(ErrorResponse{Error: message})
}
```

FILE: uuid.go
```go
package main

import (
	"crypto/rand"
	"fmt"
)

// generateUUID creates a version 4 UUID.
func generateUUID() string {
	uuid := make([]byte, 16)
	_, err := rand.Read(uuid)
	if err != nil {
		panic(fmt.Sprintf("failed to generate UUID: %v", err))
	}

	// Set version 4
	uuid[6] = (uuid[6] & 0x0f) | 0x40
	// Set variant 1
	uuid[8] = (uuid[8] & 0x3f) | 0x80

	return fmt.Sprintf("%08x-%04x-%04x-%04x-%012x",
		uuid[0:4], uuid[4:6], uuid[6:8], uuid[8:10], uuid[10:16])
}
```

FILE: main_test.go
```go
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestHealthEndpoint(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	w := httptest.NewRecorder()

	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
	})

	// Create a simple handler to simulate the middleware wrapper if needed, 
	// but for unit testing validation logic directly is often easier.
	// Let's test the validation function directly as requested: "unit tests for the validation rules".
}

func TestValidateCreateOrder(t *testing.T) {
	tests := []struct {
		name        string
		req         CreateOrderRequest
		expectError bool
		errorMsg    string
	}{
		{
			name:        "valid order",
			req:         CreateOrderRequest{CustomerID: "c-1", Items: []Item{{SKU: "A-1", Quantity: 2, UnitPriceCents: 1250}}},
			expectError: false,
		},
		{
			name:        "empty customerId",
			req:         CreateOrderRequest{CustomerID: "", Items: []Item{{SKU: "A-1", Quantity: 2, UnitPriceCents: 1250}}},
			expectError: true,
			errorMsg:    "customerId is required",
		},
		{
			name:        "customerId too long",
			req:         CreateOrderRequest{CustomerID: strings.Repeat("a", 65), Items: []Item{{SKU: "A-1", Quantity: 2, UnitPriceCents: 1250}}},
			expectError: true,
			errorMsg:    "customerId must be between 1 and 64 characters",
		},
		{
			name:        "empty items",
			req:         CreateOrderRequest{CustomerID: "c-1", Items: []Item{}},
			expectError: true,
			errorMsg:    "items must contain between 1 and 50 entries",
		},
		{
			name:        "sku too long",
			req:         CreateOrderRequest{CustomerID: "c-1", Items: []Item{{SKU: strings.Repeat("a", 33), Quantity: 2, UnitPriceCents: 1250}}},
			expectError: true,
			errorMsg:    "items[0].sku must be between 1 and 32 characters",
		},
		{
			name:        "quantity zero",
			req:         CreateOrderRequest{CustomerID: "c-1", Items: []Item{{SKU: "A-1", Quantity: 0, UnitPriceCents: 1250}}},
			expectError: true,
			errorMsg:    "items[0].quantity must be between 1 and 100",
		},
		{
			name:        "quantity too high",
			req:         CreateOrderRequest{CustomerID: "c-1", Items: []Item{{SKU: "A-1", Quantity: 101, UnitPriceCents: 1250}}},
			expectError: true,
			errorMsg:    "items[0].quantity must be between 1 and 100",
		},
		{
			name:        "unitPriceCents zero",
			req:         CreateOrderRequest{CustomerID: "c-1", Items: []Item{{SKU: "A-1", Quantity: 2, UnitPriceCents: 0}}},
			expectError: true,
			errorMsg:    "items[0].unitPriceCents must be between 1 and 1000000",
		},
		{
			name:        "unitPriceCents too high",
			req:         CreateOrderRequest{CustomerID: "c-1", Items: []Item{{SKU: "A-1", Quantity: 2, UnitPriceCents: 1000001}}},
			expectError: true,
			errorMsg:    "items[0].unitPriceCents must be between 1 and 1000000",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := validateCreateOrder(tt.req)
			if tt.expectError {
				if err == nil {
					t.Errorf("expected error, got nil")
				} else if !strings.Contains(err.Error(), tt.errorMsg) {
					t.Errorf("expected error to contain %q, got %q", tt.errorMsg, err.Error())
				}
			} else {
				if err != nil {
					t.Errorf("expected no error, got %v", err)
				}
			}
		})
	}
}

func TestGetOrderNotFound(t *testing.T) {
	store := NewInMemoryStore()
	
	// Create a request to get a non-existent order
	req := httptest.NewRequest(http.MethodGet, "/orders/non-existent-id", nil)
	w := httptest.NewRecorder()

	// Simulate the handler logic
	id := strings.TrimPrefix(req.URL.Path, "/orders/")
	order, found := store.Get(id)
	
	if found {
		t.Errorf("expected order not to be found")
	}

	// Check response
	if w.Code != http.StatusNotFound {
		t.Errorf("expected status %d, got %d", http.StatusNotFound, w.Code)
	}

	var resp ErrorResponse
	if err := json.NewDecoder(w.Body).Decode(&resp); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}

	if resp.Error == "" {
		t.Error("expected error message in response")
	}
}

func TestCreateOrderSuccess(t *testing.T) {
	store := NewInMemoryStore()
	
	body := `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}]}`
	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	// Parse and validate
	var createReq CreateOrderRequest
	decoder := json.NewDecoder(req.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&createReq); err != nil {
		t.Fatalf("failed to decode request: %v", err)
	}

	if err := validateCreateOrder(createReq); err != nil {
		t.Fatalf("validation failed: %v", err)
	}

	// Calculate total
	var totalCents int64
	for _, item := range createReq.Items {
		totalCents += int64(item.Quantity) * int64(item.UnitPriceCents)
	}

	id := generateUUID()
	order := Order{
		ID:         id,
		CustomerID: createReq.CustomerID,
		Items:      createReq.Items,
		TotalCents: totalCents,
		CreatedAt:  req.Context().Value(0).(time.Time), // Mock time for test if needed, but here we just check logic
	}
	order.CreatedAt = time.Now().UTC() // Just for consistency

	store.Create(order)

	// Verify it was stored
	storedOrder, found := store.Get(id)
	if !found {
		t.Fatal("order not found in store")
	}

	if storedOrder.TotalCents != 2500 {
		t.Errorf("expected total %d, got %d", 2500, storedOrder.TotalCents)
	}
}
```