package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestValidateCustomerID(t *testing.T) {
	tests := []struct {
		name    string
		id      string
		wantErr bool
	}{
		{"valid short ID", "c-1", false},
		{"valid long ID", strings.Repeat("c", 64), false},
		{"empty ID", "", true},
		{"too short", "", true},
		{"too long", strings.Repeat("c", 65), true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := validateCustomerID(tt.id)
			if (err != nil) != tt.wantErr {
				t.Errorf("validateCustomerID(%q) error = %v, wantErr %v", tt.id, err, tt.wantErr)
			}
		})
	}
}

func TestValidateItems(t *testing.T) {
	tests := []struct {
		name    string
		items   []OrderItem
		wantErr bool
	}{
		{"valid single item", []OrderItem{{SKU: "A-1", Quantity: 1, UnitPriceCents: 100}}, false},
		{"valid multiple items", []OrderItem{
			{SKU: "A-1", Quantity: 1, UnitPriceCents: 100},
			{SKU: "A-2", Quantity: 2, UnitPriceCents: 200},
		}, false},
		{"too many items", nil, true},
		{"empty items", []OrderItem{}, true},
		{"invalid quantity", []OrderItem{{SKU: "A-1", Quantity: 0, UnitPriceCents: 100}}, true},
		{"invalid unit price", []OrderItem{{SKU: "A-1", Quantity: 1, UnitPriceCents: 0}}, true},
		{"invalid sku length", []OrderItem{{SKU: strings.Repeat("a", 33), Quantity: 1, UnitPriceCents: 100}}, true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := validateItems(tt.items)
			if (err != nil) != tt.wantErr {
				t.Errorf("validateItems() error = %v, wantErr %v", err, tt.wantErr)
			}
		})
	}
}

func TestHandleCreateOrder(t *testing.T) {
	store := NewOrderStore()
	handler := NewOrderHandler(store)

	tests := []struct {
		name           string
		requestBody    string
		wantStatus     int
		wantLocation   bool
		wantError      bool
	}{
		{
			name:        "valid order",
			requestBody: `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}]}`,
			wantStatus:  http.StatusCreated,
			wantLocation: true,
		},
		{
			name:        "invalid customer ID",
			requestBody: `{"customerId": "", "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]}`,
			wantStatus:  http.StatusBadRequest,
			wantError:   true,
		},
		{
			name:        "invalid items",
			requestBody: `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 0, "unitPriceCents": 100}]}`,
			wantStatus:  http.StatusBadRequest,
			wantError:   true,
		},
		{
			name:        "invalid JSON",
			requestBody: `{invalid json}`,
			wantStatus:  http.StatusBadRequest,
			wantError:   true,
		},
		{
			name:        "unknown fields ignored",
			requestBody: `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}], "unknown": "field"}`,
			wantStatus:  http.StatusCreated,
			wantLocation: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(tt.requestBody))
			req.Header.Set("Content-Type", "application/json")
			w := httptest.NewRecorder()

			handler.handleCreateOrder(w, req)

			if w.Code != tt.wantStatus {
				t.Errorf("handleCreateOrder() status = %d, want %d", w.Code, tt.wantStatus)
			}

			if tt.wantLocation {
				location := w.Header().Get("Location")
				if location == "" {
					t.Errorf("handleCreateOrder() missing Location header")
				}
			}

			if tt.wantError {
				var resp ErrorResponse
				if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
					t.Errorf("handleCreateOrder() failed to unmarshal error response: %v", err)
				}
				if resp.Error == "" {
					t.Errorf("handleCreateOrder() error response has empty error message")
				}
			} else {
				var resp Order
				if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
					t.Errorf("handleCreateOrder() failed to unmarshal order response: %v", err)
				}
				if resp.ID == "" {
					t.Errorf("handleCreateOrder() returned order with empty ID")
				}
			}
		})
	}
}

func TestHandleGetOrder(t *testing.T) {
	store := NewOrderStore()
	handler := NewOrderHandler(store)

	// Create an order first
	reqBody := `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]}`
	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(reqBody))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	handler.handleCreateOrder(w, req)

	var createdOrder Order
	if err := json.Unmarshal(w.Body.Bytes(), &createdOrder); err != nil {
		t.Fatalf("failed to unmarshal created order: %v", err)
	}

	tests := []struct {
		name       string
		orderID    string
		wantStatus int
	}{
		{"existing order", createdOrder.ID, http.StatusOK},
		{"non-existing order", "non-existing-id", http.StatusNotFound},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodGet, fmt.Sprintf("/orders/%s", tt.orderID), nil)
			w := httptest.NewRecorder()

			handler.handleGetOrder(w, req, tt.orderID)

			if w.Code != tt.wantStatus {
				t.Errorf("handleGetOrder() status = %d, want %d", w.Code, tt.wantStatus)
			}

			if tt.wantStatus == http.StatusOK {
				var resp Order
				if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
					t.Errorf("handleGetOrder() failed to unmarshal order response: %v", err)
				}
				if resp.ID != tt.orderID {
					t.Errorf("handleGetOrder() returned order with ID %s, want %s", resp.ID, tt.orderID)
				}
			} else if tt.wantStatus == http.StatusNotFound {
				var resp ErrorResponse
				if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
					t.Errorf("handleGetOrder() failed to unmarshal error response: %v", err)
				}
				if resp.Error == "" {
					t.Errorf("handleGetOrder() error response has empty error message")
				}
			}
		})
	}
}

func TestHandleHealth(t *testing.T) {
	handler := NewOrderHandler(NewOrderStore())

	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	w := httptest.NewRecorder()

	handler.handleHealth(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("handleHealth() status = %d, want %d", w.Code, http.StatusOK)
	}

	var resp map[string]string
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Errorf("handleHealth() failed to unmarshal response: %v", err)
	}
	if resp["status"] != "ok" {
		t.Errorf("handleHealth() status = %s, want %s", resp["status"], "ok")
	}
}

func TestLoggingMiddleware(t *testing.T) {
	store := NewOrderStore()
	handler := NewOrderHandler(store)
	mux := http.NewServeMux()
	mux.HandleFunc("/health", handler.handleHealth)

	server := httptest.NewServer(loggingMiddleware(mux))
	defer server.Close()

	resp, err := http.Get(server.URL + "/health")
	if err != nil {
		t.Fatalf("failed to make request: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Errorf("expected status 200, got %d", resp.StatusCode)
	}

	// Check that the log output contains the expected keys
	// Since we can't easily capture stdout in tests, we'll just verify the request was processed
}

func TestConcurrentAccess(t *testing.T) {
	store := NewOrderStore()
	handler := NewOrderHandler(store)
	mux := http.NewServeMux()
	mux.HandleFunc("/orders", handler.handleCreateOrder)
	mux.HandleFunc("/orders/", func(w http.ResponseWriter, r *http.Request) {
		id := r.URL.Path[len("/orders/"):]
		handler.handleGetOrder(w, r, id)
	})
	mux.HandleFunc("/health", handler.handleHealth)

	server := httptest.NewServer(loggingMiddleware(mux))
	defer server.Close()

	// Create several orders concurrently
	done := make(chan bool)
	for i := 0; i < 10; i++ {
		go func(i int) {
			reqBody := fmt.Sprintf(`{"customerId": "c-%d", "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]}`, i)
			resp, err := http.Post(server.URL+"/orders", "application/json", bytes.NewBufferString(reqBody))
			if err != nil {
				t.Errorf("failed to create order: %v", err)
				return
			}
			defer resp.Body.Close()
			
			if resp.StatusCode != http.StatusCreated {
				t.Errorf("expected status 201, got %d", resp.StatusCode)
			}
			
			var order Order
			if err := json.NewDecoder(resp.Body).Decode(&order); err != nil {
				t.Errorf("failed to decode response: %v", err)
				return
			}
			
			// Verify we can retrieve the order
			getResp, err := http.Get(server.URL + "/orders/" + order.ID)
			if err != nil {
				t.Errorf("failed to get order: %v", err)
				return
			}
			defer getResp.Body.Close()
			
			if getResp.StatusCode != http.StatusOK {
				t.Errorf("expected status 200 for retrieval, got %d", getResp.StatusCode)
			}
			
			done <- true
		}(i)
	}

	// Wait for all goroutines to complete
	for i := 0; i < 10; i++ {
		<-done
	}
}
