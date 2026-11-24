FILE: src/main.rs
```rust
use axum::{
    extract::{Path, State},
    http::{HeaderName, StatusCode},
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use axum::extract::rejection::JsonRejection;
use chrono::Utc;
use serde::{Deserialize, Serialize};
use std::{
    collections::HashMap,
    env,
    sync::{Arc, Mutex},
    time::Instant,
};
use tokio::signal;
use uuid::Uuid;

// --- Domain Models ---

#[derive(Debug, Deserialize)]
struct CreateOrderRequest {
    customer_id: String,
    items: Vec<OrderItem>,
}

#[derive(Debug, Deserialize, Serialize, Clone)]
struct OrderItem {
    sku: String,
    quantity: u32,
    unit_price_cents: u32,
}

#[derive(Debug, Serialize, Clone)]
struct OrderResponse {
    id: String,
    customer_id: String,
    items: Vec<OrderItem>,
    total_cents: u64,
    created_at: String,
}

// --- State Management ---

#[derive(Clone, Debug)]
struct AppState {
    orders: Arc<Mutex<HashMap<String, OrderResponse>>>,
}

// --- Validation Helpers ---

fn validate_create_request(req: &CreateOrderRequest) -> Result<(), String> {
    if req.customer_id.len() < 1 || req.customer_id.len() > 64 {
        return Err("customer_id must be between 1 and 64 characters".to_string());
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
            return Err(format!("items[{}].unit_price_cents must be between 1 and 1000000", i));
        }
    }

    Ok(())
}

// --- Handlers ---

async fn health_handler() -> impl IntoResponse {
    Json(serde_json::json!({ "status": "ok" }))
}

async fn create_order_handler(
    State(state): State<AppState>,
    Json(req): Json<CreateOrderRequest>,
) -> impl IntoResponse {
    // Validate
    if let Err(e) = validate_create_request(&req) {
        return (
            StatusCode::BAD_REQUEST,
            Json(serde_json::json!({ "error": e })),
        )
            .into_response();
    }

    let id = Uuid::new_v4().to_string();
    let now = Utc::now().to_rfc3339();

    // Calculate total
    let total_cents: u64 = req
        .items
        .iter()
        .map(|item| {
            // Use u64 to prevent overflow during multiplication
            item.quantity as u64 * item.unit_price_cents as u64
        })
        .sum();

    let order = OrderResponse {
        id: id.clone(),
        customer_id: req.customer_id,
        items: req.items,
        total_cents,
        created_at: now,
    };

    {
        let mut orders = state.orders.lock().unwrap();
        orders.insert(id.clone(), order.clone());
    }

    let mut response = (
        StatusCode::CREATED,
        Json(serde_json::json!({
            "id": order.id,
            "customerId": order.customer_id,
            "items": order.items,
            "totalCents": order.total_cents,
            "createdAt": order.created_at
        })),
    )
    .into_response();

    response
        .headers_mut()
        .insert(
            HeaderName::from_static("location"),
            format!("/orders/{}", id).parse().unwrap(),
        );

    response
}

async fn get_order_handler(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> impl IntoResponse {
    let orders = state.orders.lock().unwrap();

    match orders.get(&id) {
        Some(order) => {
            let resp = serde_json::json!({
                "id": order.id,
                "customerId": order.customer_id,
                "items": order.items,
                "totalCents": order.total_cents,
                "createdAt": order.created_at
            });
            (StatusCode::OK, Json(resp)).into_response()
        }
        None => (
            StatusCode::NOT_FOUND,
            Json(serde_json::json!({ "error": "Order not found" })),
        )
            .into_response(),
    }
}

// --- Custom Error Handler for Validation ---

async fn handle_json_rejection(rejection: JsonRejection) -> impl IntoResponse {
    let status = rejection.status();
    let error = rejection.into_body().to_string();
    (status, Json(serde_json::json!({ "error": error })))
}

// --- Logging Middleware ---

async fn log_middleware(
    req: axum::extract::Request,
    next: axum::middleware::Next,
) -> impl IntoResponse {
    let method = req.method().clone();
    let path = req.uri().path().to_string();
    let start = Instant::now();

    let response = next.run(req).await;

    let duration = start.elapsed();
    let status = response.status().as_u16();

    println!(
        "{{\"method\": \"{}\", \"path\": \"{}\", \"status\": {}, \"durationMs\": {}}}",
        method,
        path,
        status,
        duration.as_millis()
    );

    response
}

#[tokio::main]
async fn main() {
    let orders: HashMap<String, OrderResponse> = HashMap::new();
    let state = AppState {
        orders: Arc::new(Mutex::new(orders)),
    };

    let app = Router::new()
        .route("/health", get(health_handler))
        .route("/orders", post(create_order_handler).on_error(handle_json_rejection))
        .route("/orders/{id}", get(get_order_handler))
        .layer(axum::middleware::from_fn(log_middleware))
        .with_state(state);

    let port = env::var("PORT")
        .ok()
        .and_then(|p| p.parse().ok())
        .unwrap_or(8080);

    let listener = tokio::net::TcpListener::bind(format!("0.0.0.0:{}", port))
        .await
        .expect("Failed to bind to port");

    eprintln!("Listening on http://0.0.0.0:{}", port);

    let (tx, rx) = tokio::sync::broadcast::channel(1);

    let server = axum::serve(listener, app)
        .with_graceful_shutdown(async move {
            // Wait for shutdown signal
            signal::unix::signal(signal::unix::SignalKind::terminate())
                .expect("failed to install signal handler")
                .recv()
                .await;
            let _ = tx.send(());
        });

    tokio::spawn(async move {
        if let Err(e) = server.await {
            eprintln!("Server error: {}", e);
        }
    });

    // Wait for shutdown signal in main task to keep process alive
    signal::unix::signal(signal::unix::SignalKind::terminate())
        .expect("failed to install signal handler")
        .recv()
        .await;

    eprintln!("Shutting down gracefully...");
}
```