import pytest
import httpx
import json
import time
import threading
import asyncio
import os
import signal
import subprocess
import sys

# Import the app directly for testing
from main import app

# Test client
@pytest.fixture
def client():
    with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c

# Helper to create a valid order request
def create_order_payload(customer_id="c-1", items=None):
    if items is None:
        items = [{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}]
    return {
        "customerId": customer_id,
        "items": items
    }

class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_ok(self, client):
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

class TestCreateOrder:
    @pytest.mark.asyncio
    async def test_create_order_success(self, client):
        payload = create_order_payload()
        response = await client.post("/orders", json=payload)
        
        assert response.status_code == 201
        assert "Location" in response.headers
        assert response.headers["Location"].startswith("/orders/")
        
        body = response.json()
        assert body["customerId"] == "c-1"
        assert len(body["items"]) == 1
        assert body["items"][0]["sku"] == "A-1"
        assert body["items"][0]["quantity"] == 2
        assert body["items"][0]["unitPriceCents"] == 1250
        assert body["totalCents"] == 2500
        assert "id" in body
        assert "createdAt" in body

    @pytest.mark.asyncio
    async def test_create_order_invalid_json(self, client):
        response = await client.post("/orders", content="not json", headers={"Content-Type": "application/json"})
        assert response.status_code == 400
        assert "error" in response.json()

    @pytest.mark.asyncio
    async def test_create_order_missing_customer_id(self, client):
        payload = {"items": [{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}]}
        response = await client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    @pytest.mark.asyncio
    async def test_create_order_empty_items(self, client):
        payload = {"customerId": "c-1", "items": []}
        response = await client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    @pytest.mark.asyncio
    async def test_create_order_invalid_sku_length(self, client):
        payload = {"customerId": "c-1", "items": [{"sku": "a" * 33, "quantity": 2, "unitPriceCents": 1250}]}
        response = await client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    @pytest.mark.asyncio
    async def test_create_order_invalid_quantity(self, client):
        payload = {"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 0, "unitPriceCents": 1250}]}
        response = await client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    @pytest.mark.asyncio
    async def test_create_order_invalid_unit_price(self, client):
        payload = {"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 2, "unitPriceCents": 0}]}
        response = await client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    @pytest.mark.asyncio
    async def test_create_order_too_many_items(self, client):
        items = [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100} for _ in range(51)]
        payload = {"customerId": "c-1", "items": items}
        response = await client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    @pytest.mark.asyncio
    async def test_create_order_customer_id_too_long(self, client):
        payload = {"customerId": "c" * 65, "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]}
        response = await client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    @pytest.mark.asyncio
    async def test_create_order_sku_too_short(self, client):
        payload = {"customerId": "c-1", "items": [{"sku": "", "quantity": 1, "unitPriceCents": 100}]}
        response = await client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    @pytest.mark.asyncio
    async def test_create_order_quantity_too_high(self, client):
        payload = {"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 101, "unitPriceCents": 100}]}
        response = await client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    @pytest.mark.asyncio
    async def test_create_order_unit_price_too_high(self, client):
        payload = {"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 1000001}]}
        response = await client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    @pytest.mark.asyncio
    async def test_create_order_ignore_unknown_fields(self, client):
        payload = {"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100, "extra": "field"}], "extra": "field"}
        response = await client.post("/orders", json=payload)
        assert response.status_code == 201
        body = response.json()
        assert "extra" not in body
        assert "extra" not in body["items"][0]

    @pytest.mark.asyncio
    async def test_create_order_multiple_items(self, client):
        items = [
            {"sku": "A-1", "quantity": 2, "unitPriceCents": 100},
            {"sku": "A-2", "quantity": 3, "unitPriceCents": 200}
        ]
        payload = {"customerId": "c-1", "items": items}
        response = await client.post("/orders", json=payload)
        assert response.status_code == 201
        body = response.json()
        assert body["totalCents"] == 2*100 + 3*200

class TestGetOrder:
    @pytest.mark.asyncio
    async def test_get_order_success(self, client):
        payload = create_order_payload()
        create_resp = await client.post("/orders", json=payload)
        order_id = create_resp.json()["id"]
        
        response = await client.get(f"/orders/{order_id}")
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == order_id
        assert body["customerId"] == "c-1"

    @pytest.mark.asyncio
    async def test_get_order_not_found(self, client):
        response = await client.get("/orders/non-existent-id")
        assert response.status_code == 404
        assert "error" in response.json()

class TestConcurrency:
    @pytest.mark.asyncio
    async def test_concurrent_orders(self, client):
        errors = []
        
        async def create_order():
            try:
                payload = create_order_payload()
                response = await client.post("/orders", json=payload)
                if response.status_code != 201:
                    errors.append(f"Failed: {response.status_code} {response.text}")
            except Exception as e:
                errors.append(str(e))
        
        # Run concurrent tasks
        tasks = [create_order() for _ in range(10)]
        await asyncio.gather(*tasks)
        
        assert not errors, f"Concurrency errors: {errors}"
