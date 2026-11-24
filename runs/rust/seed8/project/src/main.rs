use axum::{
    extract::{Path, State},
    http::{HeaderName, StatusCode},
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use chrono::Utc;
use serde::{Deserialize, Serialize};
use std::{
    collections::HashMap,
    sync::{Arc, Mutex},
};
use tokio::signal;
use tower_http::trace::TraceLayer;
use uuid::Uuid;

// --- Models ---

#[derive(Debug, Deserialize)]
struct CreateOrderRequest {
    customer_id: String,
    items: Vec<OrderItemRequest>,
}

#[derive(Debug, Deserialize)]
struct OrderItemRequest {
    sku: String,
    quantity: u32,
    unit_price_cents: u64,
}

#[derive(Debug, Serialize, Clone)]
struct OrderResponse {
    id: String,
    customer_id: String,
    items: Vec<OrderItemResponse>,
    total_cents: u64,
    created_at: String,
}

#[derive(Debug, Serialize, Clone)]
struct OrderItemResponse {
    sku: String,
    quantity: u32,
    unit_price_cents: u64,
}

#[derive(Debug, Serialize)]
struct ErrorResponse {
    error: String,
}

// --- State ---

#[derive(Clone)]
struct AppState {
    orders: Arc<Mutex<HashMap<String, OrderResponse>>>,
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

async fn create_order(
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
        store.insert(id.clone(), order);
    }

    let mut response = (
        StatusCode::CREATED,
        Json(OrderResponse {
            id: id.clone(),
            customer_id: order.customer_id,
            items: order.items,
            total_cents: order.total_cents,
            created_at: created_at,
        }),
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

async fn get_order(
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

async fn health() -> Json<serde_json::Value> {
    Json(serde_json::json!({ "status": "ok" }))
}

// --- Main ---

#[tokio::main]
async fn main() {
    let orders = Arc::new(Mutex::new(HashMap::new()));
    let state = AppState { orders };

    let app = Router::new()
        .route("/orders", post(create_order))
        .route("/orders/{id}", get(get_order))
        .route("/health", get(health))
        .with_state(state)
        .layer(TraceLayer::new_for_http());

    let listener = tokio::net::TcpListener::bind("0.0.0.0:8080")
        .await
        .expect("Failed to bind to port 8080");

    println!("Server listening on 0.0.0.0:8080");

    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal())
        .await
        .unwrap();
}

async fn shutdown_signal() {
    let ctrl_c = async {
        signal::ctrl_c()
            .await
            .expect("failed to install Ctrl+C handler");
    };

    #[cfg(unix)]
    let terminate = async {
        signal::unix::signal(signal::unix::SignalKind::terminate())
            .expect("failed to install signal handler")
            .recv()
            .await;
    };

    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();

    tokio::select! {
        _ = ctrl_c => {},
        _ = terminate => {},
    }
}
