FILE: tests/test_orders.py
```python
import os
import sys
import uuid
from datetime import datetime, timezone

import httpx
import pytest

# Ensure the main module is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_ok(self):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


class TestCreateOrderValidation:
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
        
        # Validate UUID format
        uuid.UUID(data["id"])
        
        # Validate timestamp format (RFC 3339)
        try:
            datetime.fromisoformat(data["createdAt"].replace('Z', '+00:00'))
        except ValueError:
            pytest.fail("Invalid timestamp format")

    def test_create_order_missing_customer_id(self):
        payload = {
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_empty_items(self):
        payload = {
            "customerId": "c-1",
            "items": []
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_invalid_quantity_too_low(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 0, "unitPriceCents": 100}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_invalid_quantity_too_high(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 101, "unitPriceCents": 100}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_invalid_price_too_low(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 0}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_invalid_price_too_high(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 1000001}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_invalid_sku_length_too_short(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "", "quantity": 1, "unitPriceCents": 100}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_invalid_sku_length_too_long(self):
        sku = "A" * 33
        payload = {
            "customerId": "c-1",
            "items": [{"sku": sku, "quantity": 1, "unitPriceCents": 100}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_too_many_items(self):
        items = [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100} for _ in range(51)]
        payload = {
            "customerId": "c-1",
            "items": items
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_invalid_customer_id_length(self):
        payload = {
            "customerId": "c" * 65,
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_invalid_json(self):
        response = client.post("/orders", content="not json", headers={"Content-Type": "application/json"})
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_ignore_unknown_fields(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}],
            "unknownField": "value"
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert "unknownField" not in data


class TestGetOrder:
    def test_get_order_success(self):
        # First create an order
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]
        }
        create_resp = client.post("/orders", json=payload)
        assert create_resp.status_code == 201
        order_id = create_resp.json()["id"]
        
        # Then get it
        get_resp = client.get(f"/orders/{order_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["id"] == order_id
        assert data["customerId"] == "c-1"

    def test_get_order_not_found(self):
        fake_id = str(uuid.uuid4())
        response = client.get(f"/orders/{fake_id}")
        assert response.status_code == 404
        assert "error" in response.json()
```

FILE: requirements-dev.txt
```text
pytest>=7.4.0
httpx>=0.25.0
pytest-asyncio>=0.21.0
```