package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestValidateCustomerID(t *testing.T) {
	tests := []struct {
		name     string
		input    string
		expected string
	}{
		{"empty", "", "customerId is required"},
		{"too long", strings.Repeat("a", 65), "customerId must be between 1 and 64 characters"},
		{"valid", "c-1", ""},
		{"valid max length", strings.Repeat("a", 64), ""},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			errMsg := validateCustomerID(tt.input)
			if errMsg != tt.expected {
				t.Errorf("validateCustomerID(%q) = %q, want %q", tt.input, errMsg, tt.expected)
			}
		})
	}
}

func TestValidateItems(t *testing.T) {
	tests := []struct {
		name     string
		input    []OrderItemReq
		expected string
	}{
		{"nil", nil, "items is required"},
		{"empty", []OrderItemReq{}, "items must have between 1 and 50 entries"},
		{"too many", func() []OrderItemReq {
			items := make([]OrderItemReq, 51)
			for i := range items {
				items[i] = OrderItemReq{SKU: "A", Quantity: 1, UnitPriceCents: 1}
			}
			return items
		}(), "items must have between 1 and 50 entries"},
		{"missing sku", []OrderItemReq{{Quantity: 1, UnitPriceCents: 1}}, "items[0].sku is required"},
		{"invalid quantity", []OrderItemReq{{SKU: "A", Quantity: 0, UnitPriceCents: 1}}, "items[0].quantity must be between 1 and 100"},
		{"invalid price", []OrderItemReq{{SKU: "A", Quantity: 1, UnitPriceCents: 0}}, "items[0].unitPriceCents must be between 1 and 1000000"},
		{"valid", []OrderItemReq{{SKU: "A-1", Quantity: 2, UnitPriceCents: 1250}}, ""},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, errMsg := validateItems(tt.input)
			if errMsg != tt.expected {
				t.Errorf("validateItems(%v) = %q, want %q", tt.input, errMsg, tt.expected)
			}
		})
	}
}

func TestCreateOrderSuccess(t *testing.T) {
	store := NewOrderStore()
	handler := handleCreateOrder(store)

	body := `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}]}`
	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(body))
	w := httptest.NewRecorder()

	handler.ServeHTTP(w, req)

	if w.Code != http.StatusCreated {
		t.Errorf("Expected status %d, got %d", http.StatusCreated, w.Code)
	}

	resp := w.Result()
	if loc := resp.Header.Get("Location"); loc == "" {
		t.Error("Expected Location header")
	}

	var orderResp OrderResponse
	if err := json.NewDecoder(resp.Body).Decode(&orderResp); err != nil {
		t.Fatalf("Failed to decode response: %v", err)
	}

	if orderResp.CustomerID != "c-1" {
		t.Errorf("Expected customerId 'c-1', got '%s'", orderResp.CustomerID)
	}
	if len(orderResp.Items) != 1 {
		t.Errorf("Expected 1 item, got %d", len(orderResp.Items))
	}
	if orderResp.Items[0].SKU != "A-1" {
		t.Errorf("Expected SKU 'A-1', got '%s'", orderResp.Items[0].SKU)
	}
	if orderResp.TotalCents.Int.String() != "2500" {
		t.Errorf("Expected total '2500', got '%s'", orderResp.TotalCents.Int.String())
	}
}

func TestCreateOrderInvalidJSON(t *testing.T) {
	store := NewOrderStore()
	handler := handleCreateOrder(store)

	body := `{"invalid json`
	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(body))
	w := httptest.NewRecorder()

	handler.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status %d, got %d", http.StatusBadRequest, w.Code)
	}
}

func TestCreateOrderMissingCustomerID(t *testing.T) {
	store := NewOrderStore()
	handler := handleCreateOrder(store)

	body := `{"items": [{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}]}`
	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(body))
	w := httptest.NewRecorder()

	handler.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status %d, got %d", http.StatusBadRequest, w.Code)
	}
}

func TestCreateOrderMissingItems(t *testing.T) {
	store := NewOrderStore()
	handler := handleCreateOrder(store)

	body := `{"customerId": "c-1"}`
	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(body))
	w := httptest.NewRecorder()

	handler.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status %d, got %d", http.StatusBadRequest, w.Code)
	}
}

func TestCreateOrderInvalidQuantity(t *testing.T) {
	store := NewOrderStore()
	handler := handleCreateOrder(store)

	body := `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 0, "unitPriceCents": 1250}]}`
	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(body))
	w := httptest.NewRecorder()

	handler.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status %d, got %d", http.StatusBadRequest, w.Code)
	}
}

func TestGetOrderSuccess(t *testing.T) {
	store := NewOrderStore()
	createHandler := handleCreateOrder(store)
	getHandler := handleGetOrder(store)

	// Create an order first
	body := `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}]}`
	createReq := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(body))
	createW := httptest.NewRecorder()
	createHandler.ServeHTTP(createW, createReq)

	if createW.Code != http.StatusCreated {
		t.Fatalf("Failed to create order: %s", createW.Body.String())
	}

	resp := createW.Result()
	location := resp.Header.Get("Location")
	if location == "" {
		t.Fatal("Expected Location header")
	}
	
	// Extract ID from location
	id := strings.TrimPrefix(location, "/orders/")

	// Get the order
	getReq := httptest.NewRequest(http.MethodGet, "/orders/"+id, nil)
	getW := httptest.NewRecorder()
	getHandler.ServeHTTP(getW, getReq)

	if getW.Code != http.StatusOK {
		t.Errorf("Expected status %d, got %d", http.StatusOK, getW.Code)
	}

	var orderResp OrderResponse
	if err := json.NewDecoder(getW.Body).Decode(&orderResp); err != nil {
		t.Fatalf("Failed to decode response: %v", err)
	}

	if orderResp.ID != id {
		t.Errorf("Expected ID '%s', got '%s'", id, orderResp.ID)
	}
}

func TestGetOrderNotFound(t *testing.T) {
	store := NewOrderStore()
	handler := handleGetOrder(store)

	req := httptest.NewRequest(http.MethodGet, "/orders/non-existent", nil)
	w := httptest.NewRecorder()

	handler.ServeHTTP(w, req)

	if w.Code != http.StatusNotFound {
		t.Errorf("Expected status %d, got %d", http.StatusNotFound, w.Code)
	}

	var errResp ErrorResponse
	if err := json.NewDecoder(w.Body).Decode(&errResp); err != nil {
		t.Fatalf("Failed to decode error response: %v", err)
	}
	if errResp.Error != "Order not found" {
		t.Errorf("Expected error 'Order not found', got '%s'", errResp.Error)
	}
}

func TestHealth(t *testing.T) {
	handler := handleHealth

	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	w := httptest.NewRecorder()

	handler(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("Expected status %d, got %d", http.StatusOK, w.Code)
	}

	var resp map[string]string
	if err := json.NewDecoder(w.Body).Decode(&resp); err != nil {
		t.Fatalf("Failed to decode response: %v", err)
	}
	if resp["status"] != "ok" {
		t.Errorf("Expected status 'ok', got '%s'", resp["status"])
	}
}

func TestIgnoreUnknownFields(t *testing.T) {
	store := NewOrderStore()
	handler := handleCreateOrder(store)

	body := `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}], "unknownField": "value"}`
	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(body))
	w := httptest.NewRecorder()

	handler.ServeHTTP(w, req)

	if w.Code != http.StatusCreated {
		t.Errorf("Expected status %d, got %d. Body: %s", http.StatusCreated, w.Code, w.Body.String())
	}
}

func TestMaxTotalCents(t *testing.T) {
	store := NewOrderStore()
	handler := handleCreateOrder(store)

	// Construct a request that results in a large total
	// 50 items, each with quantity 100 and price 1000000
	// Total = 50 * 100 * 1000000 = 5,000,000,000
	items := make([]map[string]interface{}, 50)
	for i := range items {
		items[i] = map[string]interface{}{
			"sku":            "A",
			"quantity":       100,
			"unitPriceCents": 1000000,
		}
	}
	reqBody := map[string]interface{}{
		"customerId": "c-1",
		"items":      items,
	}
	
	jsonBody, _ := json.Marshal(reqBody)
	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBuffer(jsonBody))
	w := httptest.NewRecorder()

	handler.ServeHTTP(w, req)

	if w.Code != http.StatusCreated {
		t.Errorf("Expected status %d, got %d. Body: %s", http.StatusCreated, w.Code, w.Body.String())
	}

	var orderResp OrderResponse
	if err := json.NewDecoder(w.Body).Decode(&orderResp); err != nil {
		t.Fatalf("Failed to decode response: %v", err)
	}

	expectedTotal := "5000000000"
	if orderResp.TotalCents.Int.String() != expectedTotal {
		t.Errorf("Expected total '%s', got '%s'", expectedTotal, orderResp.TotalCents.Int.String())
	}
}
