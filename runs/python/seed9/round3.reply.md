FILE: main.py
```python
import os
import uuid
import time
import json
import signal
import sys
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Annotated, Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field

# --- Models ---

class OrderItem(BaseModel):
    sku: Annotated[str, Field(min_length=1, max_length=32)]
    quantity: Annotated[int, Field(ge=1, le=100)]
    unitPriceCents: Annotated[int, Field(ge=1, le=1000000)]

class CreateOrderRequest(BaseModel):
    customerId: Annotated[str, Field(min_length=1, max_length=64)]
    items: Annotated[list[OrderItem], Field(min_length=1, max_length=50)]

    class ConfigDict:
        extra = "ignore"

class OrderResponse(BaseModel):
    id: str
    customerId: str
    items: list[OrderItem]
    totalCents: int
    createdAt: str

# --- In-Memory Store ---

class OrderStore:
    def __init__(self):
        self._orders: dict[str, dict[str, Any]] = {}
        self._lock = None  # Will be initialized in lifespan
        import asyncio
        self._lock = asyncio.Lock()

    async def create_order(self, request: CreateOrderRequest) -> OrderResponse:
        order_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        created_at_str = now.strftime("%Y-%m-%dT%H:%M:%S") + "Z" # RFC 3339 UTC
        
        # Calculate total
        total = 0
        for item in request.items:
            total += item.quantity * item.unitPriceCents
        
        order_data = {
            "id": order_id,
            "customerId": request.customerId,
            "items": [item.model_dump() for item in request.items],
            "totalCents": total,
            "createdAt": created_at_str
        }

        async with self._lock:
            self._orders[order_id] = order_data

        return OrderResponse(**order_data)

    async def get_order(self, order_id: str) -> OrderResponse | None:
        async with self._lock:
            order_data = self._orders.get(order_id)
            if order_data:
                return OrderResponse(**order_data)
            return None

# --- App Setup ---

store = OrderStore()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    yield
    # Shutdown

app = FastAPI(lifespan=lifespan)

# --- Middleware for Logging ---

@app.middleware("http")
async def log_request(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start_time) * 1000
    
    log_entry = {
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "durationMs": round(duration_ms, 2),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    # Write JSON log line to stdout
    print(json.dumps(log_entry), flush=True)
    
    return response

# --- Error Handlers ---

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    # Extract a simple error message
    if errors:
        first_error = errors[0]
        msg = first_error.get('msg', 'Validation error')
    else:
        msg = 'Validation error'
        
    return JSONResponse(
        status_code=400,
        content={"error": msg}
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail}
    )

# --- Routes ---

@app.post("/orders", status_code=201)
async def create_order(request: CreateOrderRequest):
    order = await store.create_order(request)
    return JSONResponse(
        content=order.model_dump(),
        status_code=201,
        headers={"Location": f"/orders/{order.id}"}
    )

@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    order = await store.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@app.get("/health")
async def health_check():
    return {"status": "ok"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
```

FILE: test_main.py
```python
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
```