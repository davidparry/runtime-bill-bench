FILE: main_test.go
```go
package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestHandleCreateOrder(t *testing.T) {
	store := NewOrderStore()
	handler := handleCreateOrder(store)

	tests := []struct {
		name          string
		payload       interface{}
		expectedStatus int
	}{
		{
			name: "valid order",
			payload: map[string]interface{}{
				"customerId": "c-1",
				"items": []map[string]interface{}{
					{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250},
				},
			},
			expectedStatus: http.StatusCreated,
		},
		{
			name: "invalid JSON",
			payload: []byte("not json"),
			expectedStatus: http.StatusBadRequest,
		},
		{
			name: "missing customerId",
			payload: map[string]interface{}{
				"items": []map[string]interface{}{
					{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250},
				},
			},
			expectedStatus: http.StatusBadRequest,
		},
		{
			name: "customerId too long",
			payload: map[string]interface{}{
				"customerId": "a",
				"items": []map[string]interface{}{
					{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250},
				},
			},
			expectedStatus: http.StatusBadRequest,
		},
		{
			name: "items empty",
			payload: map[string]interface{}{
				"customerId": "c-1",
				"items":      []map[string]interface{}{},
			},
			expectedStatus: http.StatusBadRequest,
		},
		{
			name: "items too many",
			payload: map[string]interface{}{
				"customerId": "c-1",
				"items": func() []map[string]interface{} {
					items := make([]map[string]interface{}, 51)
					for i := 0; i < 51; i++ {
						items[i] = map[string]interface{}{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}
					}
					return items
				}(),
			},
			expectedStatus: http.StatusBadRequest,
		},
		{
			name: "item sku missing",
			payload: map[string]interface{}{
				"customerId": "c-1",
				"items": []map[string]interface{}{
					{"quantity": 2, "unitPriceCents": 1250},
				},
			},
			expectedStatus: http.StatusBadRequest,
		},
		{
			name: "item sku too long",
			payload: map[string]interface{}{
				"customerId": "c-1",
				"items": []map[string]interface{}{
					{"sku": "a", "quantity": 2, "unitPriceCents": 1250},
				},
			},
			expectedStatus: http.StatusBadRequest,
		},
		{
			name: "item quantity zero",
			payload: map[string]interface{}{
				"customerId": "c-1",
				"items": []map[string]interface{}{
					{"sku": "A-1", "quantity": 0, "unitPriceCents": 1250},
				},
			},
			expectedStatus: http.StatusBadRequest,
		},
		{
			name: "item quantity too high",
			payload: map[string]interface{}{
				"customerId": "c-1",
				"items": []map[string]interface{}{
					{"sku": "A-1", "quantity": 101, "unitPriceCents": 1250},
				},
			},
			expectedStatus: http.StatusBadRequest,
		},
		{
			name: "item unitPriceCents zero",
			payload: map[string]interface{}{
				"customerId": "c-1",
				"items": []map[string]interface{}{
					{"sku": "A-1", "quantity": 2, "unitPriceCents": 0},
				},
			},
			expectedStatus: http.StatusBadRequest,
		},
		{
			name: "item unitPriceCents too high",
			payload: map[string]interface{}{
				"customerId": "c-1",
				"items": []map[string]interface{}{
					{"sku": "A-1", "quantity": 2, "unitPriceCents": 1000001},
				},
			},
			expectedStatus: http.StatusBadRequest,
		},
		{
			name: "unknown fields ignored",
			payload: map[string]interface{}{
				"customerId": "c-1",
				"items": []map[string]interface{}{
					{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250, "extra": "field"},
				},
				"extraTop": "field",
			},
			expectedStatus: http.StatusCreated,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var body []byte
			var err error
			switch p := tt.payload.(type) {
			case []byte:
				body = p
			default:
				body, err = json.Marshal(p)
				if err != nil {
					t.Fatalf("failed to marshal payload: %v", err)
				}
			}

			req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewReader(body))
			rec := httptest.NewRecorder()

			handler.ServeHTTP(rec, req)

			if rec.Code != tt.expectedStatus {
				t.Errorf("expected status %d, got %d. Body: %s", tt.expectedStatus, rec.Code, rec.Body.String())
			}
		})
	}
}

func TestHandleGetOrder(t *testing.T) {
	store := NewOrderStore()
	handler := handleGetOrder(store)

	// Create a valid order first
	validOrder := Order{
		ID:         "test-id-123",
		CustomerID: "c-1",
		Items:      []OrderItem{{SKU: "A-1", Quantity: 2, UnitPriceCents: 1250}},
		TotalCents: 2500,
		CreatedAt:  time.Now().UTC(),
	}
	store.Create(validOrder)

	tests := []struct {
		name          string
		path          string
		expectedStatus int
	}{
		{
			name:          "valid order",
			path:          "/orders/test-id-123",
			expectedStatus: http.StatusOK,
		},
		{
			name:          "non-existent order",
			path:          "/orders/non-existent",
			expectedStatus: http.StatusNotFound,
		},
		{
			name:          "invalid path",
			path:          "/orders",
			expectedStatus: http.StatusBadRequest,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodGet, tt.path, nil)
			rec := httptest.NewRecorder()

			handler.ServeHTTP(rec, req)

			if rec.Code != tt.expectedStatus {
				t.Errorf("expected status %d, got %d. Body: %s", tt.expectedStatus, rec.Code, rec.Body.String())
			}
		})
	}
}

func TestHandleHealth(t *testing.T) {
	handler := handleHealth()
	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Errorf("expected status %d, got %d", http.StatusOK, rec.Code)
	}

	var resp map[string]string
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}

	if resp["status"] != "ok" {
		t.Errorf("expected status 'ok', got '%s'", resp["status"])
	}
}
```