FILE: main.py
```python
"""
Orders Service - FastAPI Application

This module defines the ASGI application for the Orders service.
It handles order creation, retrieval, and health checks using an in-memory store.
"""

import asyncio
import json
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ConfigDict

# --- Models ---

class Item(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    sku: str = Field(..., min_length=1, max_length=32)
    quantity: int = Field(..., ge=1, le=100)
    unitPriceCents: int = Field(..., ge=1, le=1000000)

class OrderCreateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    customerId: str = Field(..., min_length=1, max_length=64)
    items: list[Item] = Field(..., min_length=1, max_length=50)

class OrderResponse(BaseModel):
    id: str
    customerId: str
    items: list[Item]
    totalCents: int
    createdAt: str

# --- Store ---

class InMemoryStore:
    def __init__(self):
        self._orders: dict[str, OrderResponse] = {}
        self._lock = asyncio.Lock()

    async def create_order(self, request: OrderCreateRequest) -> OrderResponse:
        order_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        created_at = now.strftime("%Y-%m-%dT%H:%M:%S.%fZ") # RFC 3339 with microseconds
        
        # Calculate total
        total = 0
        for item in request.items:
            total += item.quantity * item.unitPriceCents
        
        order = OrderResponse(
            id=order_id,
            customerId=request.customerId,
            items=request.items,
            totalCents=total,
            createdAt=created_at
        )
        
        async with self._lock:
            self._orders[order_id] = order
            
        return order

    async def get_order(self, order_id: str) -> OrderResponse | None:
        async with self._lock:
            return self._orders.get(order_id)

# --- Lifespan & App ---

store = InMemoryStore()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    yield
    # Shutdown: graceful shutdown is handled by uvicorn, but we can log if needed
    sys.stdout.flush()

app = FastAPI(title="Orders Service", lifespan=lifespan)

# --- Middleware for Logging ---

@app.middleware("http")
async def log_request(request: Request, call_next):
    start_time = time.time()
    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = (time.time() - start_time) * 1000
        log_entry = {
            "method": request.method,
            "path": request.url.path,
            "status": 500,
            "durationMs": round(duration_ms, 2),
            "error": str(exc)
        }
        sys.stdout.write(json.dumps(log_entry) + "\n")
        sys.stdout.flush()
        raise exc
    
    duration_ms = (time.time() - start_time) * 1000
    log_entry = {
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "durationMs": round(duration_ms, 2)
    }
    sys.stdout.write(json.dumps(log_entry) + "\n")
    sys.stdout.flush()
    
    return response

# --- Validation Error Handler ---

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Extract error messages
    errors = exc.errors()
    # Create a simple error message string
    error_msg = "; ".join([f"{e['loc'][-1]}: {e['msg']}" for e in errors])
    
    return JSONResponse(
        status_code=400,
        content={"error": error_msg}
    )

# --- Endpoints ---

@app.post("/orders", status_code=201)
async def create_order(request: OrderCreateRequest):
    """
    Create a new order.
    Returns 201 with Location header and order details.
    """
    order = await store.create_order(request)
    
    response = JSONResponse(
        content=order.model_dump(),
        status_code=201
    )
    response.headers["Location"] = f"/orders/{order.id}"
    return response

@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    """
    Retrieve an order by ID.
    Returns 404 if not found.
    """
    order = await store.get_order(order_id)
    
    if not order:
        return JSONResponse(
            content={"error": "Order not found"},
            status_code=404
        )
        
    return JSONResponse(
        content=order.model_dump(),
        status_code=200
    )

@app.get("/health")
async def health_check():
    """
    Health check endpoint.
    """
    return {"status": "ok"}

# --- Entry Point ---

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
```

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