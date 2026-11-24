import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_create_order_success():
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
    assert data["totalCents"] == 2500
    assert len(data["items"]) == 1
    assert data["items"][0]["sku"] == "A-1"
    assert data["createdAt"] != ""

def test_create_order_invalid_no_customer_id():
    payload = {
        "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]
    }
    response = client.post("/orders", json=payload)
    assert response.status_code == 400  # Changed to 400 as per acceptance criteria

def test_create_order_invalid_empty_items():
    payload = {
        "customerId": "c-1",
        "items": []
    }
    response = client.post("/orders", json=payload)
    assert response.status_code == 400

def test_create_order_invalid_sku_too_long():
    payload = {
        "customerId": "c-1",
        "items": [{"sku": "A" * 33, "quantity": 1, "unitPriceCents": 100}]
    }
    response = client.post("/orders", json=payload)
    assert response.status_code == 400

def test_create_order_invalid_quantity_zero():
    payload = {
        "customerId": "c-1",
        "items": [{"sku": "A-1", "quantity": 0, "unitPriceCents": 100}]
    }
    response = client.post("/orders", json=payload)
    assert response.status_code == 400

def test_create_order_invalid_unit_price_zero():
    payload = {
        "customerId": "c-1",
        "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 0}]
    }
    response = client.post("/orders", json=payload)
    assert response.status_code == 400

def test_get_order_not_found():
    response = client.get("/orders/non-existent-id")
    assert response.status_code == 404
    assert "error" in response.json() or "detail" in response.json()

def test_get_order_success():
    # Create an order first
    payload = {
        "customerId": "c-2",
        "items": [{"sku": "B-1", "quantity": 1, "unitPriceCents": 2000}]
    }
    create_resp = client.post("/orders", json=payload)
    assert create_resp.status_code == 201
    order_id = create_resp.json()["id"]
    
    # Get the order
    response = client.get(f"/orders/{order_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == order_id
    assert data["totalCents"] == 2000
