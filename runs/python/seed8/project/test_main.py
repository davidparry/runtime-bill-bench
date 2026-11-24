import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

class TestCreateOrderValidation:
    def test_missing_customer_id(self):
        response = client.post("/orders", json={"items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]})
        assert response.status_code == 400
        assert "error" in response.json()

    def test_missing_items(self):
        response = client.post("/orders", json={"customerId": "c-1"})
        assert response.status_code == 400
        assert "error" in response.json()

    def test_empty_items(self):
        response = client.post("/orders", json={"customerId": "c-1", "items": []})
        assert response.status_code == 400
        assert "error" in response.json()

    def test_invalid_quantity_too_low(self):
        response = client.post("/orders", json={"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 0, "unitPriceCents": 100}]})
        assert response.status_code == 400
        assert "error" in response.json()

    def test_invalid_quantity_too_high(self):
        response = client.post("/orders", json={"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 101, "unitPriceCents": 100}]})
        assert response.status_code == 400
        assert "error" in response.json()

    def test_invalid_unit_price_zero(self):
        response = client.post("/orders", json={"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 0}]})
        assert response.status_code == 400
        assert "error" in response.json()

    def test_invalid_unit_price_too_high(self):
        response = client.post("/orders", json={"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 1000001}]})
        assert response.status_code == 400
        assert "error" in response.json()

    def test_invalid_sku_length(self):
        response = client.post("/orders", json={"customerId": "c-1", "items": [{"sku": "A" * 33, "quantity": 1, "unitPriceCents": 100}]})
        assert response.status_code == 400
        assert "error" in response.json()

    def test_invalid_customer_id_length(self):
        response = client.post("/orders", json={"customerId": "c" * 65, "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]})
        assert response.status_code == 400
        assert "error" in response.json()

    def test_invalid_items_length(self):
        items = [{"sku": f"S-{i}", "quantity": 1, "unitPriceCents": 100} for i in range(51)]
        response = client.post("/orders", json={"customerId": "c-1", "items": items})
        assert response.status_code == 400
        assert "error" in response.json()

    def test_invalid_json(self):
        response = client.post("/orders", content="not json", headers={"Content-Type": "application/json"})
        assert response.status_code == 400
        assert "error" in response.json()

class TestCreateOrderSuccess:
    def test_valid_order(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}]
        }
        response = client.post("/orders", json=payload)
        
        assert response.status_code == 201
        assert "Location" in response.headers
        assert response.headers["Location"].startswith("/orders/")
        
        data = response.json()
        assert data["customerId"] == "c-1"
        assert len(data["items"]) == 1
        assert data["items"][0]["sku"] == "A-1"
        assert data["totalCents"] == 2500
        assert "id" in data
        assert "createdAt" in data

    def test_multiple_items(self):
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
        assert data["totalCents"] == 100 + 400  # 500

class TestGetOrder:
    def test_existing_order(self):
        # Create an order first
        create_resp = client.post("/orders", json={
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]
        })
        order_id = create_resp.json()["id"]
        
        get_resp = client.get(f"/orders/{order_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["id"] == order_id
        assert data["totalCents"] == 100

    def test_non_existing_order(self):
        response = client.get("/orders/non-existent-id")
        assert response.status_code == 404
        assert "error" in response.json()

class TestHealth:
    def test_health_check(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
