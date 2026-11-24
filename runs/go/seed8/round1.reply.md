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
	"math/big"
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

// Order represents an order in the system.
type Order struct {
	ID         string    `json:"id"`
	CustomerID string    `json:"customerId"`
	Items      []OrderItem `json:"items"`
	TotalCents *big.Int  `json:"totalCents"`
	CreatedAt  time.Time `json:"createdAt"`
}

// OrderItem represents a single item in an order.
type OrderItem struct {
	SKU            string `json:"sku"`
	Quantity       int    `json:"quantity"`
	UnitPriceCents int    `json:"unitPriceCents"`
}

// CreateOrderRequest represents the JSON body for creating an order.
type CreateOrderRequest struct {
	CustomerID string         `json:"customerId"`
	Items      []OrderItemReq `json:"items"`
}

// OrderItemReq is used for unmarshalling order items.
type OrderItemReq struct {
	SKU            string `json:"sku"`
	Quantity       int    `json:"quantity"`
	UnitPriceCents int    `json:"unitPriceCents"`
}

// ErrorResponse is the JSON body for error responses.
type ErrorResponse struct {
	Error string `json:"error"`
}

// OrderStore manages in-memory orders with concurrency safety.
type OrderStore struct {
	mu      sync.RWMutex
	orders  map[string]*Order
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
	// Return a copy to prevent external mutation of stored state
	// although for this simple service, returning the pointer is often acceptable
	// if we ensure we never modify it after creation. Here we return the pointer
	// but ensure the JSON marshaling happens on it directly.
	return order, true
}

// validateCustomerID checks the rules for customerId.
func validateCustomerID(id string) string {
	if id == "" {
		return "customerId is required"
	}
	if utf8.RuneCountInString(id) < 1 || utf8.RuneCountInString(id) > 64 {
		return "customerId must be between 1 and 64 characters"
	}
	return ""
}

// validateItems checks the rules for items.
func validateItems(items []OrderItemReq) ([]OrderItem, string) {
	if items == nil {
		return nil, "items is required"
	}
	if len(items) < 1 || len(items) > 50 {
		return nil, "items must have between 1 and 50 entries"
	}

	validItems := make([]OrderItem, 0, len(items))
	for i, item := range items {
		if item.SKU == "" {
			return nil, fmt.Sprintf("items[%d].sku is required", i)
		}
		if utf8.RuneCountInString(item.SKU) < 1 || utf8.RuneCountInString(item.SKU) > 32 {
			return nil, fmt.Sprintf("items[%d].sku must be between 1 and 32 characters", i)
		}
		if item.Quantity < 1 || item.Quantity > 100 {
			return nil, fmt.Sprintf("items[%d].quantity must be between 1 and 100", i)
		}
		if item.UnitPriceCents < 1 || item.UnitPriceCents > 1000000 {
			return nil, fmt.Sprintf("items[%d].unitPriceCents must be between 1 and 1000000", i)
		}
		validItems = append(validItems, OrderItem{
			SKU:            item.SKU,
			Quantity:       item.Quantity,
			UnitPriceCents: item.UnitPriceCents,
		})
	}
	return validItems, ""
}

// calculateTotalCents calculates the total price in cents.
func calculateTotalCents(items []OrderItem) *big.Int {
	total := big.NewInt(0)
	for _, item := range items {
		// Use Int64 for unitPriceCents as it fits in int64, but multiply carefully
		q := int64(item.Quantity)
		p := int64(item.UnitPriceCents)
		// Check for potential overflow before multiplication if needed, 
		// but max is 100 * 1,000,000 = 100,000,000 which fits in int64 easily.
		// We accumulate into a big.Int to support the requirement that totalCents
		// can reach 5,000,000,000 which also fits in int64, but the prompt explicitly
		// asks for 64-bit integer handling in the JSON output.
		// Using big.Int ensures we don't have any edge case issues and satisfies
		// the "needs a 64-bit integer" note by allowing arbitrary precision 
		// (though int64 would suffice for the max specified).
		// However, since Go's json package handles *big.Int poorly, we need to 
		// store it as *big.Int in the struct but marshal it to a number.
		// Actually, standard json marshaling does not support *big.Int.
		// We need a custom type or marshal manually.
		
		// Let's use a custom type for JSON marshaling.
	}
	return total
}

// Custom type for JSON marshaling of big.Int
type BigInt struct {
	*big.Int
}

func (b BigInt) MarshalJSON() ([]byte, error) {
	if b.Int == nil {
		return []byte("null"), nil
	}
	return []byte(b.Int.String()), nil
}

// OrderWithBigInt is a helper struct for JSON marshaling
type OrderWithBigInt struct {
	ID         string        `json:"id"`
	CustomerID string        `json:"customerId"`
	Items      []OrderItem   `json:"items"`
	TotalCents BigInt        `json:"totalCents"`
	CreatedAt  time.Time     `json:"createdAt"`
}

func handleCreateOrder(store *OrderStore) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeJSON(w, http.StatusMethodNotAllowed, ErrorResponse{Error: "Method not allowed"})
			return
		}

		var req CreateOrderRequest
		decoder := json.NewDecoder(r.Body)
		decoder.DisallowUnknownFields() // Wait, the prompt says "Ignore unknown fields".
		// json.Decoder doesn't have a simple "IgnoreUnknownFields" flag like some libs.
		// We must manually unmarshal into a map first or use a custom decoder.
		// Let's use a map to ignore unknown fields.
		
		// Re-decode into map
		var rawReq map[string]json.RawMessage
		if err := json.NewDecoder(r.Body).Decode(&rawReq); err != nil {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "Invalid JSON"})
			return
		}

		// Extract customerId
		customerIDBytes, ok := rawReq["customerId"]
		if !ok {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "customerId is required"})
			return
		}
		var customerId string
		if err := json.Unmarshal(customerIDBytes, &customerId); err != nil {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "customerId must be a string"})
			return
		}
		
		// Extract items
		itemsBytes, ok := rawReq["items"]
		if !ok {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "items is required"})
			return
		}
		var items []OrderItemReq
		if err := json.Unmarshal(itemsBytes, &items); err != nil {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "items must be an array"})
			return
		}

		// Validate
		if errMsg := validateCustomerID(customerId); errMsg != "" {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: errMsg})
			return
		}
		validItems, errMsg := validateItems(items)
		if errMsg != "" {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: errMsg})
			return
		}

		// Calculate Total
		total := big.NewInt(0)
		for _, item := range validItems {
			q := big.NewInt(int64(item.Quantity))
			p := big.NewInt(int64(item.UnitPriceCents))
			q.Mul(q, p)
			total.Add(total, q)
		}

		// Create Order
		id := uuid.New().String()
		now := time.Now().UTC()
		
		order := &Order{
			ID:         id,
			CustomerID: customerId,
			Items:      validItems,
			TotalCents: total,
			CreatedAt:  now,
		}

		store.Create(order)

		// Prepare Response
		resp := OrderWithBigInt{
			ID:         order.ID,
			CustomerID: order.CustomerID,
			Items:      order.Items,
			TotalCents: BigInt{order.TotalCents},
			CreatedAt:  order.CreatedAt,
		}

		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("Location", fmt.Sprintf("/orders/%s", id))
		w.WriteHeader(http.StatusCreated)
		json.NewEncoder(w).Encode(resp)
	}
}

func handleGetOrder(store *OrderStore) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeJSON(w, http.StatusMethodNotAllowed, ErrorResponse{Error: "Method not allowed"})
			return
		}

		id := strings.TrimPrefix(r.URL.Path, "/orders/")
		if id == "" {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "Order ID is required"})
			return
		}

		order, ok := store.Get(id)
		if !ok {
			writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "Order not found"})
			return
		}

		resp := OrderWithBigInt{
			ID:         order.ID,
			CustomerID: order.CustomerID,
			Items:      order.Items,
			TotalCents: BigInt{order.TotalCents},
			CreatedAt:  order.CreatedAt,
		}

		writeJSON(w, http.StatusOK, resp)
	}
}

func handleHealth(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeJSON(w, http.StatusMethodNotAllowed, ErrorResponse{Error: "Method not allowed"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func writeJSON(w http.ResponseWriter, status int, data interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(data)
}

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	store := NewOrderStore()

	mux := http.NewServeMux()
	mux.HandleFunc("/orders", handleCreateOrder(store))
	mux.HandleFunc("/orders/", handleGetOrder(store)) // Must be after /orders to avoid conflict
	mux.HandleFunc("/health", handleHealth)

	server := &http.Server{
		Addr:    ":" + port,
		Handler: mux,
	}

	// Graceful shutdown
	ctx, cancel := context.WithCancel(context.Background())
	go func() {
		sigChan := make(chan os.Signal, 1)
		signal.Notify(sigChan, syscall.SIGTERM)
		<-sigChan
		log.Println("SIGTERM received, shutting down...")
		cancel()
	}()

	go func() {
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("Server error: %v", err)
		}
	}()

	// Wait for cancellation
	<-ctx.Done()

	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer shutdownCancel()

	if err := server.Shutdown(shutdownCtx); err != nil {
		log.Fatalf("Server forced to shutdown: %v", err)
	}

	log.Println("Server exited")
}
```

Wait, I need to check the `uuid` package. The prompt says "no third-party modules". I cannot use `github.com/google/uuid`. I must generate a UUID v4 using the standard library.

Also, `big.Int` marshaling needs to be handled correctly.

Let's rewrite `main.go` properly.

FILE: main.go
```go
package main

import (
	"context"
	"crypto/rand"
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
)

// Order represents an order in the system.
type Order struct {
	ID         string     `json:"-"`
	CustomerID string     `json:"customerId"`
	Items      []OrderItem `json:"items"`
	TotalCents *big.Int   `json:"-"`
	CreatedAt  time.Time  `json:"createdAt"`
}

// OrderItem represents a single item in an order.
type OrderItem struct {
	SKU            string `json:"sku"`
	Quantity       int    `json:"quantity"`
	UnitPriceCents int    `json:"unitPriceCents"`
}

// OrderItemReq is used for unmarshalling order items.
type OrderItemReq struct {
	SKU            string `json:"sku"`
	Quantity       int    `json:"quantity"`
	UnitPriceCents int    `json:"unitPriceCents"`
}

// ErrorResponse is the JSON body for error responses.
type ErrorResponse struct {
	Error string `json:"error"`
}

// BigInt is a helper type to marshal big.Int to JSON as a number.
type BigInt struct {
	*big.Int
}

func (b BigInt) MarshalJSON() ([]byte, error) {
	if b.Int == nil {
		return []byte("null"), nil
	}
	return []byte(b.Int.String()), nil
}

// OrderResponse is the JSON response structure.
type OrderResponse struct {
	ID         string        `json:"id"`
	CustomerID string        `json:"customerId"`
	Items      []OrderItem   `json:"items"`
	TotalCents BigInt        `json:"totalCents"`
	CreatedAt  time.Time     `json:"createdAt"`
}

// OrderStore manages in-memory orders with concurrency safety.
type OrderStore struct {
	mu     sync.RWMutex
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
	return order, true
}

// generateUUID generates a version 4 UUID.
func generateUUID() string {
	u := make([]byte, 16)
	if _, err := rand.Read(u); err != nil {
		panic(err)
	}
	u[6] = (u[6] & 0x0f) | 0x40 // Version 4
	u[8] = (u[8] & 0x3f) | 0x80 // Variant 1
	return fmt.Sprintf("%x-%x-%x-%x-%x", u[0:4], u[4:6], u[6:8], u[8:10], u[10:16])
}

// validateCustomerID checks the rules for customerId.
func validateCustomerID(id string) string {
	if id == "" {
		return "customerId is required"
	}
	if utf8.RuneCountInString(id) < 1 || utf8.RuneCountInString(id) > 64 {
		return "customerId must be between 1 and 64 characters"
	}
	return ""
}

// validateItems checks the rules for items.
func validateItems(items []OrderItemReq) ([]OrderItem, string) {
	if items == nil {
		return nil, "items is required"
	}
	if len(items) < 1 || len(items) > 50 {
		return nil, "items must have between 1 and 50 entries"
	}

	validItems := make([]OrderItem, 0, len(items))
	for i, item := range items {
		if item.SKU == "" {
			return nil, fmt.Sprintf("items[%d].sku is required", i)
		}
		if utf8.RuneCountInString(item.SKU) < 1 || utf8.RuneCountInString(item.SKU) > 32 {
			return nil, fmt.Sprintf("items[%d].sku must be between 1 and 32 characters", i)
		}
		if item.Quantity < 1 || item.Quantity > 100 {
			return nil, fmt.Sprintf("items[%d].quantity must be between 1 and 100", i)
		}
		if item.UnitPriceCents < 1 || item.UnitPriceCents > 1000000 {
			return nil, fmt.Sprintf("items[%d].unitPriceCents must be between 1 and 1000000", i)
		}
		validItems = append(validItems, OrderItem{
			SKU:            item.SKU,
			Quantity:       item.Quantity,
			UnitPriceCents: item.UnitPriceCents,
		})
	}
	return validItems, ""
}

func handleCreateOrder(store *OrderStore) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeJSON(w, http.StatusMethodNotAllowed, ErrorResponse{Error: "Method not allowed"})
			return
		}

		var rawReq map[string]json.RawMessage
		if err := json.NewDecoder(r.Body).Decode(&rawReq); err != nil {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "Invalid JSON"})
			return
		}

		// Extract customerId
		customerIDBytes, ok := rawReq["customerId"]
		if !ok {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "customerId is required"})
			return
		}
		var customerId string
		if err := json.Unmarshal(customerIDBytes, &customerId); err != nil {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "customerId must be a string"})
			return
		}

		// Extract items
		itemsBytes, ok := rawReq["items"]
		if !ok {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "items is required"})
			return
		}
		var items []OrderItemReq
		if err := json.Unmarshal(itemsBytes, &items); err != nil {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "items must be an array"})
			return
		}

		// Validate
		if errMsg := validateCustomerID(customerId); errMsg != "" {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: errMsg})
			return
		}
		validItems, errMsg := validateItems(items)
		if errMsg != "" {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: errMsg})
			return
		}

		// Calculate Total
		total := big.NewInt(0)
		for _, item := range validItems {
			q := big.NewInt(int64(item.Quantity))
			p := big.NewInt(int64(item.UnitPriceCents))
			q.Mul(q, p)
			total.Add(total, q)
		}

		// Create Order
		id := generateUUID()
		now := time.Now().UTC()

		order := &Order{
			ID:         id,
			CustomerID: customerId,
			Items:      validItems,
			TotalCents: total,
			CreatedAt:  now,
		}

		store.Create(order)

		// Prepare Response
		resp := OrderResponse{
			ID:         order.ID,
			CustomerID: order.CustomerID,
			Items:      order.Items,
			TotalCents: BigInt{order.TotalCents},
			CreatedAt:  order.CreatedAt,
		}

		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("Location", fmt.Sprintf("/orders/%s", id))
		w.WriteHeader(http.StatusCreated)
		json.NewEncoder(w).Encode(resp)
	}
}

func handleGetOrder(store *OrderStore) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeJSON(w, http.StatusMethodNotAllowed, ErrorResponse{Error: "Method not allowed"})
			return
		}

		id := strings.TrimPrefix(r.URL.Path, "/orders/")
		if id == "" {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "Order ID is required"})
			return
		}

		order, ok := store.Get(id)
		if !ok {
			writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "Order not found"})
			return
		}

		resp := OrderResponse{
			ID:         order.ID,
			CustomerID: order.CustomerID,
			Items:      order.Items,
			TotalCents: BigInt{order.TotalCents},
			CreatedAt:  order.CreatedAt,
		}

		writeJSON(w, http.StatusOK, resp)
	}
}

func handleHealth(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeJSON(w, http.StatusMethodNotAllowed, ErrorResponse{Error: "Method not allowed"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func writeJSON(w http.ResponseWriter, status int, data interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(data)
}

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	store := NewOrderStore()

	mux := http.NewServeMux()
	mux.HandleFunc("/orders", handleCreateOrder(store))
	mux.HandleFunc("/orders/", handleGetOrder(store))
	mux.HandleFunc("/health", handleHealth)

	server := &http.Server{
		Addr:    ":" + port,
		Handler: mux,
	}

	// Graceful shutdown
	ctx, cancel := context.WithCancel(context.Background())
	go func() {
		sigChan := make(chan os.Signal, 1)
		signal.Notify(sigChan, syscall.SIGTERM)
		<-sigChan
		log.Println("SIGTERM received, shutting down...")
		cancel()
	}()

	go func() {
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("Server error: %v", err)
		}
	}()

	// Wait for cancellation
	<-ctx.Done()

	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer shutdownCancel()

	if err := server.Shutdown(shutdownCtx); err != nil {
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
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestValidateCustomerID(t *testing.T) {
	tests := []struct {
		name     string
		input    string
		expected string
	}{
		{"empty", "", "customerId is required"},
		{"too long", strings.Repeat("a", 65), "customerId must be between 1 and 64 characters"},
		{"valid", "c-1", ""},
		{"valid max length", strings.Repeat("a", 64), ""},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			errMsg := validateCustomerID(tt.input)
			if errMsg != tt.expected {
				t.Errorf("validateCustomerID(%q) = %q, want %q", tt.input, errMsg, tt.expected)
			}
		})
	}
}

func TestValidateItems(t *testing.T) {
	tests := []struct {
		name     string
		input    []OrderItemReq
		expected string
	}{
		{"nil", nil, "items is required"},
		{"empty", []OrderItemReq{}, "items must have between 1 and 50 entries"},
		{"too many", func() []OrderItemReq {
			items := make([]OrderItemReq, 51)
			for i := range items {
				items[i] = OrderItemReq{SKU: "A", Quantity: 1, UnitPriceCents: 1}
			}
			return items
		}(), "items must have between 1 and 50 entries"},
		{"missing sku", []OrderItemReq{{Quantity: 1, UnitPriceCents: 1}}, "items[0].sku is required"},
		{"invalid quantity", []OrderItemReq{{SKU: "A", Quantity: 0, UnitPriceCents: 1}}, "items[0].quantity must be between 1 and 100"},
		{"invalid price", []OrderItemReq{{SKU: "A", Quantity: 1, UnitPriceCents: 0}}, "items[0].unitPriceCents must be between 1 and 1000000"},
		{"valid", []OrderItemReq{{SKU: "A-1", Quantity: 2, UnitPriceCents: 1250}}, ""},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, errMsg := validateItems(tt.input)
			if errMsg != tt.expected {
				t.Errorf("validateItems(%v) = %q, want %q", tt.input, errMsg, tt.expected)
			}
		})
	}
}

func TestCreateOrderSuccess(t *testing.T) {
	store := NewOrderStore()
	handler := handleCreateOrder(store)

	body := `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}]}`
	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(body))
	w := httptest.NewRecorder()

	handler.ServeHTTP(w, req)

	if w.Code != http.StatusCreated {
		t.Errorf("Expected status %d, got %d", http.StatusCreated, w.Code)
	}

	resp := w.Result()
	if loc := resp.Header.Get("Location"); loc == "" {
		t.Error("Expected Location header")
	}

	var orderResp OrderResponse
	if err := json.NewDecoder(resp.Body).Decode(&orderResp); err != nil {
		t.Fatalf("Failed to decode response: %v", err)
	}

	if orderResp.CustomerID != "c-1" {
		t.Errorf("Expected customerId 'c-1', got '%s'", orderResp.CustomerID)
	}
	if len(orderResp.Items) != 1 {
		t.Errorf("Expected 1 item, got %d", len(orderResp.Items))
	}
	if orderResp.Items[0].SKU != "A-1" {
		t.Errorf("Expected SKU 'A-1', got '%s'", orderResp.Items[0].SKU)
	}
	if orderResp.TotalCents.Int.String() != "2500" {
		t.Errorf("Expected total '2500', got '%s'", orderResp.TotalCents.Int.String())
	}
}

func TestCreateOrderInvalidJSON(t *testing.T) {
	store := NewOrderStore()
	handler := handleCreateOrder(store)

	body := `{"invalid json`
	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(body))
	w := httptest.NewRecorder()

	handler.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status %d, got %d", http.StatusBadRequest, w.Code)
	}
}

func TestCreateOrderMissingCustomerID(t *testing.T) {
	store := NewOrderStore()
	handler := handleCreateOrder(store)

	body := `{"items": [{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}]}`
	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(body))
	w := httptest.NewRecorder()

	handler.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status %d, got %d", http.StatusBadRequest, w.Code)
	}
}

func TestCreateOrderMissingItems(t *testing.T) {
	store := NewOrderStore()
	handler := handleCreateOrder(store)

	body := `{"customerId": "c-1"}`
	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(body))
	w := httptest.NewRecorder()

	handler.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status %d, got %d", http.StatusBadRequest, w.Code)
	}
}

func TestCreateOrderInvalidQuantity(t *testing.T) {
	store := NewOrderStore()
	handler := handleCreateOrder(store)

	body := `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 0, "unitPriceCents": 1250}]}`
	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(body))
	w := httptest.NewRecorder()

	handler.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status %d, got %d", http.StatusBadRequest, w.Code)
	}
}

func TestGetOrderSuccess(t *testing.T) {
	store := NewOrderStore()
	createHandler := handleCreateOrder(store)
	getHandler := handleGetOrder(store)

	// Create an order first
	body := `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}]}`
	createReq := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(body))
	createW := httptest.NewRecorder()
	createHandler.ServeHTTP(createW, createReq)

	if createW.Code != http.StatusCreated {
		t.Fatalf("Failed to create order: %s", createW.Body.String())
	}

	resp := createW.Result()
	location := resp.Header.Get("Location")
	if location == "" {
		t.Fatal("Expected Location header")
	}
	
	// Extract ID from location
	id := strings.TrimPrefix(location, "/orders/")

	// Get the order
	getReq := httptest.NewRequest(http.MethodGet, "/orders/"+id, nil)
	getW := httptest.NewRecorder()
	getHandler.ServeHTTP(getW, getReq)

	if getW.Code != http.StatusOK {
		t.Errorf("Expected status %d, got %d", http.StatusOK, getW.Code)
	}

	var orderResp OrderResponse
	if err := json.NewDecoder(getW.Body).Decode(&orderResp); err != nil {
		t.Fatalf("Failed to decode response: %v", err)
	}

	if orderResp.ID != id {
		t.Errorf("Expected ID '%s', got '%s'", id, orderResp.ID)
	}
}

func TestGetOrderNotFound(t *testing.T) {
	store := NewOrderStore()
	handler := handleGetOrder(store)

	req := httptest.NewRequest(http.MethodGet, "/orders/non-existent", nil)
	w := httptest.NewRecorder()

	handler.ServeHTTP(w, req)

	if w.Code != http.StatusNotFound {
		t.Errorf("Expected status %d, got %d", http.StatusNotFound, w.Code)
	}

	var errResp ErrorResponse
	if err := json.NewDecoder(w.Body).Decode(&errResp); err != nil {
		t.Fatalf("Failed to decode error response: %v", err)
	}
	if errResp.Error != "Order not found" {
		t.Errorf("Expected error 'Order not found', got '%s'", errResp.Error)
	}
}

func TestHealth(t *testing.T) {
	handler := handleHealth

	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	w := httptest.NewRecorder()

	handler.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("Expected status %d, got %d", http.StatusOK, w.Code)
	}

	var resp map[string]string
	if err := json.NewDecoder(w.Body).Decode(&resp); err != nil {
		t.Fatalf("Failed to decode response: %v", err)
	}
	if resp["status"] != "ok" {
		t.Errorf("Expected status 'ok', got '%s'", resp["status"])
	}
}

func TestIgnoreUnknownFields(t *testing.T) {
	store := NewOrderStore()
	handler := handleCreateOrder(store)

	body := `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}], "unknownField": "value"}`
	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(body))
	w := httptest.NewRecorder()

	handler.ServeHTTP(w, req)

	if w.Code != http.StatusCreated {
		t.Errorf("Expected status %d, got %d. Body: %s", http.StatusCreated, w.Code, w.Body.String())
	}
}

func TestMaxTotalCents(t *testing.T) {
	store := NewOrderStore()
	handler := handleCreateOrder(store)

	// Construct a request that results in a large total
	// 50 items, each with quantity 100 and price 1000000
	// Total = 50 * 100 * 1000000 = 5,000,000,000
	items := make([]map[string]interface{}, 50)
	for i := range items {
		items[i] = map[string]interface{}{
			"sku":            "A",
			"quantity":       100,
			"unitPriceCents": 1000000,
		}
	}
	reqBody := map[string]interface{}{
		"customerId": "c-1",
		"items":      items,
	}
	
	jsonBody, _ := json.Marshal(reqBody)
	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBuffer(jsonBody))
	w := httptest.NewRecorder()

	handler.ServeHTTP(w, req)

	if w.Code != http.StatusCreated {
		t.Errorf("Expected status %d, got %d. Body: %s", http.StatusCreated, w.Code, w.Body.String())
	}

	var orderResp OrderResponse
	if err := json.NewDecoder(w.Body).Decode(&orderResp); err != nil {
		t.Fatalf("Failed to decode response: %v", err)
	}

	expectedTotal := "5000000000"
	if orderResp.TotalCents.Int.String() != expectedTotal {
		t.Errorf("Expected total '%s', got '%s'", expectedTotal, orderResp.TotalCents.Int.String())
	}
}
```