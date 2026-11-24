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

// Order represents the order entity stored in memory.
type Order struct {
	ID         string      `json:"id"`
	CustomerID string      `json:"customerId"`
	Items      []OrderItem `json:"items"`
	TotalCents int64       `json:"totalCents"`
	CreatedAt  time.Time   `json:"createdAt"`
}

// OrderItem represents a single line item in an order.
type OrderItem struct {
	SKU            string `json:"sku"`
	Quantity       int    `json:"quantity"`
	UnitPriceCents int    `json:"unitPriceCents"`
}

// CreateOrderRequest represents the incoming JSON payload for creating an order.
type CreateOrderRequest struct {
	CustomerID string       `json:"customerId"`
	Items      []OrderItem `json:"items"`
}

// ErrorResponse represents a JSON error response.
type ErrorResponse struct {
	Error string `json:"error"`
}

// OrderStore handles concurrent access to orders in memory.
type OrderStore struct {
	mu     sync.RWMutex
	orders map[string]Order
}

func NewOrderStore() *OrderStore {
	return &OrderStore{
		orders: make(map[string]Order),
	}
}

func (s *OrderStore) Create(order Order) {
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

// validateCreateRequest checks the incoming request body for validity.
// It returns the parsed request if valid, or an error string if not.
func validateCreateRequest(r *http.Request) (*CreateOrderRequest, error) {
	var req CreateOrderRequest
	decoder := json.NewDecoder(r.Body)
	// Spec says "Ignore unknown fields". json.Decoder ignores them by default.
	// We explicitly do NOT call DisallowUnknownFields().
	
	if err := decoder.Decode(&req); err != nil {
		return nil, fmt.Errorf("invalid JSON body: %s", err.Error())
	}

	// Validate CustomerID
	if req.CustomerID == "" {
		return nil, fmt.Errorf("customerId is required")
	}
	if len(req.CustomerID) < 1 || len(req.CustomerID) > 64 {
		return nil, fmt.Errorf("customerId must be between 1 and 64 characters")
	}
	if !utf8.ValidString(req.CustomerID) {
		return nil, fmt.Errorf("customerId must be valid UTF-8")
	}

	// Validate Items
	if len(req.Items) < 1 {
		return nil, fmt.Errorf("items is required and must have at least 1 entry")
	}
	if len(req.Items) > 50 {
		return nil, fmt.Errorf("items must have at most 50 entries")
	}

	for i, item := range req.Items {
		// Validate SKU
		if item.SKU == "" {
			return nil, fmt.Errorf("items[%d].sku is required", i)
		}
		if len(item.SKU) < 1 || len(item.SKU) > 32 {
			return nil, fmt.Errorf("items[%d].sku must be between 1 and 32 characters", i)
		}
		if !utf8.ValidString(item.SKU) {
			return nil, fmt.Errorf("items[%d].sku must be valid UTF-8", i)
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

		req, err := validateCreateRequest(r)
		if err != nil {
			writeError(w, http.StatusBadRequest, err.Error())
			return
		}

		// Generate UUID
		id := generateUUID()

		// Calculate total
		total := calculateTotal(req.Items)

		// Create order
		order := Order{
			ID:         id,
			CustomerID: req.CustomerID,
			Items:      req.Items,
			TotalCents: total,
			CreatedAt:  time.Now().UTC(),
		}

		store.Create(order)

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
		prefix := "/orders/"
		if !strings.HasPrefix(path, prefix) {
			writeError(w, http.StatusNotFound, "order not found")
			return
		}
		id := strings.TrimPrefix(path, prefix)
		if id == "" {
			writeError(w, http.StatusBadRequest, "invalid order ID")
			return
		}

		order, found := store.Get(id)
		if !found {
			writeError(w, http.StatusNotFound, "order not found")
			return
		}

		writeJSON(w, http.StatusOK, order)
	}
}

func handleHealth(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

// generateUUID generates a UUID v4.
// Format: xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx
// y is [8, 9, a, b]
func generateUUID() string {
	const hex = "0123456789abcdef"
	b := make([]byte, 36)
	
	randBytes := make([]byte, 16)
	if _, err := rand.Read(randBytes); err != nil {
		panic("failed to read random bytes")
	}

	// Byte 0-3: Random
	b[0] = hex[randBytes[0]>>4]
	b[1] = hex[randBytes[0]&0xf]
	b[2] = hex[randBytes[1]>>4]
	b[3] = hex[randBytes[1]&0xf]
	b[4] = '-'
	
	// Byte 4-5: Random
	b[5] = hex[randBytes[2]>>4]
	b[6] = hex[randBytes[2]&0xf]
	b[7] = '-'
	
	// Byte 6: Version 4 (0100)
	b[8] = '4'
	// Byte 7: Variant (10xx) -> top 2 bits are 10
	b[9] = hex[(randBytes[3]&0x3f)|0x80>>4] // This is wrong, need to mask first
	// Correct variant logic:
	// randBytes[3] & 0x3f gives 6 bits.
	// We want the top 2 bits of the nibble to be 10.
	// So we take randBytes[3] & 0x3f (0xxxxxxx) -> 0-63
	// Then we set the top 2 bits to 10? No.
	// The byte is 10xxxxxx.
	// So the byte value is 0x80 | (randBytes[3] & 0x3f).
	// Wait, the byte is split into two nibbles.
	// The byte itself is 10xxxxxx.
	// So the high nibble is 8, 9, A, or B? No.
	// The byte is 10xxxxxx. 
	// The high nibble is 10xx. The low nibble is xxxx.
	// So the high nibble is 8, 9, A, or B?
	// 1000 is 8. 1001 is 9. 1010 is A. 1011 is B.
	// So yes, the high nibble is (randBytes[3] >> 4) & 0x3 | 0x8?
	// No. The byte is 10xxxxxx.
	// The high nibble is 10xx.
	// So the high nibble is (randBytes[3] >> 4) & 0x3 | 0x8.
	// But we want the whole byte to be 10xxxxxx.
	// So the high nibble is 8, 9, A, or B.
	// The low nibble is random.
	
	// Let's do it byte by byte.
	// Byte 6 (index 6 in randBytes, which is the 7th byte) corresponds to the 3rd group of 4 hex digits?
	// UUID: 8-4-4-4-12
	// Groups:
	// 1: 4 bytes (8 hex digits)
	// 2: 2 bytes (4 hex digits)
	// 3: 2 bytes (4 hex digits) -> Version and Variant
	// 4: 2 bytes (4 hex digits)
	// 5: 6 bytes (12 hex digits)
	
	// Let's map randBytes to these groups.
	// Group 1: randBytes[0..3]
	// Group 2: randBytes[4..5]
	// Group 3: randBytes[6..7]
	// Group 4: randBytes[8..9]
	// Group 5: randBytes[10..15]
	
	// Group 1
	b[0] = hex[randBytes[0]>>4]
	b[1] = hex[randBytes[0]&0xf]
	b[2] = hex[randBytes[1]>>4]
	b[3] = hex[randBytes[1]&0xf]
	b[4] = '-'
	
	// Group 2
	b[5] = hex[randBytes[2]>>4]
	b[6] = hex[randBytes[2]&0xf]
	b[7] = '-'
	
	// Group 3
	// First byte of Group 3: Version 4
	// High nibble is 4, low nibble is random top 2 bits? No.
	// The byte is 0100xxxx.
	// So high nibble is 4. Low nibble is (randBytes[3] >> 4) & 0xf?
	// No, the byte is 0100xxxx.
	// So the byte value is 0x40 | (randBytes[3] & 0x0f).
	// High nibble is 4. Low nibble is randBytes[3] & 0x0f.
	b[8] = '4'
	b[9] = hex[randBytes[3]&0xf]
	b[10] = '-'
	
	// Second byte of Group 3: Variant 1 (10xx)
	// The byte is 10xxxxxx.
	// High nibble is 8, 9, A, or B?
	// 1000 is 8. 1001 is 9. 1010 is A. 1011 is B.
	// So the high nibble is (randBytes[4] >> 4) & 0x3 | 0x8.
	// The low nibble is randBytes[4] & 0xf.
	b[11] = hex[(randBytes[4]>>4)&0x3|0x8]
	b[12] = hex[randBytes[4]&0xf]
	b[13] = '-'
	
	// Group 4
	b[14] = hex[randBytes[5]>>4]
	b[15] = hex[randBytes[5]&0xf]
	b[16] = hex[randBytes[6]>>4]
	b[17] = hex[randBytes[6]&0xf]
	b[18] = '-'
	
	// Group 5
	b[19] = hex[randBytes[7]>>4]
	b[20] = hex[randBytes[7]&0xf]
	b[21] = hex[randBytes[8]>>4]
	b[22] = hex[randBytes[8]&0xf]
	b[23] = hex[randBytes[9]>>4]
	b[24] = hex[randBytes[9]&0xf]
	b[25] = hex[randBytes[10]>>4]
	b[26] = hex[randBytes[10]&0xf]
	b[27] = hex[randBytes[11]>>4]
	b[28] = hex[randBytes[11]&0xf]
	b[29] = hex[randBytes[12]>>4]
	b[30] = hex[randBytes[12]&0xf]
	b[31] = hex[randBytes[13]>>4]
	b[32] = hex[randBytes[13]&0xf]
	b[33] = hex[randBytes[14]>>4]
	b[34] = hex[randBytes[14]&0xf]
	b[35] = hex[randBytes[15]>>4]
	b[36] = hex[randBytes[15]&0xf]

	return string(b)
}

// loggingMiddleware logs each request to stdout in JSON format.
func loggingMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		
		// Wrap the ResponseWriter to capture status code
		wrapped := &statusResponseWriter{ResponseWriter: w, statusCode: http.StatusOK}
		
		next.ServeHTTP(wrapped, r)
		
		duration := time.Since(start).Milliseconds()
		
		logEntry := map[string]interface{}{
			"method":     r.Method,
			"path":       r.URL.Path,
			"status":     wrapped.statusCode,
			"durationMs": duration,
		}
		
		json.NewEncoder(os.Stdout).Encode(logEntry)
	})
}

// statusResponseWriter wraps http.ResponseWriter to capture the status code.
type statusResponseWriter struct {
	http.ResponseWriter
	statusCode int
}

func (w *statusResponseWriter) WriteHeader(code int) {
	w.statusCode = code
	w.ResponseWriter.WriteHeader(code)
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
		Addr:         ":" + port,
		Handler:      loggingMiddleware(mux),
		ReadTimeout:  5 * time.Second,
		WriteTimeout: 10 * time.Second,
		IdleTimeout:  30 * time.Second,
	}

	// Graceful shutdown channel
	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGTERM)

	go func() {
		log.Printf("Server starting on port %s", port)
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("Server failed: %v", err)
		}
	}()

	// Wait for signal
	<-stop
	log.Println("Shutting down server...")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if err := server.Shutdown(ctx); err != nil {
		log.Fatalf("Server forced to shutdown: %v", err)
	}

	log.Println("Server exited")
}
```