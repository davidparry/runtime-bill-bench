import pytest
from fastapi.testclient import TestClient
import json

from main import app

client = TestClient(app)

class TestHealth:
    def test_health_ok(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

class TestCreateOrder:
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
        payload = {
            "customerId": "c-2",
            "items": [
                {"sku": "A-1", "quantity": 1, "unitPriceCents": 100},
                {"sku": "B-2", "quantity": 2, "unitPriceCents": 200}
            ]
        }
        response = client.post("/orders", json=payload)
        
        assert response.status_code == 201
        data = response.json()
        assert data["totalCents"] == 100 + 400 == 500

    def test_create_order_invalid_json(self):
        response = client.post("/orders", content="not json", headers={"content-type": "application/json"})
        assert response.status_code == 400
        data = response.json()
        assert "error" in data

    def test_create_order_missing_customer_id(self):
        payload = {
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        data = response.json()
        assert "error" in data

    def test_create_order_empty_items(self):
        payload = {
            "customerId": "c-1",
            "items": []
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        data = response.json()
        assert "error" in data

    def test_create_order_invalid_sku_length(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "a" * 33, "quantity": 1, "unitPriceCents": 100}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        data = response.json()
        assert "error" in data

    def test_create_order_invalid_quantity_zero(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 0, "unitPriceCents": 100}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        data = response.json()
        assert "error" in data

    def test_create_order_invalid_quantity_too_high(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 101, "unitPriceCents": 100}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        data = response.json()
        assert "error" in data

    def test_create_order_invalid_unit_price_zero(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 0}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        data = response.json()
        assert "error" in data

    def test_create_order_invalid_unit_price_too_high(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 1000001}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        data = response.json()
        assert "error" in data

    def test_create_order_too_many_items(self):
        items = [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100} for _ in range(51)]
        payload = {
            "customerId": "c-1",
            "items": items
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        data = response.json()
        assert "error" in data

    def test_create_order_ignore_unknown_fields(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100, "extra": "field"}],
            "unknownRoot": "value"
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["customerId"] == "c-1"

    def test_create_order_large_total_cents(self):
        # Max quantity 100 * Max price 1000000 = 100,000,000 per item
        # 50 items * 100,000,000 = 5,000,000,000
        items = [{"sku": "A-1", "quantity": 100, "unitPriceCents": 1000000} for _ in range(50)]
        payload = {
            "customerId": "c-1",
            "items": items
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["totalCents"] == 5000000000

class TestGetOrder:
    def test_get_order_success(self):
        # Create an order first
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]
        }
        create_response = client.post("/orders", json=payload)
        order_id = create_response.json()["id"]
        
        # Get the order
        response = client.get(f"/orders/{order_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == order_id
        assert data["customerId"] == "c-1"

    def test_get_order_not_found(self):
        response = client.get("/orders/non-existent-id")
        assert response.status_code == 404
        data = response.json()
        assert "error" in data

    def test_get_order_invalid_uuid_format(self):
        # Even if the ID doesn't look like a UUID, if it's not in the store, it's 404
        response = client.get("/orders/not-a-uuid")
        assert response.status_code == 404
        data = response.json()
        assert "error" in data
