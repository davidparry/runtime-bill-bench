FILE: main_test.go
```go
package main

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestHealthEndpoint(t *testing.T) {
	// Define a simple handler for health
	healthHandler := func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeError(w, http.StatusMethodNotAllowed, "method not allowed")
			return
		}
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	}

	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	w := httptest.NewRecorder()

	logRequest(healthHandler)(w, req)

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
		id := r.URL.Path[len("/orders/"):]
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

func TestCreateOrderSuccessLogic(t *testing.T) {
	store := NewOrderStore()

	// Create a request
	reqBody := CreateOrderRequest{
		CustomerID: "c-1",
		Items:      []OrderItem{{SKU: "A-1", Quantity: 2, UnitPriceCents: 1250}},
	}

	// Validate
	errMsg := validateCreateOrderRequest(reqBody)
	if errMsg != "" {
		t.Fatalf("validation failed: %s", errMsg)
	}

	// Simulate creation
	orderID := generateUUID()
	now := time.Now().UTC()
	total := calculateTotal(reqBody.Items)

	order := Order{
		ID:         orderID,
		CustomerID: reqBody.CustomerID,
		Items:      reqBody.Items,
		TotalCents: total,
		CreatedAt:  now,
	}

	store.Set(order)

	// Verify retrieval
	retrieved, found := store.Get(orderID)
	if !found {
		t.Fatal("order not found in store after setting")
	}

	if retrieved.ID != order.ID {
		t.Errorf("expected ID %s, got %s", order.ID, retrieved.ID)
	}
	if retrieved.TotalCents != order.TotalCents {
		t.Errorf("expected total %d, got %d", order.TotalCents, retrieved.TotalCents)
	}
}
```