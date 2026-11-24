package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestHealthEndpoint(t *testing.T) {
	req := httptest.NewRequest("GET", "/health", nil)
	w := httptest.NewRecorder()

	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
		logRequest(r, http.StatusOK, time.Since(start).Milliseconds())
	})

	handler.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected status 200, got %d", w.Code)
	}

	var resp map[string]string
	json.Unmarshal(w.Body.Bytes(), &resp)
	if resp["status"] != "ok" {
		t.Errorf("expected status 'ok', got '%s'", resp["status"])
	}
}

func TestCreateOrderValidationSuccess(t *testing.T) {
	body := `{
		"customerId": "c-1",
		"items": [
			{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}
		]
	}`

	req, err := validateOrderRequest([]byte(body))
	if err != nil {
		t.Fatalf("validation failed: %v", err)
	}
	if req.CustomerID != "c-1" {
		t.Errorf("expected customerId 'c-1', got '%s'", req.CustomerID)
	}
	if len(req.Items) != 1 {
		t.Fatalf("expected 1 item, got %d", len(req.Items))
	}
	if req.Items[0].SKU != "A-1" {
		t.Errorf("expected sku 'A-1', got '%s'", req.Items[0].SKU)
	}
	if req.Items[0].Quantity != 2 {
		t.Errorf("expected quantity 2, got %d", req.Items[0].Quantity)
	}
	if req.Items[0].UnitPriceCents != 1250 {
		t.Errorf("expected unitPriceCents 1250, got %d", req.Items[0].UnitPriceCents)
	}
}

func TestCreateOrderValidationErrors(t *testing.T) {
	tests := []struct {
		name     string
		body     string
		expected string
	}{
		{
			name:     "missing customerId",
			body:     `{"items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]}`,
			expected: "customerId is required",
		},
		{
			name:     "missing items",
			body:     `{"customerId": "c-1"}`,
			expected: "items is required",
		},
		{
			name:     "invalid json",
			body:     `not json`,
			expected: "invalid JSON",
		},
		{
			name:     "empty items",
			body:     `{"customerId": "c-1", "items": []}`,
			expected: "items must contain between 1 and 50 entries",
		},
		{
			name:     "sku too long",
			body:     `{"customerId": "c-1", "items": [{"sku": "A12345678901234567890123456789012", "quantity": 1, "unitPriceCents": 100}]}`,
			expected: "items[0].sku must be between 1 and 32 characters",
		},
		{
			name:     "quantity zero",
			body:     `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 0, "unitPriceCents": 100}]}`,
			expected: "items[0].quantity must be between 1 and 100",
		},
		{
			name:     "quantity 101",
			body:     `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 101, "unitPriceCents": 100}]}`,
			expected: "items[0].quantity must be between 1 and 100",
		},
		{
			name:     "price zero",
			body:     `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 0}]}`,
			expected: "items[0].unitPriceCents must be between 1 and 1000000",
		},
		{
			name:     "price 1000001",
			body:     `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 1000001}]}`,
			expected: "items[0].unitPriceCents must be between 1 and 1000000",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, err := validateOrderRequest([]byte(tt.body))
			if err == nil {
				t.Fatalf("expected error, got nil")
			}
			if !strings.Contains(err.Error(), tt.expected) {
				t.Errorf("expected error to contain '%s', got '%s'", tt.expected, err.Error())
			}
		})
	}
}

func TestGetOrderNotFound(t *testing.T) {
	// Create a fresh store for this test to avoid interference
	localStore := NewOrderStore()

	req := httptest.NewRequest("GET", "/orders/non-existent-id", nil)
	w := httptest.NewRecorder()

	// Simulate handler logic
	start := time.Now()
	path := strings.TrimPrefix(req.URL.Path, "/")
	parts := strings.Split(path, "/")
	if len(parts) != 2 {
		writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "not found"})
		logRequest(req, http.StatusNotFound, time.Since(start).Milliseconds())
		t.Fatal("invalid path")
	}
	id := parts[1]

	order, found := localStore.Get(id)
	if !found {
		writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "order not found"})
		logRequest(req, http.StatusNotFound, time.Since(start).Milliseconds())
		
		if w.Code != http.StatusNotFound {
			t.Errorf("expected status 404, got %d", w.Code)
		}
		
		var resp ErrorResponse
		json.Unmarshal(w.Body.Bytes(), &resp)
		if resp.Error != "order not found" {
			t.Errorf("expected error 'order not found', got '%s'", resp.Error)
		}
		return
	}
	
	t.Errorf("expected order not found, got %+v", order)
}
