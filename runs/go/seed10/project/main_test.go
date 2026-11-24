package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

// TestValidationRules tests the validation logic for the CreateOrderRequest.
func TestValidationRules(t *testing.T) {
	store := NewOrderStore()
	handler := NewOrderHandler(store)

	tests := []struct {
		name       string
		body       interface{}
		wantStatus int
	}{
		{
			name:       "valid order",
			body:       CreateOrderRequest{CustomerID: "c-1", Items: []OrderItem{{SKU: "A-1", Quantity: 2, UnitPriceCents: 1250}}},
			wantStatus: http.StatusCreated,
		},
		{
			name:       "missing customerId",
			body:       CreateOrderRequest{Items: []OrderItem{{SKU: "A-1", Quantity: 2, UnitPriceCents: 1250}}},
			wantStatus: http.StatusBadRequest,
		},
		{
			name:       "customerId too long",
			body:       CreateOrderRequest{CustomerID: string(make([]byte, 65)), Items: []OrderItem{{SKU: "A-1", Quantity: 2, UnitPriceCents: 1250}}},
			wantStatus: http.StatusBadRequest,
		},
		{
			name:       "empty items array",
			body:       CreateOrderRequest{CustomerID: "c-1", Items: []OrderItem{}},
			wantStatus: http.StatusBadRequest,
		},
		{
			name:       "too many items",
			body:       CreateOrderRequest{CustomerID: "c-1", Items: make([]OrderItem, 51)},
			wantStatus: http.StatusBadRequest,
		},
		{
			name:       "invalid quantity (0)",
			body:       CreateOrderRequest{CustomerID: "c-1", Items: []OrderItem{{SKU: "A-1", Quantity: 0, UnitPriceCents: 1250}}},
			wantStatus: http.StatusBadRequest,
		},
		{
			name:       "invalid quantity (101)",
			body:       CreateOrderRequest{CustomerID: "c-1", Items: []OrderItem{{SKU: "A-1", Quantity: 101, UnitPriceCents: 1250}}},
			wantStatus: http.StatusBadRequest,
		},
		{
			name:       "invalid unitPriceCents (0)",
			body:       CreateOrderRequest{CustomerID: "c-1", Items: []OrderItem{{SKU: "A-1", Quantity: 1, UnitPriceCents: 0}}},
			wantStatus: http.StatusBadRequest,
		},
		{
			name:       "invalid unitPriceCents (1000001)",
			body:       CreateOrderRequest{CustomerID: "c-1", Items: []OrderItem{{SKU: "A-1", Quantity: 1, UnitPriceCents: 1000001}}},
			wantStatus: http.StatusBadRequest,
		},
		{
			name:       "invalid sku length (0)",
			body:       CreateOrderRequest{CustomerID: "c-1", Items: []OrderItem{{SKU: "", Quantity: 1, UnitPriceCents: 100}}},
			wantStatus: http.StatusBadRequest,
		},
		{
			name:       "invalid sku length (33)",
			body:       CreateOrderRequest{CustomerID: "c-1", Items: []OrderItem{{SKU: string(make([]byte, 33)), Quantity: 1, UnitPriceCents: 100}}},
			wantStatus: http.StatusBadRequest,
		},
		{
			name:       "unknown fields ignored",
			body:       map[string]interface{}{"customerId": "c-1", "items": []map[string]interface{}{{"sku": "A-1", "quantity": 1, "unitPriceCents": 100, "extra": "field"}}, "extraRoot": "field"},
			wantStatus: http.StatusCreated,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			bodyBytes, err := json.Marshal(tt.body)
			if err != nil {
				t.Fatalf("failed to marshal test body: %v", err)
			}

			req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewReader(bodyBytes))
			req.Header.Set("Content-Type", "application/json")
			w := httptest.NewRecorder()

			handler.HandleOrders(w, req)

			if w.Code != tt.wantStatus {
				t.Errorf("got status %d, want %d. Body: %s", w.Code, tt.wantStatus, w.Body.String())
			}
		})
	}
}

// TestNotFound tests the 404 case for GET /orders/{id}.
func TestNotFound(t *testing.T) {
	store := NewOrderStore()
	handler := NewOrderHandler(store)

	req := httptest.NewRequest(http.MethodGet, "/orders/non-existent-id", nil)
	w := httptest.NewRecorder()

	handler.HandleOrderByID(w, req)

	if w.Code != http.StatusNotFound {
		t.Errorf("got status %d, want %d", w.Code, http.StatusNotFound)
	}

	var resp ErrorResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}
	if resp.Error == "" {
		t.Error("expected error message in response body")
	}
}

// TestHealth checks the health endpoint.
func TestHealth(t *testing.T) {
	store := NewOrderStore()
	handler := NewOrderHandler(store)

	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	w := httptest.NewRecorder()

	handler.HandleHealth(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("got status %d, want %d", w.Code, http.StatusOK)
	}

	var resp map[string]string
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}
	if resp["status"] != "ok" {
		t.Errorf("got status %s, want 'ok'", resp["status"])
	}
}
