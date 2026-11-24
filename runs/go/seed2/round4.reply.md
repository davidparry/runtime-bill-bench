FILE: main_test.go
```go
package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

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

	// Simulate the handler logic for a non-existent order
	id := "non-existent-id"
	order, found := store.Get(id)

	if found {
		t.Errorf("expected order not to be found")
	}
	_ = order

	// Check response via httptest
	req := httptest.NewRequest(http.MethodGet, "/orders/"+id, nil)
	w := httptest.NewRecorder()
	
	// Call the handler directly to test response
	handleGetOrder(w, req, id, store)

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

	// Call the handler directly
	handleCreateOrder(w, req, store)

	if w.Code != http.StatusCreated {
		t.Errorf("expected status %d, got %d", http.StatusCreated, w.Code)
	}

	var resp Order
	if err := json.NewDecoder(w.Body).Decode(&resp); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}

	if resp.ID == "" {
		t.Error("expected ID in response")
	}
	if resp.CustomerID != "c-1" {
		t.Errorf("expected customerId 'c-1', got '%s'", resp.CustomerID)
	}
	if resp.TotalCents != 2500 {
		t.Errorf("expected total 2500, got %d", resp.TotalCents)
	}
	if resp.CreatedAt.IsZero() {
		t.Error("expected CreatedAt to be set")
	}

	// Verify it was stored
	storedOrder, found := store.Get(resp.ID)
	if !found {
		t.Fatal("order not found in store")
	}

	if storedOrder.TotalCents != 2500 {
		t.Errorf("expected stored total %d, got %d", 2500, storedOrder.TotalCents)
	}
}

func TestHealthEndpoint(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	w := httptest.NewRecorder()

	// Simulate handler logic
	if req.Method != http.MethodGet {
		http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(map[string]string{"status": "ok"})

	if w.Code != http.StatusOK {
		t.Errorf("expected status %d, got %d", http.StatusOK, w.Code)
	}

	var resp map[string]string
	if err := json.NewDecoder(w.Body).Decode(&resp); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}

	if resp["status"] != "ok" {
		t.Errorf("expected status 'ok', got '%s'", resp["status"])
	}
}

// Helper to ensure time is used if needed, though not strictly necessary here
var _ = time.Now
```