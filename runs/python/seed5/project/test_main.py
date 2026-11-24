"""
Tests for Orders Service

Tests validation rules and 404 cases.
"""

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


class TestCreateOrder:
    """Tests for POST /orders endpoint."""

    def test_create_order_success(self):
        """Test successful order creation."""
        payload = {
            "customerId": "c-1",
            "items": [
                {"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}
            ]
        }
        response = client.post("/orders", json=payload)
        
        assert response.status_code == 201
        assert "Location" in response.headers
        assert response.headers["Location"].startswith("/orders/")
        
        data = response.json()
        assert data["customerId"] == "c-1"
        assert len(data["items"]) == 1
        assert data["items"][0]["sku"] == "A-1"
        assert data["items"][0]["quantity"] == 2
        assert data["items"][0]["unitPriceCents"] == 1250
        assert data["totalCents"] == 2500
        assert "id" in data
        assert "createdAt" in data

    def test_create_order_multiple_items(self):
        """Test order with multiple items."""
        payload = {
            "customerId": "c-2",
            "items": [
                {"sku": "S-1", "quantity": 1, "unitPriceCents": 100},
                {"sku": "S-2", "quantity": 3, "unitPriceCents": 200}
            ]
        }
        response = client.post("/orders", json=payload)
        
        assert response.status_code == 201
        data = response.json()
        assert data["totalCents"] == 100 + (3 * 200) == 700

    def test_create_order_invalid_json(self):
        """Test response for invalid JSON body."""
        response = client.post("/orders", content="not json", headers={"Content-Type": "application/json"})
        
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_missing_customerId(self):
        """Test validation for missing customerId."""
        payload = {
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]
        }
        response = client.post("/orders", json=payload)
        
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_empty_items(self):
        """Test validation for empty items array."""
        payload = {
            "customerId": "c-1",
            "items": []
        }
        response = client.post("/orders", json=payload)
        
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_sku_too_long(self):
        """Test validation for SKU exceeding max length."""
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A" * 33, "quantity": 1, "unitPriceCents": 100}]
        }
        response = client.post("/orders", json=payload)
        
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_quantity_zero(self):
        """Test validation for quantity less than 1."""
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 0, "unitPriceCents": 100}]
        }
        response = client.post("/orders", json=payload)
        
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_quantity_too_high(self):
        """Test validation for quantity exceeding max."""
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 101, "unitPriceCents": 100}]
        }
        response = client.post("/orders", json=payload)
        
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_unit_price_zero(self):
        """Test validation for unitPriceCents less than 1."""
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 0}]
        }
        response = client.post("/orders", json=payload)
        
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_unit_price_too_high(self):
        """Test validation for unitPriceCents exceeding max."""
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 1000001}]
        }
        response = client.post("/orders", json=payload)
        
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_too_many_items(self):
        """Test validation for more than 50 items."""
        items = [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100} for _ in range(51)]
        payload = {
            "customerId": "c-1",
            "items": items
        }
        response = client.post("/orders", json=payload)
        
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_customerId_too_long(self):
        """Test validation for customerId exceeding max length."""
        payload = {
            "customerId": "c" * 65,
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]
        }
        response = client.post("/orders", json=payload)
        
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_ignore_unknown_fields(self):
        """Test that unknown fields are ignored."""
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}],
            "unknownField": "should be ignored",
            "nested": {"key": "value"}
        }
        response = client.post("/orders", json=payload)
        
        assert response.status_code == 201
        data = response.json()
        assert "unknownField" not in data
        assert "nested" not in data

    def test_create_order_content_type_application_json(self):
        """Test that response has correct content type."""
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]
        }
        response = client.post("/orders", json=payload)
        
        assert response.status_code == 201
        assert "application/json" in response.headers.get("content-type", "")


class TestGetOrder:
    """Tests for GET /orders/{id} endpoint."""

    def test_get_order_success(self):
        """Test retrieving an existing order."""
        # First create an order
        create_payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]
        }
        create_response = client.post("/orders", json=create_payload)
        order_id = create_response.json()["id"]
        
        # Now retrieve it
        response = client.get(f"/orders/{order_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == order_id
        assert data["customerId"] == "c-1"

    def test_get_order_not_found(self):
        """Test 404 for non-existent order."""
        response = client.get("/orders/non-existent-id")
        
        assert response.status_code == 404
        assert "error" in response.json()
        assert "not found" in response.json()["error"].lower()

    def test_get_order_content_type(self):
        """Test that response has correct content type."""
        response = client.get("/orders/non-existent-id")
        
        assert response.status_code == 404
        assert "application/json" in response.headers.get("content-type", "")


class TestHealth:
    """Tests for GET /health endpoint."""

    def test_health_check(self):
        """Test health check endpoint."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_health_content_type(self):
        """Test that health response has correct content type."""
        response = client.get("/health")
        
        assert response.status_code == 200
        assert "application/json" in response.headers.get("content-type", "")
