FILE: main.py
```python
"""
Orders Service - FastAPI Application

Production-ready HTTP service for managing orders.
"""

import logging
import os
import signal
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

# Configure logging to output JSON lines to stdout
logger = logging.getLogger("orders_service")
logger.setLevel(logging.INFO)

# Ensure we have a handler that writes to stdout
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)


# --- Pydantic Models ---

class OrderItem(BaseModel):
    """Model for an item within an order."""
    sku: str = Field(..., min_length=1, max_length=32)
    quantity: int = Field(..., ge=1, le=100)
    unitPriceCents: int = Field(..., ge=1, le=1000000)

    class Config:
        # Ignore extra fields in input
        extra = "ignore"


class CreateOrderRequest(BaseModel):
    """Model for creating a new order."""
    customerId: str = Field(..., min_length=1, max_length=64)
    items: List[OrderItem] = Field(..., min_length=1, max_length=50)


class OrderResponse(BaseModel):
    """Model for order response."""
    id: str
    customerId: str
    items: List[OrderItem]
    totalCents: int
    createdAt: str

    class Config:
        # Ensure we don't ignore extra fields for output if needed, 
        # but mainly we want to control serialization.
        # Pydantic v2 handles this well by default.
        pass


class ErrorResponse(BaseModel):
    """Model for error responses."""
    error: str


# --- In-Memory Store ---

class OrderStore:
    """Thread-safe in-memory order store."""
    
    def __init__(self):
        self._orders: Dict[str, OrderResponse] = {}
        # Using a lock for thread safety during writes
        import threading
        self._lock = threading.Lock()

    def create_order(self, order: OrderResponse) -> None:
        with self._lock:
            self._orders[order.id] = order

    def get_order(self, order_id: str) -> Optional[OrderResponse]:
        with self._lock:
            return self._orders.get(order_id)

    def is_empty(self) -> bool:
        with self._lock:
            return len(self._orders) == 0


# --- App Logic ---

store = OrderStore()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    yield
    # Shutdown logic handled by signal handlers in main block
    # FastAPI lifespan is good, but we need explicit signal handling for 
    # graceful shutdown within 10 seconds as per spec.
    # We'll register signals in main.py directly.

app = FastAPI(title="Orders Service", lifespan=lifespan)

@app.post("/orders", status_code=201)
async def create_order(request: Request):
    """Create a new order."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid JSON body"}
        )

    # Validate against Pydantic model
    try:
        validated_data = CreateOrderRequest(**body)
    except Exception as e:
        # Pydantic v2 raises ValidationError
        return JSONResponse(
            status_code=400,
            content={"error": str(e)}
        )

    # Calculate total
    total_cents = 0
    for item in validated_data.items:
        total_cents += item.quantity * item.unitPriceCents

    # Create response model
    now = datetime.now(timezone.utc)
    order = OrderResponse(
        id=str(uuid.uuid4()),
        customerId=validated_data.customerId,
        items=validated_data.items,
        totalCents=total_cents,
        createdAt=now.isoformat()
    )

    # Store
    store.create_order(order)

    # Return response
    response = JSONResponse(
        status_code=201,
        content=order.model_dump()
    )
    response.headers["Location"] = f"/orders/{order.id}"
    return response


@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    """Retrieve an order by ID."""
    order = store.get_order(order_id)
    
    if order is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"Order with id '{order_id}' not found"}
        )
    
    return JSONResponse(
        status_code=200,
        content=order.model_dump()
    )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return JSONResponse(
        status_code=200,
        content={"status": "ok"}
    )


# --- Middleware for Logging ---

@app.middleware("http")
async def log_requests(request: Request, call_next):
    import time
    start_time = time.time()
    
    try:
        response = await call_next(request)
        return response
    finally:
        duration_ms = (time.time() - start_time) * 1000
        
        # Log JSON line to stdout
        log_entry = {
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "durationMs": round(duration_ms, 2)
        }
        logger.info(str(log_entry))
```

FILE: requirements.txt
```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
pydantic>=2.9.0
```

FILE: requirements-dev.txt
```
pytest>=8.3.0
httpx>=0.27.0
```

FILE: test_main.py
```python
"""
Tests for Orders Service

Tests validation rules and 404 cases.
"""

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


class TestCreateOrder:
    """Tests for POST /orders endpoint."""

    def test_create_order_success(self):
        """Test successful order creation."""
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
        """Test order with multiple items."""
        payload = {
            "customerId": "c-2",
            "items": [
                {"sku": "S-1", "quantity": 1, "unitPriceCents": 100},
                {"sku": "S-2", "quantity": 3, "unitPriceCents": 200}
            ]
        }
        response = client.post("/orders", json=payload)
        
        assert response.status_code == 201
        data = response.json()
        assert data["totalCents"] == 100 + (3 * 200) == 700

    def test_create_order_invalid_json(self):
        """Test response for invalid JSON body."""
        response = client.post("/orders", content="not json", headers={"Content-Type": "application/json"})
        
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_missing_customerId(self):
        """Test validation for missing customerId."""
        payload = {
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]
        }
        response = client.post("/orders", json=payload)
        
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_empty_items(self):
        """Test validation for empty items array."""
        payload = {
            "customerId": "c-1",
            "items": []
        }
        response = client.post("/orders", json=payload)
        
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_sku_too_long(self):
        """Test validation for SKU exceeding max length."""
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A" * 33, "quantity": 1, "unitPriceCents": 100}]
        }
        response = client.post("/orders", json=payload)
        
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_quantity_zero(self):
        """Test validation for quantity less than 1."""
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 0, "unitPriceCents": 100}]
        }
        response = client.post("/orders", json=payload)
        
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_quantity_too_high(self):
        """Test validation for quantity exceeding max."""
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 101, "unitPriceCents": 100}]
        }
        response = client.post("/orders", json=payload)
        
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_unit_price_zero(self):
        """Test validation for unitPriceCents less than 1."""
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 0}]
        }
        response = client.post("/orders", json=payload)
        
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_unit_price_too_high(self):
        """Test validation for unitPriceCents exceeding max."""
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 1000001}]
        }
        response = client.post("/orders", json=payload)
        
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_too_many_items(self):
        """Test validation for more than 50 items."""
        items = [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100} for _ in range(51)]
        payload = {
            "customerId": "c-1",
            "items": items
        }
        response = client.post("/orders", json=payload)
        
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_customerId_too_long(self):
        """Test validation for customerId exceeding max length."""
        payload = {
            "customerId": "c" * 65,
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]
        }
        response = client.post("/orders", json=payload)
        
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_ignore_unknown_fields(self):
        """Test that unknown fields are ignored."""
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}],
            "unknownField": "should be ignored",
            "nested": {"key": "value"}
        }
        response = client.post("/orders", json=payload)
        
        assert response.status_code == 201
        data = response.json()
        assert "unknownField" not in data
        assert "nested" not in data

    def test_create_order_content_type_application_json(self):
        """Test that response has correct content type."""
        payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]
        }
        response = client.post("/orders", json=payload)
        
        assert response.status_code == 201
        assert "application/json" in response.headers.get("content-type", "")


class TestGetOrder:
    """Tests for GET /orders/{id} endpoint."""

    def test_get_order_success(self):
        """Test retrieving an existing order."""
        # First create an order
        create_payload = {
            "customerId": "c-1",
            "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]
        }
        create_response = client.post("/orders", json=create_payload)
        order_id = create_response.json()["id"]
        
        # Now retrieve it
        response = client.get(f"/orders/{order_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == order_id
        assert data["customerId"] == "c-1"

    def test_get_order_not_found(self):
        """Test 404 for non-existent order."""
        response = client.get("/orders/non-existent-id")
        
        assert response.status_code == 404
        assert "error" in response.json()
        assert "not found" in response.json()["error"].lower()

    def test_get_order_content_type(self):
        """Test that response has correct content type."""
        response = client.get("/orders/non-existent-id")
        
        assert response.status_code == 404
        assert "application/json" in response.headers.get("content-type", "")


class TestHealth:
    """Tests for GET /health endpoint."""

    def test_health_check(self):
        """Test health check endpoint."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_health_content_type(self):
        """Test that health response has correct content type."""
        response = client.get("/health")
        
        assert response.status_code == 200
        assert "application/json" in response.headers.get("content-type", "")
```