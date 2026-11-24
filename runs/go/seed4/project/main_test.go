package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestValidateOrderInput(t *testing.T) {
	tests := []struct {
		name        string
		customerID  string
		items       []Item
		expectError bool
		errorMsg    string
	}{
		{
			name:        "valid order",
			customerID:  "c-1",
			items:       []Item{{SKU: "A-1", Quantity: 2, UnitPriceCents: 1250}},
			expectError: false,
		},
		{
			name:        "customerId too short",
			customerID:  "",
			items:       []Item{{SKU: "A-1", Quantity: 2, UnitPriceCents: 1250}},
			expectError: true,
			errorMsg:    "customerId must be between 1 and 64 characters",
		},
		{
			name:        "customerId too long",
			customerID:  strings.Repeat("a", 65),
			items:       []Item{{SKU: "A-1", Quantity: 2, UnitPriceCents: 1250}},
			expectError: true,
			errorMsg:    "customerId must be between 1 and 64 characters",
		},
		{
			name:        "empty items",
			customerID:  "c-1",
			items:       []Item{},
			expectError: true,
			errorMsg:    "items must be between 1 and 50 entries",
		},
		{
			name:        "too many items",
			customerID:  "c-1",
			items:       make([]Item, 51),
			expectError: true,
			errorMsg:    "items must be between 1 and 50 entries",
		},
		{
			name:        "sku too short",
			customerID:  "c-1",
			items:       []Item{{SKU: "", Quantity: 2, UnitPriceCents: 1250}},
			expectError: true,
			errorMsg:    "item[0].sku must be between 1 and 32 characters",
		},
		{
			name:        "sku too long",
			customerID:  "c-1",
			items:       []Item{{SKU: strings.Repeat("a", 33), Quantity: 2, UnitPriceCents: 1250}},
			expectError: true,
			errorMsg:    "item[0].sku must be between 1 and 32 characters",
		},
		{
			name:        "quantity too low",
			customerID:  "c-1",
			items:       []Item{{SKU: "A-1", Quantity: 0, UnitPriceCents: 1250}},
			expectError: true,
			errorMsg:    "item[0].quantity must be between 1 and 100",
		},
		{
			name:        "quantity too high",
			customerID:  "c-1",
			items:       []Item{{SKU: "A-1", Quantity: 101, UnitPriceCents: 1250}},
			expectError: true,
			errorMsg:    "item[0].quantity must be between 1 and 100",
		},
		{
			name:        "unitPriceCents too low",
			customerID:  "c-1",
			items:       []Item{{SKU: "A-1", Quantity: 2, UnitPriceCents: 0}},
			expectError: true,
			errorMsg:    "item[0].unitPriceCents must be between 1 and 1000000",
		},
		{
			name:        "unitPriceCents too high",
			customerID:  "c-1",
			items:       []Item{{SKU: "A-1", Quantity: 2, UnitPriceCents: 1000001}},
			expectError: true,
			errorMsg:    "item[0].unitPriceCents must be between 1 and 1000000",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := validateOrderInput(tt.customerID, tt.items)
			if tt.expectError {
				if err == nil {
					t.Errorf("expected error but got nil")
				} else if err.Error() != tt.errorMsg {
					t.Errorf("expected error message '%s' but got '%s'", tt.errorMsg, err.Error())
				}
			} else {
				if err != nil {
					t.Errorf("expected no error but got '%s'", err.Error())
				}
			}
		})
	}
}

func TestGetOrder404(t *testing.T) {
	store := NewStore()
	handler := handleGetOrder(store)

	req := httptest.NewRequest(http.MethodGet, "/orders/non-existent-id", nil)
	w := httptest.NewRecorder()

	handler.ServeHTTP(w, req)

	if w.Code != http.StatusNotFound {
		t.Errorf("expected status 404, got %d", w.Code)
	}

	var response map[string]string
	if err := json.Unmarshal(w.Body.Bytes(), &response); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}

	if response["error"] != "Order not found" {
		t.Errorf("expected error message 'Order not found', got '%s'", response["error"])
	}
}

func TestCreateOrderSuccess(t *testing.T) {
	store := NewStore()
	handler := handleCreateOrder(store)

	body := `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}]}`
	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	handler.ServeHTTP(w, req)

	if w.Code != http.StatusCreated {
		t.Errorf("expected status 201, got %d", w.Code)
	}

	location := w.Header().Get("Location")
	if location == "" {
		t.Error("expected Location header")
	}

	var response Order
	if err := json.Unmarshal(w.Body.Bytes(), &response); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}

	if response.ID == "" {
		t.Error("expected non-empty ID")
	}
	if response.CustomerID != "c-1" {
		t.Errorf("expected customerId 'c-1', got '%s'", response.CustomerID)
	}
	if len(response.Items) != 1 {
		t.Errorf("expected 1 item, got %d", len(response.Items))
	}
	if response.TotalCents != 2500 {
		t.Errorf("expected totalCents 2500, got %d", response.TotalCents)
	}
}

func TestCreateOrderInvalidJSON(t *testing.T) {
	store := NewStore()
	handler := handleCreateOrder(store)

	body := `{"invalid json`
	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	handler.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected status 400, got %d", w.Code)
	}
}

func TestCreateOrderMissingFields(t *testing.T) {
	store := NewStore()
	handler := handleCreateOrder(store)

	tests := []struct {
		name string
		body string
	}{
		{
			name: "missing customerId",
			body: `{"items": [{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}]}`,
		},
		{
			name: "missing items",
			body: `{"customerId": "c-1"}`,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(tt.body))
			req.Header.Set("Content-Type", "application/json")
			w := httptest.NewRecorder()

			handler.ServeHTTP(w, req)

			if w.Code != http.StatusBadRequest {
				t.Errorf("expected status 400, got %d", w.Code)
			}
		})
	}
}

func TestHealthEndpoint(t *testing.T) {
	handler := handleHealth()

	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	w := httptest.NewRecorder()

	handler.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected status 200, got %d", w.Code)
	}

	var response map[string]string
	if err := json.Unmarshal(w.Body.Bytes(), &response); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}

	if response["status"] != "ok" {
		t.Errorf("expected status 'ok', got '%s'", response["status"])
	}
}
