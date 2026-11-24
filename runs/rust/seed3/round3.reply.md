FILE: src/main.rs
```rust
use axum::{
    extract::Path,
    http::{HeaderMap, HeaderValue, StatusCode},
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use chrono::Utc;
use serde::{Deserialize, Serialize};
use std::{
    net::SocketAddr,
    sync::Arc,
    time::{Duration, Instant},
};
use tokio::sync::RwLock;
use uuid::Uuid;

#[derive(Debug, Deserialize)]
struct CreateOrderRequest {
    customer_id: String,
    items: Vec<OrderItem>,
}

#[derive(Debug, Deserialize, Clone, Serialize)]
struct OrderItem {
    sku: String,
    quantity: u64,
    unit_price_cents: u64,
}

#[derive(Debug, Serialize)]
struct CreateOrderResponse {
    id: String,
    customer_id: String,
    items: Vec<OrderItem>,
    total_cents: u64,
    created_at: String,
}

#[derive(Debug, Serialize)]
struct ErrorResponse {
    error: String,
}

#[derive(Debug, Clone, Serialize)]
struct Order {
    id: String,
    customer_id: String,
    items: Vec<OrderItem>,
    total_cents: u64,
    created_at: String,
}

#[derive(Clone)]
struct AppState {
    orders: Arc<RwLock<Vec<Order>>>,
}

#[tokio::main]
async fn main() {
    let state = AppState {
        orders: Arc::new(RwLock::new(Vec::new())),
    };

    let app = Router::new()
        .route("/orders", post(create_order))
        .route("/orders/{id}", get(get_order))
        .route("/health", get(health_check))
        .with_state(state);

    let port = std::env::var("PORT").unwrap_or_else(|_| "8080".to_string());
    let addr = format!("0.0.0.0:{}", port);
    let listener = tokio::net::TcpListener::bind(&addr).await.unwrap();

    println!("Listening on {}", addr);

    // Graceful shutdown handling
    let shutdown_signal = async {
        let mut term = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
            .unwrap();
        term.recv().await;
        println!("Received SIGTERM, shutting down gracefully...");
    };

    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal)
        .await
        .unwrap();
}

async fn health_check() -> impl IntoResponse {
    let body = serde_json::json!({ "status": "ok" });
    (StatusCode::OK, Json(body)).into_response()
}

async fn create_order(
    state: axum::extract::State<AppState>,
    headers: HeaderMap,
    body: String,
) -> impl IntoResponse {
    let start = Instant::now();
    let method = "POST";
    let path = "/orders";

    // Parse JSON
    let req: CreateOrderRequest = match serde_json::from_str(&body) {
        Ok(r) => r,
        Err(e) => {
            let duration = start.elapsed().as_millis();
            log_request(method, path, 400, duration);
            let error_body = serde_json::json!({ "error": format!("Invalid JSON: {}", e) });
            return (StatusCode::BAD_REQUEST, Json(error_body)).into_response();
        }
    };

    // Validate
    if let Err(e) = validate_create_request(&req) {
        let duration = start.elapsed().as_millis();
        log_request(method, path, 400, duration);
        let error_body = serde_json::json!({ "error": e });
        return (StatusCode::BAD_REQUEST, Json(error_body)).into_response();
    }

    // Create order
    let order_id = Uuid::new_v4().to_string();
    let total_cents: u64 = req.items.iter().map(|i| i.quantity * i.unit_price_cents).sum();
    let created_at = Utc::now().to_rfc3339();

    let new_order = Order {
        id: order_id.clone(),
        customer_id: req.customer_id,
        items: req.items,
        total_cents,
        created_at: created_at.clone(),
    };

    {
        let mut orders = state.orders.write().await;
        orders.push(new_order);
    }

    let duration = start.elapsed().as_millis();
    log_request(method, path, 201, duration);

    let response_body = serde_json::json!({
        "id": order_id,
        "customerId": new_order.customer_id,
        "items": new_order.items,
        "totalCents": new_order.total_cents,
        "createdAt": new_order.created_at,
    });

    let mut response = Response::new(serde_json::to_string(&response_body).unwrap().into());
    response.headers_mut().insert(
        "Location",
        HeaderValue::from_str(&format!("/orders/{}", order_id)).unwrap(),
    );
    response.headers_mut().insert(
        "Content-Type",
        HeaderValue::from_static("application/json"),
    );
    response
}

async fn get_order(
    state: axum::extract::State<AppState>,
    Path(id): Path<String>,
) -> impl IntoResponse {
    let start = Instant::now();
    let method = "GET";
    let path = format!("/orders/{}", id);

    let orders = state.orders.read().await;
    let order = orders.iter().find(|o| o.id == id);

    let duration = start.elapsed().as_millis();

    match order {
        Some(o) => {
            log_request(method, &path, 200, duration);
            let response_body = serde_json::json!({
                "id": o.id,
                "customerId": o.customer_id,
                "items": o.items,
                "totalCents": o.total_cents,
                "createdAt": o.created_at,
            });
            (StatusCode::OK, Json(response_body)).into_response()
        }
        None => {
            log_request(method, &path, 404, duration);
            let error_body = serde_json::json!({ "error": "Order not found" });
            (StatusCode::NOT_FOUND, Json(error_body)).into_response()
        }
    }
}

fn validate_create_request(req: &CreateOrderRequest) -> Result<(), String> {
    if req.customer_id.len() < 1 || req.customer_id.len() > 64 {
        return Err("customerId must be between 1 and 64 characters".to_string());
    }

    if req.items.is_empty() || req.items.len() > 50 {
        return Err("items must contain between 1 and 50 entries".to_string());
    }

    for (i, item) in req.items.iter().enumerate() {
        if item.sku.len() < 1 || item.sku.len() > 32 {
            return Err(format!("items[{}].sku must be between 1 and 32 characters", i));
        }
        if item.quantity < 1 || item.quantity > 100 {
            return Err(format!("items[{}].quantity must be between 1 and 100", i));
        }
        if item.unit_price_cents < 1 || item.unit_price_cents > 1_000_000 {
            return Err(format!("items[{}].unitPriceCents must be between 1 and 1000000", i));
        }
    }

    Ok(())
}

fn log_request(method: &str, path: &str, status: u16, duration_ms: u128) {
    let log_entry = serde_json::json!({
        "method": method,
        "path": path,
        "status": status,
        "durationMs": duration_ms,
    });
    println!("{}", serde_json::to_string(&log_entry).unwrap());
}
```