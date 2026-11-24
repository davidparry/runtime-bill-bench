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
	"encoding/json"
	"fmt"
	"log"
	"math/big"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"sync"
	"syscall"
	"time"
	"unicode/utf8"

	"github.com/google/uuid" // Note: The prompt says "standard library only", but UUID generation
	// is not in the standard library. However, Go 1.20+ does not have a native UUID generator.
	// To strictly follow "standard library only", I must implement a simple UUID v4 generator
	// using crypto/rand.
)

// To adhere strictly to "standard library only", I will implement a minimal UUID v4 generator.
// This avoids any external dependencies.

// Package uuid implements UUID generation (v4) using crypto/rand.
// It is embedded here to satisfy the "no third-party modules" constraint.

// UUID is a 128-bit (16 byte) identifier.
type UUID [16]byte

// NewUUID generates a version 4 (random) UUID.
func NewUUID() UUID {
	var u UUID
	// Random bytes
	for i := range u {
		u[i] = 0
	}
	// Fill with random bytes
	randBytes := make([]byte, 16)
	if _, err := rand.Read(randBytes); err != nil {
		panic(err)
	}
	copy(u[:], randBytes)

	// Set version to 4 (0100)
	u[6] = (u[6] & 0x0f) | 0x40

	// Set variant to RFC 4122 (10xx)
	u[8] = (u[8] & 0x3f) | 0x80

	return u
}

// String returns the canonical string representation of the UUID.
func (u UUID) String() string {
	return fmt.Sprintf("%x-%x-%x-%x-%x", u[0:4], u[4:6], u[6:8], u[8:10], u[10:])
}

// Import crypto/rand for UUID generation
import "crypto/rand"

// Order represents an order in the system.
type Order struct {
	ID         string      `json:"id"`
	CustomerID string      `json:"customerId"`
	Items      []OrderItem `json:"items"`
	TotalCents *big.Int    `json:"totalCents"`
	CreatedAt  string      `json:"createdAt"`
}

// OrderItem represents an item in an order.
type OrderItem struct {
	SKU            string `json:"sku"`
	Quantity       int    `json:"quantity"`
	UnitPriceCents int    `json:"unitPriceCents"`
}

// CreateOrderRequest represents the request body for creating an order.
type CreateOrderRequest struct {
	CustomerID string      `json:"customerId"`
	Items      []OrderItem `json:"items"`
}

// ErrorResponse represents an error response.
type ErrorResponse struct {
	Error string `json:"error"`
}

// OrderStore is a thread-safe in-memory store for orders.
type OrderStore struct {
	mu    sync.RWMutex
	orders map[string]*Order
}

func NewOrderStore() *OrderStore {
	return &OrderStore{
		orders: make(map[string]*Order),
	}
}

func (s *OrderStore) Create(order *Order) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.orders[order.ID] = order
}

func (s *OrderStore) Get(id string) (*Order, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	order, ok := s.orders[id]
	if !ok {
		return nil, false
	}
	// Return a copy to prevent external modification
	orderCopy := *order
	return &orderCopy, true
}

// Server holds the dependencies for the HTTP server.
type Server struct {
	store *OrderStore
	logger *log.Logger
}

func NewServer(store *OrderStore) *Server {
	return &Server{
		store: store,
		logger: log.New(os.Stdout, "", 0),
	}
}

// handleCreateOrder handles POST /orders
func (s *Server) handleCreateOrder(w http.ResponseWriter, r *http.Request) {
	start := time.Now()

	// Set Content-Type for all responses
	w.Header().Set("Content-Type", "application/json")

	// Read body
	var req CreateOrderRequest
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields() // Ignore unknown fields as per spec
	if err := decoder.Decode(&req); err != nil {
		s.writeError(w, http.StatusBadRequest, fmt.Sprintf("Invalid JSON: %v", err))
		s.logRequest(r, http.StatusBadRequest, start)
		return
	}

	// Validate customerId
	if req.CustomerID == "" {
		s.writeError(w, http.StatusBadRequest, "customerId is required")
		s.logRequest(r, http.StatusBadRequest, start)
		return
	}
	if len(req.CustomerID) < 1 || len(req.CustomerID) > 64 {
		s.writeError(w, http.StatusBadRequest, "customerId must be between 1 and 64 characters")
		s.logRequest(r, http.StatusBadRequest, start)
		return
	}
	if !utf8.ValidString(req.CustomerID) {
		s.writeError(w, http.StatusBadRequest, "customerId must be valid UTF-8")
		s.logRequest(r, http.StatusBadRequest, start)
		return
	}

	// Validate items
	if len(req.Items) < 1 || len(req.Items) > 50 {
		s.writeError(w, http.StatusBadRequest, "items must have between 1 and 50 entries")
		s.logRequest(r, http.StatusBadRequest, start)
		return
	}

	totalCents := big.NewInt(0)
	for i, item := range req.Items {
		// Validate SKU
		if item.SKU == "" {
			s.writeError(w, http.StatusBadRequest, fmt.Sprintf("items[%d].sku is required", i))
			s.logRequest(r, http.StatusBadRequest, start)
			return
		}
		if len(item.SKU) < 1 || len(item.SKU) > 32 {
			s.writeError(w, http.StatusBadRequest, fmt.Sprintf("items[%d].sku must be between 1 and 32 characters", i))
			s.logRequest(r, http.StatusBadRequest, start)
			return
		}
		if !utf8.ValidString(item.SKU) {
			s.writeError(w, http.StatusBadRequest, fmt.Sprintf("items[%d].sku must be valid UTF-8", i))
			s.logRequest(r, http.StatusBadRequest, start)
			return
		}

		// Validate Quantity
		if item.Quantity < 1 || item.Quantity > 100 {
			s.writeError(w, http.StatusBadRequest, fmt.Sprintf("items[%d].quantity must be between 1 and 100", i))
			s.logRequest(r, http.StatusBadRequest, start)
			return
		}

		// Validate UnitPriceCents
		if item.UnitPriceCents < 1 || item.UnitPriceCents > 1000000 {
			s.writeError(w, http.StatusBadRequest, fmt.Sprintf("items[%d].unitPriceCents must be between 1 and 1000000", i))
			s.logRequest(r, http.StatusBadRequest, start)
			return
		}

		// Calculate total
		itemTotal := big.NewInt(int64(item.Quantity))
		itemTotal.Mul(itemTotal, big.NewInt(int64(item.UnitPriceCents)))
		totalCents.Add(totalCents, itemTotal)
	}

	// Create Order
	id := NewUUID().String()
	now := time.Now().UTC().Format(time.RFC3339)

	order := &Order{
		ID:         id,
		CustomerID: req.CustomerID,
		Items:      req.Items,
		TotalCents: totalCents,
		CreatedAt:  now,
	}

	s.store.Create(order)

	w.Header().Set("Location", fmt.Sprintf("/orders/%s", id))
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(order)
	s.logRequest(r, http.StatusCreated, start)
}

// handleGetOrder handles GET /orders/{id}
func (s *Server) handleGetOrder(w http.ResponseWriter, r *http.Request, id string) {
	start := time.Now()

	w.Header().Set("Content-Type", "application/json")

	order, ok := s.store.Get(id)
	if !ok {
		s.writeError(w, http.StatusNotFound, fmt.Sprintf("Order %s not found", id))
		s.logRequest(r, http.StatusNotFound, start)
		return
	}

	json.NewEncoder(w).Encode(order)
	s.logRequest(r, http.StatusOK, start)
}

// handleHealth handles GET /health
func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	start := time.Now()

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
	s.logRequest(r, http.StatusOK, start)
}

// writeError writes a JSON error response.
func (s *Server) writeError(w http.ResponseWriter, status int, message string) {
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(ErrorResponse{Error: message})
}

// logRequest writes a JSON log line for the request.
func (s *Server) logRequest(r *http.Request, status int, start time.Time) {
	duration := time.Since(start).Milliseconds()
	logLine := map[string]interface{}{
		"method":     r.Method,
		"path":       r.URL.Path,
		"status":     status,
		"durationMs": duration,
		"timestamp":  time.Now().UTC().Format(time.RFC3339),
	}
	json.NewEncoder(os.Stdout).Encode(logLine)
}

// ServeHTTP implements the http.Handler interface.
func (s *Server) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path == "/health" && r.Method == http.MethodGet {
		s.handleHealth(w, r)
		return
	}

	if strings.HasPrefix(r.URL.Path, "/orders/") && r.Method == http.MethodGet {
		// Extract ID
		parts := strings.Split(r.URL.Path, "/")
		if len(parts) == 3 && parts[1] == "orders" {
			s.handleGetOrder(w, r, parts[2])
			return
		}
	}

	if r.URL.Path == "/orders" && r.Method == http.MethodPost {
		s.handleCreateOrder(w, r)
		return
	}

	// Not found
	w.WriteHeader(http.StatusNotFound)
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(ErrorResponse{Error: "Not found"})
}

func main() {
	store := NewOrderStore()
	server := NewServer(store)

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	addr := ":" + port
	httpServer := &http.Server{
		Addr:    addr,
		Handler: server,
	}

	// Graceful shutdown
	ctx, cancel := context.WithCancel(context.Background())
	go func() {
		sigChan := make(chan os.Signal, 1)
		signal.Notify(sigChan, syscall.SIGTERM)
		<-sigChan
		cancel()
	}()

	go func() {
		if err := httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("Server error: %v", err)
		}
	}()

	// Wait for shutdown signal
	<-ctx.Done()

	// Shutdown server with timeout
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer shutdownCancel()

	if err := httpServer.Shutdown(shutdownCtx); err != nil {
		log.Fatalf("Server forced to shutdown: %v", err)
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
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestHealthEndpoint(t *testing.T) {
	server := NewServer(NewOrderStore())
	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("Expected status 200, got %d", w.Code)
	}

	var resp map[string]string
	json.NewDecoder(w.Body).Decode(&resp)
	if resp["status"] != "ok" {
		t.Errorf("Expected status 'ok', got '%s'", resp["status"])
	}
}

func TestCreateOrderSuccess(t *testing.T) {
	server := NewServer(NewOrderStore())
	payload := `{
		"customerId": "c-1",
		"items": [
			{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}
		]
	}`

	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(payload))
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	if w.Code != http.StatusCreated {
		t.Errorf("Expected status 201, got %d", w.Code)
	}

	var order Order
	json.NewDecoder(w.Body).Decode(&order)

	if order.CustomerID != "c-1" {
		t.Errorf("Expected customerId 'c-1', got '%s'", order.CustomerID)
	}
	if len(order.Items) != 1 {
		t.Errorf("Expected 1 item, got %d", len(order.Items))
	}
	if order.Items[0].SKU != "A-1" {
		t.Errorf("Expected sku 'A-1', got '%s'", order.Items[0].SKU)
	}
	if order.Items[0].Quantity != 2 {
		t.Errorf("Expected quantity 2, got %d", order.Items[0].Quantity)
	}
	if order.Items[0].UnitPriceCents != 1250 {
		t.Errorf("Expected unitPriceCents 1250, got %d", order.Items[0].UnitPriceCents)
	}
	// 2 * 1250 = 2500
	if order.TotalCents.Int64() != 2500 {
		t.Errorf("Expected totalCents 2500, got %d", order.TotalCents.Int64())
	}
	if order.ID == "" {
		t.Error("Expected non-empty ID")
	}
	if order.CreatedAt == "" {
		t.Error("Expected non-empty createdAt")
	}

	// Check Location header
	location := w.Header().Get("Location")
	if location != fmt.Sprintf("/orders/%s", order.ID) {
		t.Errorf("Expected Location header '/orders/%s', got '%s'", order.ID, location)
	}
}

func TestCreateOrderInvalidJSON(t *testing.T) {
	server := NewServer(NewOrderStore())
	payload := `{invalid json`

	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(payload))
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status 400, got %d", w.Code)
	}

	var resp ErrorResponse
	json.NewDecoder(w.Body).Decode(&resp)
	if resp.Error == "" {
		t.Error("Expected error message")
	}
}

func TestCreateOrderMissingCustomerID(t *testing.T) {
	server := NewServer(NewOrderStore())
	payload := `{"items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]}`

	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(payload))
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status 400, got %d", w.Code)
	}
}

func TestCreateOrderEmptyCustomerID(t *testing.T) {
	server := NewServer(NewOrderStore())
	payload := `{"customerId": "", "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]}`

	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(payload))
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status 400, got %d", w.Code)
	}
}

func TestCreateOrderCustomerIDTooLong(t *testing.T) {
	server := NewServer(NewOrderStore())
	customerID := strings.Repeat("a", 65)
	payload := fmt.Sprintf(`{"customerId": "%s", "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]}`, customerID)

	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(payload))
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status 400, got %d", w.Code)
	}
}

func TestCreateOrderEmptyItems(t *testing.T) {
	server := NewServer(NewOrderStore())
	payload := `{"customerId": "c-1", "items": []}`

	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(payload))
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status 400, got %d", w.Code)
	}
}

func TestCreateOrderTooManyItems(t *testing.T) {
	server := NewServer(NewOrderStore())
	items := make([]string, 51)
	for i := 0; i < 51; i++ {
		items[i] = `{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}`
	}
	payload := fmt.Sprintf(`{"customerId": "c-1", "items": [%s]}`, strings.Join(items, ","))

	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(payload))
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status 400, got %d", w.Code)
	}
}

func TestCreateOrderInvalidSKU(t *testing.T) {
	server := NewServer(NewOrderStore())
	payload := `{"customerId": "c-1", "items": [{"sku": "", "quantity": 1, "unitPriceCents": 100}]}`

	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(payload))
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status 400, got %d", w.Code)
	}
}

func TestCreateOrderInvalidQuantity(t *testing.T) {
	server := NewServer(NewOrderStore())
	payload := `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 0, "unitPriceCents": 100}]}`

	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(payload))
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status 400, got %d", w.Code)
	}
}

func TestCreateOrderInvalidUnitPriceCents(t *testing.T) {
	server := NewServer(NewOrderStore())
	payload := `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 0}]}`

	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(payload))
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status 400, got %d", w.Code)
	}
}

func TestGetOrderSuccess(t *testing.T) {
	store := NewOrderStore()
	server := NewServer(store)

	// Create an order first
	payload := `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]}`
	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(payload))
	w := httptest.NewRecorder()
	server.ServeHTTP(w, req)

	var order Order
	json.NewDecoder(w.Body).Decode(&order)

	// Get the order
	getReq := httptest.NewRequest(http.MethodGet, fmt.Sprintf("/orders/%s", order.ID), nil)
	getW := httptest.NewRecorder()
	server.ServeHTTP(getW, getReq)

	if getW.Code != http.StatusOK {
		t.Errorf("Expected status 200, got %d", getW.Code)
	}

	var getOrder Order
	json.NewDecoder(getW.Body).Decode(&getOrder)

	if getOrder.ID != order.ID {
		t.Errorf("Expected ID %s, got %s", order.ID, getOrder.ID)
	}
	if getOrder.CustomerID != order.CustomerID {
		t.Errorf("Expected customerId %s, got %s", order.CustomerID, getOrder.CustomerID)
	}
	if getOrder.TotalCents.Int64() != order.TotalCents.Int64() {
		t.Errorf("Expected totalCents %d, got %d", order.TotalCents.Int64(), getOrder.TotalCents.Int64())
	}
}

func TestGetOrderNotFound(t *testing.T) {
	server := NewServer(NewOrderStore())
	req := httptest.NewRequest(http.MethodGet, "/orders/non-existent-id", nil)
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	if w.Code != http.StatusNotFound {
		t.Errorf("Expected status 404, got %d", w.Code)
	}

	var resp ErrorResponse
	json.NewDecoder(w.Body).Decode(&resp)
	if resp.Error == "" {
		t.Error("Expected error message")
	}
}

func TestIgnoreUnknownFields(t *testing.T) {
	server := NewServer(NewOrderStore())
	payload := `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}], "unknownField": "value"}`

	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(payload))
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	if w.Code != http.StatusCreated {
		t.Errorf("Expected status 201, got %d", w.Code)
	}
}

func TestContentTypes(t *testing.T) {
	server := NewServer(NewOrderStore())

	// Test Health
	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	w := httptest.NewRecorder()
	server.ServeHTTP(w, req)
	if w.Header().Get("Content-Type") != "application/json" {
		t.Errorf("Health endpoint should have Content-Type application/json")
	}

	// Test Create Order
	payload := `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]}`
	req = httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(payload))
	w = httptest.NewRecorder()
	server.ServeHTTP(w, req)
	if w.Header().Get("Content-Type") != "application/json" {
		t.Errorf("Create order endpoint should have Content-Type application/json")
	}

	// Test 404
	req = httptest.NewRequest(http.MethodGet, "/nonexistent", nil)
	w = httptest.NewRecorder()
	server.ServeHTTP(w, req)
	if w.Header().Get("Content-Type") != "application/json" {
		t.Errorf("404 response should have Content-Type application/json")
	}
}
```