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
from pydantic import BaseModel, Field, ConfigDict

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
    model_config = ConfigDict(extra="ignore")
    
    sku: str = Field(..., min_length=1, max_length=32)
    quantity: int = Field(..., ge=1, le=100)
    unitPriceCents: int = Field(..., ge=1, le=1000000)

class CreateOrderRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    customerId: str = Field(..., min_length=1, max_length=64)
    items: List[OrderItem] = Field(..., min_length=1, max_length=50)

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

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """
    Custom exception handler to return 'error' key instead of 'detail'.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail}
    )

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
