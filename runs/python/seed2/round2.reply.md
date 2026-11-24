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
from pydantic import BaseModel, Field, field_validator, ConfigDict

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

def format_order_response(order_id: str, request: CreateOrderRequest) -> OrderResponse:
    total = calculate_total(request.items)
    now = datetime.now(timezone.utc)
    return OrderResponse(
        id=order_id,
        customerId=request.customerId,
        items=request.items,
        totalCents=total,
        createdAt=now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    )

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
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    
    try:
        order_data = CreateOrderRequest(**body)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Validation error")

    order_id = str(uuid.uuid4())
    
    async with orders_lock:
        orders_store[order_id] = {
            "id": order_id,
            "customerId": order_data.customerId,
            "items": order_data.items,
            "totalCents": calculate_total(order_data.items),
            "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        }
        
    response = JSONResponse(
        content=format_order_response(order_id, order_data).model_dump(),
        status_code=201
    )
    response.headers["Location"] = f"/orders/{order_id}"
    return response

@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    async with orders_lock:
        order = orders_store.get(order_id)
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Return in the format specified: id, customerId, items, totalCents, createdAt
    # Ensure items are serialized correctly by using model_dump on the stored items if they are Pydantic models
    # But since we stored the Pydantic objects directly in the dict, we need to serialize them.
    # We can reconstruct the response object or manually serialize.
    # Using model_dump is safer to ensure correct JSON types.
    
    # Reconstruct a temporary response object to get the correct serialization
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