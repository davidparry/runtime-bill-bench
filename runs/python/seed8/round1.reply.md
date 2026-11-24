FILE: main.py
```python
import asyncio
import json
import os
import signal
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

# --- Models ---

class OrderItem(BaseModel):
    sku: str = Field(..., min_length=1, max_length=32)
    quantity: int = Field(..., ge=1, le=100)
    unitPriceCents: int = Field(..., ge=1, le=1000000)

class CreateOrderRequest(BaseModel):
    customerId: str = Field(..., min_length=1, max_length=64)
    items: list[OrderItem] = Field(..., min_length=1, max_length=50)

    @field_validator("items")
    @classmethod
    def validate_items_not_empty(cls, v: list[OrderItem]) -> list[OrderItem]:
        if not v:
            raise ValueError("items must not be empty")
        return v

class OrderResponse(BaseModel):
    id: str
    customerId: str
    items: list[OrderItem]
    totalCents: int
    createdAt: str

# --- Store ---

class InMemoryStore:
    def __init__(self):
        self._orders: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def create_order(self, request: CreateOrderRequest) -> OrderResponse:
        order_id = uuid.uuid4().hex
        total_cents = sum(item.quantity * item.unitPriceCents for item in request.items)
        now = datetime.now(timezone.utc)
        created_at = now.isoformat()

        order_data = {
            "id": order_id,
            "customerId": request.customerId,
            "items": [item.model_dump() for item in request.items],
            "totalCents": total_cents,
            "createdAt": created_at,
        }

        async with self._lock:
            self._orders[order_id] = order_data

        return OrderResponse(
            id=order_id,
            customerId=request.customerId,
            items=request.items,
            totalCents=total_cents,
            createdAt=created_at,
        )

    async def get_order(self, order_id: str) -> OrderResponse | None:
        async with self._lock:
            order_data = self._orders.get(order_id)
        
        if not order_data:
            return None
        
        return OrderResponse(**order_data)

store = InMemoryStore()

# --- App Setup ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic if needed
    yield
    # Shutdown logic handled by signal handler in main block or here if preferred.
    # We'll handle graceful shutdown via the signal handler in the main block 
    # to ensure uvicorn's shutdown hook interacts correctly.

app = FastAPI(lifespan=lifespan)

# --- Logging Middleware ---

@app.middleware("http")
async def log_request(request: Request, call_next):
    start_time = time.time()
    try:
        response = await call_next(request)
        return response
    finally:
        duration_ms = (time.time() - start_time) * 1000
        log_entry = {
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "durationMs": round(duration_ms, 2),
        }
        # Write JSON log line to stdout
        print(json.dumps(log_entry), flush=True)

# --- Routes ---

@app.post("/orders", status_code=201)
async def create_order(request: Request):
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid JSON body"}
        )

    try:
        validated_data = CreateOrderRequest(**body)
    except Exception as e:
        # Pydantic validation errors contain details in .errors()
        # We flatten them or take the first one for a simple message.
        # The prompt asks for {"error": "<message>"}.
        errors = e.errors()
        error_msg = f"Validation error: {errors[0]['msg']}" if errors else "Validation failed"
        return JSONResponse(
            status_code=400,
            content={"error": error_msg}
        )

    order = await store.create_order(validated_data)
    
    response = JSONResponse(
        status_code=201,
        content=order.model_dump()
    )
    response.headers["Location"] = f"/orders/{order.id}"
    return response

@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    order = await store.get_order(order_id)
    if not order:
        return JSONResponse(
            status_code=404,
            content={"error": "Order not found"}
        )
    return JSONResponse(
        status_code=200,
        content=order.model_dump()
    )

@app.get("/health")
async def health_check():
    return JSONResponse(
        status_code=200,
        content={"status": "ok"}
    )

if __name__ == "__main__":
    import uvicorn
    import signal as signal_module

    host = "0.0.0.0"
    port = int(os.environ.get("PORT", 8080))

    # Graceful shutdown setup
    shutdown_event = asyncio.Event()

    def handle_signal(signum, frame):
        shutdown_event.set()

    signal_module.signal(signal_module.SIGTERM, handle_signal)
    signal_module.signal(signal_module.SIGINT, handle_signal)

    async def run():
        config = uvicorn.Config(app, host=host, port=port, log_level="info")
        server = uvicorn.Server(config)
        
        # Handle shutdown
        async def shutdown():
            server.should_exit = True
            await asyncio.sleep(10) # Wait up to 10 seconds for in-flight requests
            sys.exit(0)

        # Start server
        task = asyncio.create_task(server.serve())
        
        # Wait for shutdown signal
        await shutdown_event.wait()
        print("Shutting down gracefully...", flush=True)
        await shutdown()

    asyncio.run(run())
```

FILE: requirements.txt
```
fastapi>=0.115.0,<1.0.0
uvicorn>=0.30.0,<1.0.0
pydantic>=2.9.0,<3.0.0
```

FILE: requirements-dev.txt
```
pytest>=8.3.0,<9.0.0
httpx>=0.27.0,<1.0.0
```

FILE: test_main.py
```python
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
```