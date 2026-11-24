import pytest
import json
import time
import uuid
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

# --- Validation Tests ---

class TestValidation:
    def test_create_order_success(self):
        payload = {
            "customerId": "c-1",
            "items": [
                {"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}
            ]
        }
        response = client.post("/orders", json=payload)
        
        assert response.status_code == 201
        assert "Location" in response.headers
        assert "/orders/" in response.headers["Location"]
        
        data = response.json()
        assert data["customerId"] == "c-1"
        assert len(data["items"]) == 1
        assert data["items"][0]["sku"] == "A-1"
        assert data["totalCents"] == 2500
        assert "id" in data
        assert "createdAt" in data

    def test_create_order_invalid_json(self):
        response = client.post("/orders", content="not json", headers={"Content-Type": "application/json"})
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_missing_customerId(self):
        payload = {"items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]}
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_empty_items(self):
        payload = {"customerId": "c-1", "items": []}
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_invalid_sku_length(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "a" * 33, "quantity": 1, "unitPriceCents": 100}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_invalid_quantity(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 0, "unitPriceCents": 100}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_invalid_unit_price(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 0}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_too_many_items(self):
        items = [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100} for _ in range(51)]
        payload = {"customerId": "c-1", "items": items}
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_ignores_unknown_fields(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100, "extra": "field"}],
            "unknown": "top"
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 201

    def test_create_order_large_total(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 100, "unitPriceCents": 1000000}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 201
        assert response.json()["totalCents"] == 100000000

# --- 404 Tests ---

class TestNotFound:
    def test_get_order_not_found(self):
        fake_id = str(uuid.uuid4())
        response = client.get(f"/orders/{fake_id}")
        assert response.status_code == 404
        assert "error" in response.json()

    def test_get_order_non_existent_id(self):
        # Use a format that is definitely not in the store
        response = client.get("/orders/non-existent-id")
        assert response.status_code == 404
        assert "error" in response.json()

# --- Health Check Test ---

class TestHealth:
    def test_health_ok(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
