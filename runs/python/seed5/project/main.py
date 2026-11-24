"""
Orders Service - FastAPI Application

Production-ready HTTP service for managing orders.
"""

import asyncio
import json
import logging
import os
import signal
import sys
import time
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
        logger.info(json.dumps(log_entry))
