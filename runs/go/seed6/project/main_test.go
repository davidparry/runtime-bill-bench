package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestValidateCreateRequest(t *testing.T) {
	tests := []struct {
		name        string
		body        string
		contentType string
		wantErr     bool
		errContains string
	}{
		{
			name:        "valid request",
			body:        `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}]}`,
			contentType: "application/json",
			wantErr:     false,
		},
		{
			name:        "invalid JSON",
			body:        `{invalid}`,
			contentType: "application/json",
			wantErr:     true,
		},
		{
			name:        "missing customerId",
			body:        `{"items": [{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}]}`,
			contentType: "application/json",
			wantErr:     true,
			errContains: "customerId is required",
		},
		{
			name:        "customerId too long",
			body:        `{"customerId": "` + strings.Repeat("a", 65) + `", "items": [{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}]}`,
			contentType: "application/json",
			wantErr:     true,
			errContains: "customerId must be between 1 and 64 characters",
		},
		{
			name:        "customerId empty",
			body:        `{"customerId": "", "items": [{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}]}`,
			contentType: "application/json",
			wantErr:     true,
			errContains: "customerId is required",
		},
		{
			name:        "empty items",
			body:        `{"customerId": "c-1", "items": []}`,
			contentType: "application/json",
			wantErr:     true,
			errContains: "items is required",
		},
		{
			name:        "items too many",
			body:        `{"customerId": "c-1", "items": ` + makeItemsJSON(51) + `}`,
			contentType: "application/json",
			wantErr:     true,
			errContains: "items must have at most 50 entries",
		},
		{
			name:        "sku too long",
			body:        `{"customerId": "c-1", "items": [{"sku": "` + strings.Repeat("a", 33) + `", "quantity": 2, "unitPriceCents": 1250}]}`,
			contentType: "application/json",
			wantErr:     true,
			errContains: "items[0].sku must be between 1 and 32 characters",
		},
		{
			name:        "quantity too low",
			body:        `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 0, "unitPriceCents": 1250}]}`,
			contentType: "application/json",
			wantErr:     true,
			errContains: "items[0].quantity must be between 1 and 100",
		},
		{
			name:        "quantity too high",
			body:        `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 101, "unitPriceCents": 1250}]}`,
			contentType: "application/json",
			wantErr:     true,
			errContains: "items[0].quantity must be between 1 and 100",
		},
		{
			name:        "unitPriceCents too low",
			body:        `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 2, "unitPriceCents": 0}]}`,
			contentType: "application/json",
			wantErr:     true,
			errContains: "items[0].unitPriceCents must be between 1 and 1000000",
		},
		{
			name:        "unitPriceCents too high",
			body:        `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 2, "unitPriceCents": 1000001}]}`,
			contentType: "application/json",
			wantErr:     true,
			errContains: "items[0].unitPriceCents must be between 1 and 1000000",
		},
		{
			name:        "unknown fields ignored",
			body:        `{"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}], "extra": "field"}`,
			contentType: "application/json",
			wantErr:     false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodPost, "/orders", bytes.NewBufferString(tt.body))
			req.Header.Set("Content-Type", tt.contentType)
			
			_, err := validateCreateRequest(req)
			
			if (err != nil) != tt.wantErr {
				t.Errorf("validateCreateRequest() error = %v, wantErr %v", err, tt.wantErr)
				return
			}
			if tt.wantErr && tt.errContains != "" && !strings.Contains(err.Error(), tt.errContains) {
				t.Errorf("validateCreateRequest() error = %v, should contain %v", err, tt.errContains)
			}
		})
	}
}

func TestHandleGetOrderNotFound(t *testing.T) {
	store := NewOrderStore()
	handler := handleGetOrder(store)
	
	req := httptest.NewRequest(http.MethodGet, "/orders/non-existent-id", nil)
	rr := httptest.NewRecorder()
	
	handler.ServeHTTP(rr, req)
	
	if rr.Code != http.StatusNotFound {
		t.Errorf("handleGetOrder() status = %v, want %v", rr.Code, http.StatusNotFound)
	}
	
	var resp ErrorResponse
	if err := json.Unmarshal(rr.Body.Bytes(), &resp); err != nil {
		t.Errorf("handleGetOrder() response body is not valid JSON: %v", err)
	}
	
	if resp.Error == "" {
		t.Errorf("handleGetOrder() error message is empty")
	}
}

func makeItemsJSON(count int) string {
	if count == 0 {
		return "[]"
	}
	items := make([]string, count)
	for i := 0; i < count; i++ {
		items[i] = `{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}`
	}
	return "[" + strings.Join(items, ",") + "]"
}
