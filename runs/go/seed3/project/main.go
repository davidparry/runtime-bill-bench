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

// UUID is a 128-bit (16 byte) identifier.
type UUID [16]byte

// NewUUID generates a version 4 (random) UUID.
func NewUUID() UUID {
	var u UUID
	// Random bytes
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
	// Return a copy to prevent external modification
	orderCopy := *order
	return &orderCopy, true
}

// Server holds the dependencies for the HTTP server.
type Server struct {
	store  *OrderStore
	logger *log.Logger
}

func NewServer(store *OrderStore) *Server {
	return &Server{
		store:  store,
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
	// Do not DisallowUnknownFields to allow unknown fields as per spec
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
