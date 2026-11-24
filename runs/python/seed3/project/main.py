import os
import sys
import json
import uuid
import time
import signal
import logging
import threading
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ConfigDict

# Configure logging for structured output
logger = logging.getLogger("orders_service")
logger.setLevel(logging.INFO)

# In-memory store protected by a lock for thread safety
order_store: dict[str, dict[str, Any]] = {}
store_lock = threading.Lock()

# Setup logging handler to write JSON lines to stdout
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_record = {
            "method": getattr(record, "method", None),
            "path": getattr(record, "path", None),
            "status": getattr(record, "status_code", None),
            "durationMs": getattr(record, "duration_ms", None),
            "message": record.getMessage(),
        }
        # Ensure all required keys are present
        for key in ["method", "path", "status", "durationMs"]:
            if key not in log_record or log_record[key] is None:
                log_record[key] = None
        
        return json.dumps(log_record)

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
# Avoid duplicate logs if logger is configured elsewhere
if not logger.handlers:
    logger.addHandler(handler)


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
    model_config = ConfigDict(extra="ignore")
    
    id: str
    customerId: str
    items: list[Item]
    totalCents: int
    createdAt: str


# --- Application Logic ---

def create_order(req: OrderCreateRequest) -> OrderResponse:
    order_id = uuid.uuid4().hex
    total_cents = sum(item.quantity * item.unitPriceCents for item in req.items)
    created_at = datetime.now(timezone.utc).isoformat()
    
    order_data = {
        "id": order_id,
        "customerId": req.customerId,
        "items": req.items,
        "totalCents": total_cents,
        "createdAt": created_at
    }
    
    with store_lock:
        order_store[order_id] = order_data
        
    return OrderResponse(
        id=order_id,
        customerId=req.customerId,
        items=req.items,
        totalCents=total_cents,
        createdAt=created_at
    )

def get_order(order_id: str) -> OrderResponse | None:
    with store_lock:
        order_data = order_store.get(order_id)
    
    if order_data is None:
        return None
        
    return OrderResponse(
        id=order_data["id"],
        customerId=order_data["customerId"],
        items=order_data["items"],
        totalCents=order_data["totalCents"],
        createdAt=order_data["createdAt"]
    )

# --- FastAPI App ---

app = FastAPI(title="Orders Service")

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    
    response = await call_next(request)
    
    duration_ms = (time.time() - start_time) * 1000
    
    # Log the request
    log_record = {
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "durationMs": round(duration_ms, 2),
        "message": f"{request.method} {request.url.path} {response.status_code}"
    }
    
    # Use the logger we set up
    # We need to create a LogRecord manually to inject our fields
    record = logger.makeRecord(
        logger.name, 
        logging.INFO, 
        "", 
        0, 
        log_record["message"], 
        (), 
        None
    )
    # Manually set attributes expected by our custom formatter
    record.method = log_record["method"]
    record.path = log_record["path"]
    record.status_code = log_record["status"]
    record.duration_ms = log_record["durationMs"]
    
    logger.handle(record)
    
    return response

@app.post("/orders")
async def create_order_raw(request: Request):
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid JSON"},
            headers={"Content-Type": "application/json"}
        )
    
    try:
        req = OrderCreateRequest(**body)
    except Exception as e:
        # Pydantic raises ValidationError
        return JSONResponse(
            status_code=400,
            content={"error": str(e)},
            headers={"Content-Type": "application/json"}
        )
    
    result = create_order(req)
    
    return JSONResponse(
        status_code=201,
        content=result.model_dump(),
        headers={"Content-Type": "application/json", "Location": f"/orders/{result.id}"}
    )

@app.get("/orders/{order_id}")
async def get_order_endpoint(order_id: str):
    result = get_order(order_id)
    if result is None:
        return JSONResponse(
            status_code=404,
            content={"error": "Order not found"},
            headers={"Content-Type": "application/json"}
        )
    
    return JSONResponse(
        status_code=200,
        content=result.model_dump(),
        headers={"Content-Type": "application/json"}
    )

@app.get("/health")
async def health_check():
    return JSONResponse(
        status_code=200,
        content={"status": "ok"},
        headers={"Content-Type": "application/json"}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), log_level="info")
