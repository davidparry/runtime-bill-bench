FILE: main.py
```python
import os
import sys
import uuid
import time
import json
import signal
import asyncio
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ConfigDict

# --- Models ---

class OrderItem(BaseModel):
    sku: str = Field(..., min_length=1, max_length=32)
    quantity: int = Field(..., ge=1, le=100)
    unitPriceCents: int = Field(..., ge=1, le=1000000)

class CreateOrderRequest(BaseModel):
    customerId: str = Field(..., min_length=1, max_length=64)
    items: List[OrderItem] = Field(..., min_length=1, max_length=50)

    model_config = ConfigDict(extra="ignore")

class OrderResponse(BaseModel):
    id: str
    customerId: str
    items: List[OrderItem]
    totalCents: int
    createdAt: str

# --- In-Memory Store ---

orders_store: dict[str, Dict[str, Any]] = {}
orders_lock = asyncio.Lock()

# --- Helper Functions ---

def calculate_total(items: List[OrderItem]) -> int:
    total = 0
    for item in items:
        total += item.quantity * item.unitPriceCents
    return total

def format_order_response(order_id: str, request: CreateOrderRequest, timestamp: str) -> OrderResponse:
    total = calculate_total(request.items)
    return OrderResponse(
        id=order_id,
        customerId=request.customerId,
        items=request.items,
        totalCents=total,
        createdAt=timestamp
    )

def create_error_response(message: str) -> JSONResponse:
    return JSONResponse(status_code=400, content={"error": message})

# --- Application Setup ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(lifespan=lifespan)

# --- Middleware for Logging ---

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start_time) * 1000
    
    log_entry = {
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "durationMs": round(duration_ms, 2)
    }
    
    print(json.dumps(log_entry), flush=True)
    
    return response

# --- Routes ---

@app.post(
    "/orders",
    status_code=201,
    responses={
        201: {"model": OrderResponse, "description": "Order created successfully"},
        400: {"description": "Invalid input"},
    }
)
async def create_order(request: Request):
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return create_error_response("Invalid JSON body")
    
    try:
        order_data = CreateOrderRequest(**body)
    except Exception as e:
        # Extract a meaningful error message from Pydantic validation error
        error_msg = "Validation error"
        if hasattr(e, 'errors'):
            # Pydantic V2
            first_error = e.errors()[0]
            error_msg = f"{first_error['loc'][-1]}: {first_error['msg']}"
        elif hasattr(e, 'message'):
            # Pydantic V1 fallback or other exceptions
            error_msg = e.message
        return create_error_response(error_msg)

    order_id = str(uuid.uuid4())
    
    # Capture timestamp once to ensure consistency between create and get
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    
    async with orders_lock:
        orders_store[order_id] = {
            "id": order_id,
            "customerId": order_data.customerId,
            "items": order_data.items,
            "totalCents": calculate_total(order_data.items),
            "createdAt": timestamp
        }
        
    response = JSONResponse(
        content=format_order_response(order_id, order_data, timestamp).model_dump(),
        status_code=201
    )
    response.headers["Location"] = f"/orders/{order_id}"
    return response

@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    async with orders_lock:
        order = orders_store.get(order_id)
    
    if not order:
        return JSONResponse(status_code=404, content={"error": "Order not found"})
    
    # Return in the format specified: id, customerId, items, totalCents, createdAt
    # Ensure items are serialized correctly.
    resp_data = {
        "id": order["id"],
        "customerId": order["customerId"],
        "items": [item.model_dump() if hasattr(item, 'model_dump') else item for item in order["items"]],
        "totalCents": order["totalCents"],
        "createdAt": order["createdAt"]
    }
    
    return JSONResponse(content=resp_data)

@app.get("/health")
async def health_check():
    return {"status": "ok"}

# --- Entry Point ---

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
```