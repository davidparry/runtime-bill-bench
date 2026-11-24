FILE: main.py
```python
"""
Orders Service - FastAPI Application

This module defines the FastAPI application, including:
- In-memory order store with thread safety.
- Pydantic models for request validation and response serialization.
- Routes for creating and retrieving orders, plus a health check.
- Graceful shutdown handling.
- Structured JSON logging to stdout.
"""

import json
import logging
import os
import signal
import sys
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# --- Logging Configuration ---

# Create a logger specifically for the service
logger = logging.getLogger("orders_service")
logger.setLevel(logging.INFO)

# Custom handler to output structured JSON logs to stdout
class JsonLogHandler(logging.StreamHandler):
    def emit(self, record: logging.LogRecord) -> None:
        log_entry = {
            "method": getattr(record, "method", "N/A"),
            "path": getattr(record, "path", "N/A"),
            "status": getattr(record, "status", "N/A"),
            "durationMs": getattr(record, "durationMs", 0),
        }
        try:
            line = json.dumps(log_entry)
            self.stream.write(line + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)

# Setup handler
if not logger.handlers:
    handler = JsonLogHandler()
    logger.addHandler(handler)

# --- Models ---

class OrderItem(BaseModel):
    sku: str = Field(..., min_length=1, max_length=32)
    quantity: int = Field(..., ge=1, le=100)
    unitPriceCents: int = Field(..., ge=1, le=1000000)

    class Config:
        extra = "ignore" # Ignore unknown fields as per spec

class CreateOrderRequest(BaseModel):
    customerId: str = Field(..., min_length=1, max_length=64)
    items: List[OrderItem] = Field(..., min_length=1, max_length=50)

    class Config:
        extra = "ignore" # Ignore unknown fields

class OrderResponse(BaseModel):
    id: str
    customerId: str
    items: List[OrderItem]
    totalCents: int
    createdAt: str

# --- In-Memory Store ---

class OrderStore:
    def __init__(self):
        self._orders: Dict[str, OrderResponse] = {}
        self._lock = threading.Lock()

    def add_order(self, order: OrderResponse) -> None:
        with self._lock:
            self._orders[order.id] = order

    def get_order(self, order_id: str) -> Optional[OrderResponse]:
        with self._lock:
            return self._orders.get(order_id)

store = OrderStore()

# --- FastAPI App ---

app = FastAPI(title="Orders Service")

@app.middleware("http")
async def log_requests(request: Request, call_next):
    import time
    start_time = time.time()
    
    # Process request
    response = await call_next(request)
    
    end_time = time.time()
    duration_ms = int((end_time - start_time) * 1000)
    
    # Prepare log record
    record = logger.makeRecord(
        logger.name,
        logging.INFO,
        "(unknown)",
        0,
        "Request processed",
        (),
        None
    )
    record.method = request.method
    record.path = request.url.path
    record.status = response.status_code
    record.durationMs = duration_ms
    
    # Log the request
    logger.handle(record)
    
    return response

@app.post("/orders", status_code=201)
async def create_order(request: Request):
    """
    Creates a new order.
    """
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    try:
        validated_data = CreateOrderRequest.model_validate(body)
    except Exception as e:
        # Extract validation errors and format them into a single string message
        errors = e.errors()
        error_messages = []
        for err in errors:
            loc = " -> ".join(str(l) for l in err['loc'])
            msg = err['msg']
            error_messages.append(f"{loc}: {msg}")
        
        detail_msg = "; ".join(error_messages) if error_messages else str(e)
        raise HTTPException(status_code=400, detail=detail_msg)

    # Generate Order
    order_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    
    # Calculate total
    total_cents = 0
    for item in validated_data.items:
        total_cents += item.quantity * item.unitPriceCents
    
    # Construct response model
    order_response = OrderResponse(
        id=order_id,
        customerId=validated_data.customerId,
        items=validated_data.items,
        totalCents=total_cents,
        createdAt=now.strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    
    # Store order
    store.add_order(order_response)
    
    # Return response with Location header
    return JSONResponse(
        status_code=201,
        content=order_response.model_dump(),
        headers={"Location": f"/orders/{order_id}"}
    )

@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    """
    Retrieves an order by ID.
    """
    order = store.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"Order with id '{order_id}' not found")
    
    return order

@app.get("/health")
async def health_check():
    """
    Health check endpoint.
    """
    return {"status": "ok"}

# --- Graceful Shutdown ---

def shutdown_handler(signum, frame):
    """
    Handles SIGTERM for graceful shutdown.
    """
    # Log shutdown event
    record = logger.makeRecord(
        logger.name,
        logging.INFO,
        "(unknown)",
        0,
        "Received shutdown signal",
        (),
        None
    )
    record.method = "SIGTERM"
    record.path = "N/A"
    record.status = "SHUTDOWN"
    record.durationMs = 0
    logger.handle(record)
    
    # Exit gracefully
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGTERM, shutdown_handler)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port, log_level="warning")
```

FILE: tests/test_orders.py
```python
"""
Tests for the Orders Service.

Covers validation rules and 404 cases.
"""

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

class TestHealthEndpoint:
    def test_health_check(self):
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
        
        data = response.json()
        assert data["customerId"] == "c-1"
        assert len(data["items"]) == 1
        assert data["items"][0]["sku"] == "A-1"
        assert data["items"][0]["quantity"] == 2
        assert data["items"][0]["unitPriceCents"] == 1250
        assert data["totalCents"] == 2500
        assert "id" in data
        assert "createdAt" in data

    def test_create_order_invalid_json(self):
        response = client.post("/orders", content="not json", headers={"Content-Type": "application/json"})
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_missing_customer_id(self):
        payload = {
            "items": [
                {"sku": "A-1", "quantity": 1, "unitPriceCents": 100}
            ]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_customer_id_too_long(self):
        payload = {
            "customerId": "c" * 65,
            "items": [
                {"sku": "A-1", "quantity": 1, "unitPriceCents": 100}
            ]
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

    def test_create_order_invalid_quantity_zero(self):
        payload = {
            "customerId": "c-1",
            "items": [
                {"sku": "A-1", "quantity": 0, "unitPriceCents": 100}
            ]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_invalid_quantity_too_high(self):
        payload = {
            "customerId": "c-1",
            "items": [
                {"sku": "A-1", "quantity": 101, "unitPriceCents": 100}
            ]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_invalid_unit_price_zero(self):
        payload = {
            "customerId": "c-1",
            "items": [
                {"sku": "A-1", "quantity": 1, "unitPriceCents": 0}
            ]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_invalid_unit_price_too_high(self):
        payload = {
            "customerId": "c-1",
            "items": [
                {"sku": "A-1", "quantity": 1, "unitPriceCents": 1000001}
            ]
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_sku_too_long(self):
        payload = {
            "customerId": "c-1",
            "items": [
                {"sku": "s" * 33, "quantity": 1, "unitPriceCents": 100}
            ]
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

    def test_create_order_ignores_unknown_fields(self):
        payload = {
            "customerId": "c-1",
            "items": [
                {"sku": "A-1", "quantity": 1, "unitPriceCents": 100, "extraField": "ignored"}
            ],
            "unknownRootField": "ignored"
        }
        response = client.post("/orders", json=payload)
        assert response.status_code == 201

class TestGetOrder:
    def test_get_order_success(self):
        # Create an order first
        create_payload = {
            "customerId": "c-1",
            "items": [
                {"sku": "A-1", "quantity": 1, "unitPriceCents": 100}
            ]
        }
        create_response = client.post("/orders", json=create_payload)
        assert create_response.status_code == 201
        order_id = create_response.json()["id"]
        
        # Retrieve it
        response = client.get(f"/orders/{order_id}")
        assert response.status_code == 200
        assert response.json()["id"] == order_id

    def test_get_order_not_found(self):
        fake_id = "non-existent-id-12345"
        response = client.get(f"/orders/{fake_id}")
        assert response.status_code == 404
        assert "error" in response.json()
```