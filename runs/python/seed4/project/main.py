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
