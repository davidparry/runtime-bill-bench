FILE: main.py
```python
import os
import sys
import uuid
import time
import json
import logging
import signal
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

# Configure logging to output JSON lines to stdout
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "method": getattr(record, "method", None),
            "path": getattr(record, "path", None),
            "status": getattr(record, "status", None),
            "durationMs": getattr(record, "duration_ms", None),
            "message": record.getMessage(),
            "level": record.levelname,
        }
        # Filter out None values for cleaner logs if needed, though spec says "at least" these keys.
        # We keep them if they are present in the record context.
        return json.dumps(log_data)

logger = logging.getLogger("orders_service")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
logger.addHandler(handler)

# --- Pydantic Models ---

class Item(BaseModel):
    sku: str = Field(..., min_length=1, max_length=32)
    quantity: int = Field(..., ge=1, le=100)
    unitPriceCents: int = Field(..., ge=1, le=1000000)

    class Config:
        # Ignore unknown fields as per spec
        extra = "ignore"

class OrderRequest(BaseModel):
    customerId: str = Field(..., min_length=1, max_length=64)
    items: List[Item] = Field(..., min_length=1, max_length=50)

    class Config:
        # Ignore unknown fields as per spec
        extra = "ignore"

class OrderResponse(BaseModel):
    id: str
    customerId: str
    items: List[Item]
    totalCents: int
    createdAt: str

    class Config:
        # Ensure JSON serialization handles large integers correctly (Python ints are arbitrary precision, JSON encoder handles them)
        json_encoders = {
            int: lambda v: v
        }

# --- In-Memory Store ---

class OrderStore:
    def __init__(self):
        self._orders: Dict[str, Dict[str, Any]] = {}
        self._lock = None  # We will use asyncio.Lock if needed, but since FastAPI is async, we need to be careful.
        # However, simple dict assignment is atomic in CPython for small objects, but for safety under concurrency:
        # We'll use a standard dict. Since Python's GIL protects basic dict operations, and we are just reading/writing references,
        # it is generally safe for this scale. For strict production safety with complex mutations, a lock would be better.
        # Given the simplicity (write once, read many), a simple dict is sufficient.
        self._store_lock = __import__('threading').Lock()

    def create_order(self, order_id: str, request: OrderRequest, created_at: datetime) -> OrderResponse:
        total_cents = sum(item.quantity * item.unitPriceCents for item in request.items)
        
        order_data = {
            "id": order_id,
            "customerId": request.customerId,
            "items": [item.model_dump() for item in request.items],
            "totalCents": total_cents,
            "createdAt": created_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ") if created_at.tzinfo is None else created_at.isoformat().replace('+00:00', 'Z')
        }
        
        # Ensure totalCents is treated as a standard integer in JSON output
        # Python handles large ints natively, Pydantic handles them natively.
        
        with self._store_lock:
            self._orders[order_id] = order_data
            
        return OrderResponse(
            id=order_id,
            customerId=request.customerId,
            items=request.items,
            totalCents=total_cents,
            createdAt=order_data["createdAt"]
        )

    def get_order(self, order_id: str) -> Optional[OrderResponse]:
        with self._store_lock:
            data = self._orders.get(order_id)
        
        if data is None:
            return None
            
        return OrderResponse(
            id=data["id"],
            customerId=data["customerId"],
            items=[Item(**item) for item in data["items"]],
            totalCents=data["totalCents"],
            createdAt=data["createdAt"]
        )

store = OrderStore()

# --- FastAPI App ---

app = FastAPI(title="Orders Service")

@app.middleware("http")
async def log_requests(request: Request, call_next):
    import time
    start_time = time.time()
    
    # Add custom attributes to the request context if needed for the logger
    # We will patch the record later or use a different approach.
    # FastAPI's default logging doesn't easily support custom JSON fields per request without middleware.
    response = await call_next(request)
    
    duration_ms = int((time.time() - start_time) * 1000)
    
    # Log manually to ensure format matches spec exactly
    log_data = {
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "durationMs": duration_ms
    }
    
    # We need to push this log entry. Since we are in a middleware, we can't easily inject into the request context
    # for the standard logger without complex contextvars setup.
    # Instead, we'll use the logger directly here.
    logger.info(
        f"{request.method} {request.url.path} {response.status_code} {duration_ms}ms",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": duration_ms
        }
    )
    
    return response

@app.post("/orders", status_code=201)
async def create_order(request: OrderRequest):
    order_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc)
    
    response = store.create_order(order_id, request, created_at)
    
    # Return JSONResponse to set Location header correctly
    return JSONResponse(
        content=response.model_dump(),
        status_code=201,
        headers={"Location": f"/orders/{order_id}"}
    )

@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    order = store.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    
    return order

@app.get("/health")
async def health():
    return {"status": "ok"}

# --- Graceful Shutdown ---

def handle_sigterm(signum, frame):
    logger.info("Received SIGTERM, initiating shutdown")
    # FastAPI handles shutdown via lifespan, but we can trigger it here if needed
    # or just let the signal interrupt the main thread.
    # The spec asks to stop accepting connections and finish in-flight.
    # uvicorn handles this if we exit cleanly or if the server is stopped.
    # We will register a shutdown handler in the lifespan.
    pass

# lifespan context manager for graceful shutdown
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    loop = __import__('asyncio').get_running_loop()
    
    def signal_handler():
        loop.create_task(app.shutdown())
        
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)
        
    yield
    
    # Shutdown
    logger.info("Shutting down gracefully")
    # uvicorn will stop accepting new connections. We wait for existing ones to complete.
    # The `app.shutdown()` call above triggers uvicorn's shutdown sequence.

app.router.lifespan_context = lifespan

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
import json

from main import app

client = TestClient(app)

class TestHealth:
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
        assert response.headers["Location"].startswith("/orders/")
        
        data = response.json()
        assert data["customerId"] == "c-1"
        assert len(data["items"]) == 1
        assert data["items"][0]["sku"] == "A-1"
        assert data["items"][0]["quantity"] == 2
        assert data["items"][0]["unitPriceCents"] == 1250
        assert data["totalCents"] == 2500
        assert "id" in data
        assert "createdAt" in data
        
    def test_create_order_multiple_items(self):
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
        assert data["totalCents"] == 100 + 400 == 500

    def test_create_order_invalid_json(self):
        response = client.post("/orders", content="not json", headers={"content-type": "application/json"})
        assert response.status_code == 422  # FastAPI default validation error for invalid JSON body in Pydantic

    def test_create_order_missing_customer_id(self):
        payload = {
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 422

    def test_create_order_empty_items(self):
        payload = {
            "customerId": "c-1",
            "items": []
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 422

    def test_create_order_invalid_sku_length(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "a" * 33, "quantity": 1, "unitPriceCents": 100}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 422

    def test_create_order_invalid_quantity_zero(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 0, "unitPriceCents": 100}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 422

    def test_create_order_invalid_quantity_too_high(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 101, "unitPriceCents": 100}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 422

    def test_create_order_invalid_unit_price_zero(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 0}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 422

    def test_create_order_invalid_unit_price_too_high(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 1000001}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 422

    def test_create_order_too_many_items(self):
        items = [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100} for _ in range(51)]
        payload = {
            "customerId": "c-1",
            "items": items
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 422

    def test_create_order_ignore_unknown_fields(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100, "extra": "field"}],
            "unknownRoot": "value"
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["customerId"] == "c-1"

    def test_create_order_large_total_cents(self):
        # Max quantity 100 * Max price 1000000 = 100,000,000 per item
        # 50 items * 100,000,000 = 5,000,000,000
        items = [{"sku": "A-1", "quantity": 100, "unitPriceCents": 1000000} for _ in range(50)]
        payload = {
            "customerId": "c-1",
            "items": items
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["totalCents"] == 5000000000

class TestGetOrder:
    def test_get_order_success(self):
        # Create an order first
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]
        }
        create_response = client.post("/orders", json=payload)
        order_id = create_response.json()["id"]
        
        # Get the order
        response = client.get(f"/orders/{order_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == order_id
        assert data["customerId"] == "c-1"

    def test_get_order_not_found(self):
        response = client.get("/orders/non-existent-id")
        assert response.status_code == 404
        data = response.json()
        assert "error" in data or "detail" in data  # FastAPI returns "detail" for HTTPException

    def test_get_order_invalid_uuid_format(self):
        # Even if the ID doesn't look like a UUID, if it's not in the store, it's 404
        response = client.get("/orders/not-a-uuid")
        assert response.status_code == 404
```