import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

# --- Health Check ---

class TestHealth:
    def test_health_ok(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

# --- Create Order Validation ---

class TestCreateOrderValidation:
    def test_valid_order(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["customerId"] == "c-1"
        assert len(data["items"]) == 1
        assert data["totalCents"] == 2500
        assert "createdAt" in data
        assert "Location" in response.headers

    def test_missing_customer_id(self):
        payload = {
            "items": [{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_empty_customer_id(self):
        payload = {
            "customerId": "",
            "items": [{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_customer_id_too_long(self):
        payload = {
            "customerId": "a" * 65,
            "items": [{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_missing_items(self):
        payload = {
            "customerId": "c-1"
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_empty_items(self):
        payload = {
            "customerId": "c-1",
            "items": []
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_item_sku_too_long(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "a" * 33, "quantity": 1, "unitPriceCents": 100}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_item_quantity_zero(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 0, "unitPriceCents": 100}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_item_quantity_too_high(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 101, "unitPriceCents": 100}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_item_unit_price_zero(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 0}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_item_unit_price_too_high(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 1000001}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_too_many_items(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100} for _ in range(51)]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_invalid_json(self):
        response = client.post("/orders", content="not json", headers={"Content-Type": "application/json"})
        assert response.status_code == 400
        assert "error" in response.json()

    def test_ignore_unknown_fields(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250, "extra": "field"}],
            "extra": "field"
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert "extra" not in data
        assert len(data["items"]) == 1
        assert "extra" not in data["items"][0]

# --- Get Order ---

class TestGetOrder:
    def test_get_existing_order(self):
        # Create an order first
        create_payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}]
        }
        create_response = client.post("/orders", json=create_payload)
        assert create_response.status_code == 201
        order_id = create_response.json()["id"]
        
        # Get the order
        response = client.get(f"/orders/{order_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == order_id
        assert data["customerId"] == "c-1"
        assert data["totalCents"] == 2500

    def test_get_non_existing_order(self):
        response = client.get("/orders/non-existent-id")
        assert response.status_code == 404
        assert "error" in response.json()
