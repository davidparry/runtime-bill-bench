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
