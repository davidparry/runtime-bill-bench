FILE: src/lib.rs
```rust
use axum::{
    extract::{Path, State},
    http::{HeaderName, StatusCode},
    response::{IntoResponse, Response},
    routing::{get, post},
    Json,
};
use chrono::Utc;
use serde::{Deserialize, Serialize};
use std::{
    collections::HashMap,
    sync::{Arc, Mutex},
};
use uuid::Uuid;

// --- Models ---

#[derive(Debug, Deserialize)]
pub struct CreateOrderRequest {
    customer_id: String,
    items: Vec<OrderItemRequest>,
}

#[derive(Debug, Deserialize)]
pub struct OrderItemRequest {
    sku: String,
    quantity: u32,
    unit_price_cents: u64,
}

#[derive(Debug, Serialize, Clone)]
pub struct OrderResponse {
    pub id: String,
    pub customer_id: String,
    pub items: Vec<OrderItemResponse>,
    pub total_cents: u64,
    pub created_at: String,
}

#[derive(Debug, Serialize, Clone)]
pub struct OrderItemResponse {
    pub sku: String,
    pub quantity: u32,
    pub unit_price_cents: u64,
}

#[derive(Debug, Serialize)]
pub struct ErrorResponse {
    pub error: String,
}

// --- State ---

#[derive(Clone)]
pub struct AppState {
    pub orders: Arc<Mutex<HashMap<String, OrderResponse>>>,
}

// --- Validation Helpers ---

fn validate_customer_id(id: &str) -> Result<(), String> {
    let len = id.len();
    if len < 1 || len > 64 {
        return Err("customerId must be between 1 and 64 characters".to_string());
    }
    Ok(())
}

fn validate_items(items: &[OrderItemRequest]) -> Result<(), String> {
    let len = items.len();
    if len < 1 || len > 50 {
        return Err("items must contain between 1 and 50 entries".to_string());
    }

    for (i, item) in items.iter().enumerate() {
        let sku_len = item.sku.len();
        if sku_len < 1 || sku_len > 32 {
            return Err(format!("item[{}].sku must be between 1 and 32 characters", i));
        }
        if item.quantity < 1 || item.quantity > 100 {
            return Err(format!("item[{}].quantity must be between 1 and 100", i));
        }
        if item.unit_price_cents < 1 || item.unit_price_cents > 1_000_000 {
            return Err(format!("item[{}].unitPriceCents must be between 1 and 1000000", i));
        }
    }
    Ok(())
}

// --- Handlers ---

pub async fn create_order(
    State(state): State<AppState>,
    Json(payload): Json<CreateOrderRequest>,
) -> Result<Response, (StatusCode, Json<ErrorResponse>)> {
    // Validation
    if let Err(e) = validate_customer_id(&payload.customer_id) {
        return Err((
            StatusCode::BAD_REQUEST,
            Json(ErrorResponse { error: e }),
        ));
    }

    if let Err(e) = validate_items(&payload.items) {
        return Err((
            StatusCode::BAD_REQUEST,
            Json(ErrorResponse { error: e }),
        ));
    }

    let id = Uuid::new_v4().to_string();
    let now = Utc::now();
    let created_at = now.to_rfc3339();

    let items_resp: Vec<OrderItemResponse> = payload
        .items
        .iter()
        .map(|i| OrderItemResponse {
            sku: i.sku.clone(),
            quantity: i.quantity,
            unit_price_cents: i.unit_price_cents,
        })
        .collect();

    let total_cents: u64 = items_resp
        .iter()
        .map(|i| i.quantity as u64 * i.unit_price_cents)
        .sum();

    let order = OrderResponse {
        id: id.clone(),
        customer_id: payload.customer_id,
        items: items_resp,
        total_cents,
        created_at: created_at.clone(),
    };

    // Store
    {
        let mut store = state.orders.lock().unwrap();
        store.insert(id.clone(), order.clone());
    }

    let mut response = (
        StatusCode::CREATED,
        Json(order),
    )
    .into_response();
    response.headers_mut().insert(
        HeaderName::from_static("location"),
        format!("/orders/{}", id)
            .parse()
            .unwrap(),
    );

    Ok(response)
}

pub async fn get_order(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<OrderResponse>, (StatusCode, Json<ErrorResponse>)> {
    let store = state.orders.lock().unwrap();
    match store.get(&id) {
        Some(order) => Ok(Json(order.clone())),
        None => Err((
            StatusCode::NOT_FOUND,
            Json(ErrorResponse {
                error: format!("Order not found: {}", id),
            }),
        )),
    }
}

pub async fn health() -> Json<serde_json::Value> {
    Json(serde_json::json!({ "status": "ok" }))
}
```