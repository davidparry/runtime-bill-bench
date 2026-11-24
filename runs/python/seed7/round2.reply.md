FILE: main.py
```python
import os
import sys
import uuid
import time
import json
import logging
import signal
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

# Configure logging to output JSON lines to stdout
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_record = {
            "method": getattr(record, "method", None),
            "path": getattr(record, "path", None),
            "status": getattr(record, "status_code", None),
            "durationMs": getattr(record, "duration_ms", None),
        }
        # Filter out None values to keep logs clean
        return json.dumps({k: v for k, v in log_record.items() if v is not None})

logger = logging.getLogger("orders_service")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
logger.addHandler(handler)

# --- Data Models ---

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
        # Ensure integers are serialized correctly even if large
        use_enum_values = False

# --- In-Memory Store ---

class OrderStore:
    def __init__(self):
        self._orders: Dict[str, OrderResponse] = {}
        self._lock = asyncio.Lock()

    async def create_order(self, request: OrderRequest) -> OrderResponse:
        order_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        total_cents = 0
        for item in request.items:
            total_cents += item.quantity * item.unitPriceCents

        # Construct response manually to ensure exact field names and types
        # Pydantic v2 handles serialization, but we need to ensure totalCents is int
        response_data = {
            "id": order_id,
            "customerId": request.customerId,
            "items": [item.model_dump() for item in request.items],
            "totalCents": total_cents,
            "createdAt": now
        }
        
        order = OrderResponse(**response_data)
        
        async with self._lock:
            self._orders[order_id] = order
            
        return order

    async def get_order(self, order_id: str) -> Optional[OrderResponse]:
        async with self._lock:
            return self._orders.get(order_id)

store = OrderStore()

# --- FastAPI App ---

app = FastAPI()

@app.middleware("http")
async def log_requests(request: Request, call_next):
    import time
    start_time = time.time()
    
    # Attach context to request for logging
    request.state.method = request.method
    request.state.path = request.url.path
    
    response = await call_next(request)
    
    duration_ms = (time.time() - start_time) * 1000
    
    # Log the request
    log_data = {
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "durationMs": round(duration_ms, 2)
    }
    logger.info("Request completed", extra=log_data)
    
    return response

@app.post("/orders", status_code=201)
async def create_order(request: Request):
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    
    try:
        order_req = OrderRequest(**body)
    except Exception as e:
        # Pydantic validation errors
        # Extract message from the first error for simplicity
        if hasattr(e, 'errors') and e.errors():
            error_msg = e.errors()[0]['msg']
        else:
            error_msg = str(e)
        raise HTTPException(status_code=400, detail=error_msg)

    order = await store.create_order(order_req)
    
    # Return 201 with Location header
    return JSONResponse(
        status_code=201,
        content=order.model_dump(),
        headers={"Location": f"/orders/{order.id}"}
    )

@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    order = await store.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order.model_dump()

@app.get("/health")
async def health():
    return {"status": "ok"}

# --- Custom Exception Handlers to return "error" field ---

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": "Internal Server Error"}
    )

# --- Graceful Shutdown ---

def setup_shutdown():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    event = asyncio.Event()

    def handle_signal(signum, frame):
        logger.info("Shutdown signal received")
        event.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    
    return event

shutdown_event = setup_shutdown()

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.environ.get("PORT", 8080))
    
    async def main():
        config = uvicorn.Config(
            "main:app",
            host="0.0.0.0",
            port=port,
            log_level="info",
            access_log=False
        )
        server = uvicorn.Server(config)
        
        # Start server
        task = asyncio.create_task(server.serve())
        
        # Wait for shutdown signal
        await shutdown_event.wait()
        
        # Graceful shutdown
        logger.info("Initiating graceful shutdown")
        server.should_exit = True
        await server.shutdown()
        logger.info("Shutdown complete")

    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        pass
```

FILE: tests/test_orders.py
```python
import pytest
import json
import time
import uuid
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

# --- Validation Tests ---

class TestValidation:
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
        assert "/orders/" in response.headers["Location"]
        
        data = response.json()
        assert data["customerId"] == "c-1"
        assert len(data["items"]) == 1
        assert data["items"][0]["sku"] == "A-1"
        assert data["totalCents"] == 2500
        assert "id" in data
        assert "createdAt" in data

    def test_create_order_invalid_json(self):
        response = client.post("/orders", content="not json", headers={"Content-Type": "application/json"})
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_missing_customerId(self):
        payload = {"items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]}
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_empty_items(self):
        payload = {"customerId": "c-1", "items": []}
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_invalid_sku_length(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "a" * 33, "quantity": 1, "unitPriceCents": 100}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_invalid_quantity(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 0, "unitPriceCents": 100}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_invalid_unit_price(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 0}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_too_many_items(self):
        items = [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100} for _ in range(51)]
        payload = {"customerId": "c-1", "items": items}
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_ignores_unknown_fields(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100, "extra": "field"}],
            "unknown": "top"
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 201

    def test_create_order_large_total(self):
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 100, "unitPriceCents": 1000000}]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 201
        assert response.json()["totalCents"] == 100000000

# --- 404 Tests ---

class TestNotFound:
    def test_get_order_not_found(self):
        fake_id = str(uuid.uuid4())
        response = client.get(f"/orders/{fake_id}")
        assert response.status_code == 404
        assert "error" in response.json()

    def test_get_order_non_existent_id(self):
        # Use a format that is definitely not in the store
        response = client.get("/orders/non-existent-id")
        assert response.status_code == 404
        assert "error" in response.json()

# --- Health Check Test ---

class TestHealth:
    def test_health_ok(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
```