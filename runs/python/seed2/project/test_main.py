import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

class TestHealthEndpoint:
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
        assert response.headers["Location"] == f"/orders/{response.json()['id']}"
        
        data = response.json()
        assert data["customerId"] == "c-1"
        assert len(data["items"]) == 1
        assert data["items"][0]["sku"] == "A-1"
        assert data["totalCents"] == 2500
        assert "createdAt" in data
        assert "id" in data
        # Verify UUID format (8-4-4-4-12 hex chars)
        import uuid
        uuid.UUID(data["id"], version=4)

    def test_create_order_invalid_json(self):
        response = client.post("/orders", content="not json", headers={"content-type": "application/json"})
        assert response.status_code == 400
        assert "error" in response.json() or "detail" in response.json() # FastAPI uses 'detail' for HTTPException

    def test_create_order_missing_customer_id(self):
        payload = {
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400

    def test_create_order_empty_items(self):
        payload = {
            "customerId": "c-1",
            "items": []
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400

    def test_create_order_single_item(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 201

    def test_create_order_max_items(self):
        items = [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100} for _ in range(50)]
        payload = {
            "customerId": "c-1",
            "items": items
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 201

    def test_create_order_too_many_items(self):
        items = [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100} for _ in range(51)]
        payload = {
            "customerId": "c-1",
            "items": items
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400

    def test_create_order_invalid_sku_length(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A" * 33, "quantity": 1, "unitPriceCents": 100}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400

    def test_create_order_invalid_quantity(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 0, "unitPriceCents": 100}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400

    def test_create_order_invalid_unit_price(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 0}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400

    def test_create_order_large_total(self):
        # 50 items, max quantity 100, max price 1,000,000
        # Max total = 50 * 100 * 1,000,000 = 5,000,000,000
        items = [{"sku": "A-1", "quantity": 100, "unitPriceCents": 1000000} for _ in range(50)]
        payload = {
            "customerId": "c-1",
            "items": items
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 201
        assert response.json()["totalCents"] == 5000000000

class TestGetOrder:
    def test_get_order_success(self):
        # First create an order
        payload = {
            "customerId": "c-2",
            "items": [{"sku": "B-1", "quantity": 1, "unitPriceCents": 500}]
        }
        create_resp = client.post("/orders", json=payload)
        order_id = create_resp.json()["id"]
        
        get_resp = client.get(f"/orders/{order_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == order_id
        assert get_resp.json()["customerId"] == "c-2"

    def test_get_order_not_found(self):
        fake_id = "non-existent-id-12345"
        response = client.get(f"/orders/{fake_id}")
        assert response.status_code == 404
        assert "error" in response.json() or "detail" in response.json()
