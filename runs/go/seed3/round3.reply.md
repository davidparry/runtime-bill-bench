FILE: main_test.go
```go
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

func TestHealthEndpoint(t *testing.T) {
	server := NewServer(NewOrderStore())
	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("Expected status 200, got %d", w.Code)
	}

	var resp map[string]string
	json.NewDecoder(w.Body).Decode(&resp)
	if resp["status"] != "ok" {
		t.Errorf("Expected status 'ok', got '%s'", resp["status"])
	}
}

func TestCreateOrderSuccess(t *testing.T) {
	server := NewServer(NewOrderStore())
	payload := `{
		"customerId": "c-1",
		"items": [
			{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}
		]
	}`

	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(payload))
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	if w.Code != http.StatusCreated {
		t.Errorf("Expected status 201, got %d", w.Code)
	}

	var order Order
	json.NewDecoder(w.Body).Decode(&order)

	if order.CustomerID != "c-1" {
		t.Errorf("Expected customerId 'c-1', got '%s'", order.CustomerID)
	}
	if len(order.Items) != 1 {
		t.Errorf("Expected 1 item, got %d", len(order.Items))
	}
	if order.Items[0].SKU != "A-1" {
		t.Errorf("Expected sku 'A-1', got '%s'", order.Items[0].SKU)
	}
	if order.Items[0].Quantity != 2 {
		t.Errorf("Expected quantity 2, got %d", order.Items[0].Quantity)
	}
	if order.Items[0].UnitPriceCents != 1250 {
		t.Errorf("Expected unitPriceCents 1250, got %d", order.Items[0].UnitPriceCents)
	}
	// 2 * 1250 = 2500
	if order.TotalCents.Int64() != 2500 {
		t.Errorf("Expected totalCents 2500, got %d", order.TotalCents.Int64())
	}
	if order.ID == "" {
		t.Error("Expected non-empty ID")
	}
	if order.CreatedAt == "" {
		t.Error("Expected non-empty createdAt")
	}

	// Check Location header
	location := w.Header().Get("Location")
	if location != fmt.Sprintf("/orders/%s", order.ID) {
		t.Errorf("Expected Location header '/orders/%s', got '%s'", order.ID, location)
	}
}

func TestCreateOrderInvalidJSON(t *testing.T) {
	server := NewServer(NewOrderStore())
	payload := `{invalid json`

	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(payload))
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status 400, got %d", w.Code)
	}

	var resp ErrorResponse
	json.NewDecoder(w.Body).Decode(&resp)
	if resp.Error == "" {
		t.Error("Expected error message")
	}
}

func TestCreateOrderMissingCustomerID(t *testing.T) {
	server := NewServer(NewOrderStore())
	payload := `{"items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]}`

	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(payload))
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status 400, got %d", w.Code)
	}
}

func TestCreateOrderEmptyCustomerID(t *testing.T) {
	server := NewServer(NewOrderStore())
	payload := `{"customerId": "", "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]}`

	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(payload))
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status 400, got %d", w.Code)
	}
}

func TestCreateOrderCustomerIDTooLong(t *testing.T) {
	server := NewServer(NewOrderStore())
	customerID := strings.Repeat("a", 65)
	payload := fmt.Sprintf(`{"customerId": "%s", "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]}`, customerID)

	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(payload))
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status 400, got %d", w.Code)
	}
}

func TestCreateOrderEmptyItems(t *testing.T) {
	server := NewServer(NewOrderStore())
	payload := `{"customerId": "c-1", "items": []}`

	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(payload))
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status 400, got %d", w.Code)
	}
}

func TestCreateOrderTooManyItems(t *testing.T) {
	server := NewServer(NewOrderStore())
	items := make([]string, 51)
	for i := 0; i < 51; i++ {
		items[i] = `{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}`
	}
	payload := fmt.Sprintf(`{"customerId": "c-1", "items": [%s]}`, strings.Join(items, ","))

	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(payload))
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status 400, got %d", w.Code)
	}
}

func TestCreateOrderInvalidSKU(t *testing.T) {
	server := NewServer(NewOrderStore())
	payload := `{"customerId": "c-1", "items": [{"sku": "", "quantity": 1, "unitPriceCents": 100}]}`

	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(payload))
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status 400, got %d", w.Code)
	}
}

func TestCreateOrderInvalidQuantity(t *testing.T) {
	server := NewServer(NewOrderStore())
	payload := `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 0, "unitPriceCents": 100}]}`

	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(payload))
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status 400, got %d", w.Code)
	}
}

func TestCreateOrderInvalidUnitPriceCents(t *testing.T) {
	server := NewServer(NewOrderStore())
	payload := `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 0}]}`

	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(payload))
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status 400, got %d", w.Code)
	}
}

func TestGetOrderSuccess(t *testing.T) {
	store := NewOrderStore()
	server := NewServer(store)

	// Create an order first
	payload := `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]}`
	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(payload))
	w := httptest.NewRecorder()
	server.ServeHTTP(w, req)

	var order Order
	json.NewDecoder(w.Body).Decode(&order)

	// Get the order
	getReq := httptest.NewRequest(http.MethodGet, fmt.Sprintf("/orders/%s", order.ID), nil)
	getW := httptest.NewRecorder()
	server.ServeHTTP(getW, getReq)

	if getW.Code != http.StatusOK {
		t.Errorf("Expected status 200, got %d", getW.Code)
	}

	var getOrder Order
	json.NewDecoder(getW.Body).Decode(&getOrder)

	if getOrder.ID != order.ID {
		t.Errorf("Expected ID %s, got %s", order.ID, getOrder.ID)
	}
	if getOrder.CustomerID != order.CustomerID {
		t.Errorf("Expected customerId %s, got %s", order.CustomerID, getOrder.CustomerID)
	}
	if getOrder.TotalCents.Int64() != order.TotalCents.Int64() {
		t.Errorf("Expected totalCents %d, got %d", order.TotalCents.Int64(), getOrder.TotalCents.Int64())
	}
}

func TestGetOrderNotFound(t *testing.T) {
	server := NewServer(NewOrderStore())
	req := httptest.NewRequest(http.MethodGet, "/orders/non-existent-id", nil)
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	if w.Code != http.StatusNotFound {
		t.Errorf("Expected status 404, got %d", w.Code)
	}

	var resp ErrorResponse
	json.NewDecoder(w.Body).Decode(&resp)
	if resp.Error == "" {
		t.Error("Expected error message")
	}
}

func TestIgnoreUnknownFields(t *testing.T) {
	server := NewServer(NewOrderStore())
	payload := `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}], "unknownField": "value"}`

	req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(payload))
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	if w.Code != http.StatusCreated {
		t.Errorf("Expected status 201, got %d", w.Code)
	}
}

func TestContentTypes(t *testing.T) {
	server := NewServer(NewOrderStore())

	// Test Health
	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	w := httptest.NewRecorder()
	server.ServeHTTP(w, req)
	if w.Header().Get("Content-Type") != "application/json" {
		t.Errorf("Health endpoint should have Content-Type application/json")
	}

	// Test Create Order
	payload := `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]}`
	req = httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(payload))
	w = httptest.NewRecorder()
	server.ServeHTTP(w, req)
	if w.Header().Get("Content-Type") != "application/json" {
		t.Errorf("Create order endpoint should have Content-Type application/json")
	}

	// Test 404
	req = httptest.NewRequest(http.MethodGet, "/nonexistent", nil)
	w = httptest.NewRecorder()
	server.ServeHTTP(w, req)
	if w.Header().Get("Content-Type") != "application/json" {
		t.Errorf("404 response should have Content-Type application/json")
	}
}
```