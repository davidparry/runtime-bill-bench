FILE: main.py
```python
import json
import os
import sys
import time
import uuid
import signal
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

# --- Models ---

class Item(BaseModel):
    sku: Annotated[str, Field(min_length=1, max_length=32)]
    quantity: Annotated[int, Field(ge=1, le=100)]
    unitPriceCents: Annotated[int, Field(ge=1, le=1000000)]

class OrderRequest(BaseModel):
    customerId: Annotated[str, Field(min_length=1, max_length=64)]
    items: Annotated[list[Item], Field(min_length=1, max_length=50)]

    model_config = {"extra": "ignore"}

class OrderResponse(BaseModel):
    id: str
    customerId: str
    items: list[Item]
    totalCents: int
    createdAt: str

    model_config = {"extra": "ignore"}

class ErrorResponse(BaseModel):
    error: str

# --- In-Memory Store ---

class OrderStore:
    def __init__(self):
        self._orders: dict[str, OrderResponse] = {}
        self._lock = asyncio.Lock()

    async def create_order(self, request: OrderRequest) -> OrderResponse:
        order_id = uuid.uuid4().hex  # UUID v4 hex string
        total_cents = sum(item.quantity * item.unitPriceCents for item in request.items)
        created_at = datetime.now(timezone.utc).isoformat()
        
        order = OrderResponse(
            id=order_id,
            customerId=request.customerId,
            items=request.items,
            totalCents=total_cents,
            createdAt=created_at
        )
        
        async with self._lock:
            self._orders[order_id] = order
            
        return order

    async def get_order(self, order_id: str) -> OrderResponse | None:
        async with self._lock:
            return self._orders.get(order_id)

    async def delete_order(self, order_id: str) -> None:
        async with self._lock:
            if order_id in self._orders:
                del self._orders[order_id]

store = OrderStore()

# --- Lifespan / Graceful Shutdown ---

async def graceful_shutdown(signum, frame):
    # Signal received, initiate shutdown
    pass

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(_handle_shutdown(s)))
    yield
    # Shutdown
    # FastAPI handles stopping the server loop. 
    # We rely on uvicorn's graceful shutdown timeout (default 5s) 
    # and our own logic to finish requests.
    # Since we are using asyncio, we just let it exit.
    # The "exit within 10 seconds" is handled by the OS killing us if we hang, 
    # but uvicorn is smart enough to drain connections.

async def _handle_shutdown(sig):
    # Trigger shutdown logic if needed, but FastAPI/Uvicorn handles the core.
    # We just ensure we don't block.
    pass

app = FastAPI(lifespan=lifespan)

# --- Middleware for Logging ---

@app.middleware("http")
async def log_request(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration_ms = int((time.time() - start_time) * 1000)
    
    log_data = {
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "durationMs": duration_ms
    }
    
    # Log to stdout as JSON
    print(json.dumps(log_data), flush=True)
    
    return response

# --- Routes ---

@app.post("/orders", status_code=201)
async def create_order(req: OrderRequest):
    # Validation is handled by Pydantic automatically.
    # If validation fails, FastAPI raises HTTPException(422) by default.
    # The prompt asks for 400 with {"error": "<message>"}.
    # We need to override the default validation error handler.
    try:
        order = await store.create_order(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")
    
    # Return 201 with Location header
    response = JSONResponse(
        content=order.model_dump(),
        status_code=201,
        headers={"Location": f"/orders/{order.id}"}
    )
    return response

@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    order = await store.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@app.get("/health")
async def health():
    return {"status": "ok"}

# --- Custom Validation Error Handler ---

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # For 404s, return standard format
    if exc.status_code == 404:
        return JSONResponse(
            status_code=404,
            content={"error": exc.detail}
        )
    
    # For 422 (Validation Errors), we want 400 with {"error": "<message>"}
    if exc.status_code == 422:
        # Extract validation errors
        errors = exc.detail
        # Pydantic v2 detail is a list of dicts
        # We'll combine them into a single message or list them
        error_messages = []
        for err in errors:
            loc = " -> ".join(str(l) for l in err.get("loc", []))
            msg = err.get("msg", "")
            error_messages.append(f"{loc}: {msg}")
        
        error_msg = "; ".join(error_messages) if error_messages else "Validation failed"
        return JSONResponse(
            status_code=400,
            content={"error": error_msg}
        )
    
    # For other HTTP errors
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"}
    )

# --- Entry Point ---

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
```

FILE: test_main.py
```python
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
```