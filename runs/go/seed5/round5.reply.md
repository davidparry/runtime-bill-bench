FILE: main.go
```go
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"math/rand"
	"net/http"
	"os"
	"os/signal"
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
			"method":     r.Method,
			"path":       r.URL.Path,
			"status":     wrappedWriter.statusCode,
			"durationMs": duration,
			"timestamp":  time.Now().UTC().Format(time.RFC3339),
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

		// Read body first to allow manual parsing if needed, but here we use a custom decoder
		body, err := io.ReadAll(r.Body)
		if err != nil {
			writeError(w, http.StatusBadRequest, fmt.Sprintf("failed to read body: %s", err.Error()))
			return
		}

		// Use a map to unmarshal first to ignore unknown fields
		var rawReq map[string]interface{}
		if err := json.Unmarshal(body, &rawReq); err != nil {
			writeError(w, http.StatusBadRequest, fmt.Sprintf("invalid JSON: %s", err.Error()))
			return
		}

		// Validate customerId
		customerIDRaw, ok := rawReq["customerId"]
		if !ok {
			writeError(w, http.StatusBadRequest, "customerId is required")
			return
		}
		customerID, ok := customerIDRaw.(string)
		if !ok {
			writeError(w, http.StatusBadRequest, "customerId must be a string")
			return
		}
		if customerID == "" {
			writeError(w, http.StatusBadRequest, "customerId is required")
			return
		}
		if len(customerID) < 1 || len(customerID) > 64 {
			writeError(w, http.StatusBadRequest, "customerId must be between 1 and 64 characters")
			return
		}
		if !utf8.ValidString(customerID) {
			writeError(w, http.StatusBadRequest, "customerId must be valid UTF-8")
			return
		}

		// Validate items
		itemsRaw, ok := rawReq["items"]
		if !ok {
			writeError(w, http.StatusBadRequest, "items is required")
			return
		}
		itemsSlice, ok := itemsRaw.([]interface{})
		if !ok {
			writeError(w, http.StatusBadRequest, "items must be an array")
			return
		}
		if len(itemsSlice) < 1 {
			writeError(w, http.StatusBadRequest, "items is required and must have at least 1 entry")
			return
		}
		if len(itemsSlice) > 50 {
			writeError(w, http.StatusBadRequest, "items must have at most 50 entries")
			return
		}

		var items []OrderItem
		for i, itemRaw := range itemsSlice {
			itemMap, ok := itemRaw.(map[string]interface{})
			if !ok {
				writeError(w, http.StatusBadRequest, fmt.Sprintf("items[%d] must be an object", i))
				return
			}

			var item OrderItem

			// Validate SKU
			skuRaw, ok := itemMap["sku"]
			if !ok {
				writeError(w, http.StatusBadRequest, fmt.Sprintf("items[%d].sku is required", i))
				return
			}
			sku, ok := skuRaw.(string)
			if !ok {
				writeError(w, http.StatusBadRequest, fmt.Sprintf("items[%d].sku must be a string", i))
				return
			}
			if sku == "" {
				writeError(w, http.StatusBadRequest, fmt.Sprintf("items[%d].sku is required", i))
				return
			}
			if len(sku) < 1 || len(sku) > 32 {
				writeError(w, http.StatusBadRequest, fmt.Sprintf("items[%d].sku must be between 1 and 32 characters", i))
				return
			}
			if !utf8.ValidString(sku) {
				writeError(w, http.StatusBadRequest, fmt.Sprintf("items[%d].sku must be valid UTF-8", i))
				return
			}
			item.SKU = sku

			// Validate Quantity
			qtyRaw, ok := itemMap["quantity"]
			if !ok {
				writeError(w, http.StatusBadRequest, fmt.Sprintf("items[%d].quantity is required", i))
				return
			}
			qtyFloat, ok := qtyRaw.(float64)
			if !ok {
				writeError(w, http.StatusBadRequest, fmt.Sprintf("items[%d].quantity must be an integer", i))
				return
			}
			quantity := int(qtyFloat)
			if float64(quantity) != qtyFloat {
				writeError(w, http.StatusBadRequest, fmt.Sprintf("items[%d].quantity must be an integer", i))
				return
			}
			if quantity < 1 || quantity > 100 {
				writeError(w, http.StatusBadRequest, fmt.Sprintf("items[%d].quantity must be between 1 and 100", i))
				return
			}
			item.Quantity = quantity

			// Validate UnitPriceCents
			upcRaw, ok := itemMap["unitPriceCents"]
			if !ok {
				writeError(w, http.StatusBadRequest, fmt.Sprintf("items[%d].unitPriceCents is required", i))
				return
			}
			upcFloat, ok := upcRaw.(float64)
			if !ok {
				writeError(w, http.StatusBadRequest, fmt.Sprintf("items[%d].unitPriceCents must be an integer", i))
				return
			}
			unitPriceCents := int(upcFloat)
			if float64(unitPriceCents) != upcFloat {
				writeError(w, http.StatusBadRequest, fmt.Sprintf("items[%d].unitPriceCents must be an integer", i))
				return
			}
			if unitPriceCents < 1 || unitPriceCents > 1000000 {
				writeError(w, http.StatusBadRequest, fmt.Sprintf("items[%d].unitPriceCents must be between 1 and 1000000", i))
				return
			}
			item.UnitPriceCents = unitPriceCents

			items = append(items, item)
		}

		req := CreateOrderRequest{
			CustomerID: customerID,
			Items:      items,
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
		id := r.URL.Path[len("/orders/"):]
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