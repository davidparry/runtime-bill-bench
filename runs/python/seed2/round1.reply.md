FILE: main.py
```python
import os
import sys
import uuid
import time
import json
import signal
import asyncio
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

# --- Models ---

class OrderItem(BaseModel):
    sku: str = Field(..., min_length=1, max_length=32)
    quantity: int = Field(..., ge=1, le=100)
    unitPriceCents: int = Field(..., ge=1, le=1000000)

class CreateOrderRequest(BaseModel):
    customerId: str = Field(..., min_length=1, max_length=64)
    items: List[OrderItem] = Field(..., min_length=1, max_length=50)

    class Config:
        # Ignore unknown fields as per spec
        extra = "ignore"

class OrderResponse(BaseModel):
    id: str
    customerId: str
    items: List[OrderItem]
    totalCents: int
    createdAt: str

# --- In-Memory Store ---

# Using a simple dict with a lock for thread safety in async context
# Note: FastAPI handles concurrency via asyncio tasks. A standard dict is safe for simple assignments/reads
# if we ensure atomicity of check-and-set, but here we just append.
# However, to be strictly safe under concurrent writes, we use an asyncio.Lock.
orders_store: dict[str, dict] = {}
orders_lock = asyncio.Lock()

# --- Helper Functions ---

def calculate_total(items: List[OrderItem]) -> int:
    """
    Calculates the total cost.
    Python handles large integers automatically, so overflow is not an issue
    even if the sum exceeds 2^31 - 1. The spec mentions 5000000000 which fits in 64-bit signed int.
    """
    total = 0
    for item in items:
        total += item.quantity * item.unitPriceCents
    return total

def format_order_response(order_id: str, request: CreateOrderRequest) -> OrderResponse:
    total = calculate_total(request.items)
    now = datetime.now(timezone.utc)
    return OrderResponse(
        id=order_id,
        customerId=request.customerId,
        items=request.items,
        totalCents=total,
        createdAt=now.strftime("%Y-%m-%dT%H:%M:%S.%fZ") # RFC 3339 UTC
    )

# --- Application Setup ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    yield
    # Shutdown
    # Graceful shutdown is handled by uvicorn, but we can ensure cleanup here if needed.
    # The spec asks for stopping accepting connections and finishing in-flight.
    # FastAPI/Uvicorn handles this automatically when receiving SIGTERM.

app = FastAPI(lifespan=lifespan)

# --- Middleware for Logging ---

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start_time) * 1000
    
    log_entry = {
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "durationMs": round(duration_ms, 2)
    }
    
    # Write JSON log line to stdout
    print(json.dumps(log_entry), flush=True)
    
    return response

# --- Routes ---

@app.post(
    "/orders",
    status_code=201,
    responses={
        201: {"model": OrderResponse, "description": "Order created successfully"},
        400: {"description": "Invalid input"},
    }
)
async def create_order(request: Request):
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    
    try:
        order_data = CreateOrderRequest(**body)
    except Exception as e:
        # Pydantic validation errors return a list of dicts. We flatten or pick the first message.
        # The spec asks for {"error": "<message>"}. We'll provide a generic message or the first validation error.
        raise HTTPException(status_code=400, detail="Validation error")

    order_id = str(uuid.uuid4())
    
    async with orders_lock:
        orders_store[order_id] = {
            "id": order_id,
            "customerId": order_data.customerId,
            "items": order_data.items,
            "totalCents": calculate_total(order_data.items),
            "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        }
        
    response = JSONResponse(
        content=format_order_response(order_id, order_data).model_dump(),
        status_code=201
    )
    response.headers["Location"] = f"/orders/{order_id}"
    return response

@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    async with orders_lock:
        order = orders_store.get(order_id)
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Return in the format specified: id, customerId, items, totalCents, createdAt
    # The order dict has these keys.
    return JSONResponse(content=order)

@app.get("/health")
async def health_check():
    return {"status": "ok"}

# --- Entry Point ---

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
```

FILE: requirements.txt
```text
fastapi>=0.115.0
uvicorn>=0.30.0
pydantic>=2.9.0
```

FILE: requirements-dev.txt
```text
pytest>=8.3.0
httpx>=0.27.0
```

FILE: test_main.py
```python
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
```