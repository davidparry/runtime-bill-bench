FILE: src/main.rs
```rust
use axum::{
    extract::{Path, State},
    http::{HeaderName, StatusCode},
    response::IntoResponse,
    routing::{get, post},
    Json, Router,
};
use chrono::Utc;
use serde::{Deserialize, Serialize};
use std::{
    collections::HashMap,
    sync::{Arc, Mutex},
    time::Instant,
};
use tokio::signal;
use tower_http::trace::TraceLayer;
use uuid::Uuid;

// --- Domain Models ---

#[derive(Debug, Deserialize)]
struct CreateOrderRequest {
    #[serde(rename = "customerId")]
    customer_id: String,
    items: Vec<OrderItem>,
}

#[derive(Debug, Deserialize, Serialize, Clone)]
struct OrderItem {
    sku: String,
    quantity: u32,
    #[serde(rename = "unitPriceCents")]
    unit_price_cents: u32,
}

#[derive(Debug, Serialize, Clone)]
struct OrderResponse {
    id: String,
    #[serde(rename = "customerId")]
    customer_id: String,
    items: Vec<OrderItem>,
    #[serde(rename = "totalCents")]
    total_cents: u64,
    #[serde(rename = "createdAt")]
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
        return (StatusCode::BAD_REQUEST, Json(serde_json::json!({ "error": e }))).into_response();
    }

    let id = Uuid::new_v4().to_string();
    let now = Utc::now().to_rfc3339();

    // Calculate total
    let total_cents: u64 = req
        .items
        .iter()
        .map(|item| {
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
            "id": id,
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
        .route("/orders", post(create_order_handler))
        .route("/orders/{id}", get(get_order_handler))
        .layer(axum::middleware::from_fn(log_middleware))
        .layer(TraceLayer::new_for_http())
        .with_state(state);

    let listener = tokio::net::TcpListener::bind("0.0.0.0:8080")
        .await
        .expect("Failed to bind to port 8080");
    let port = listener.local_addr().unwrap().port();
    eprintln!("Listening on http://0.0.0.0:{}", port);

    let (tx, rx) = tokio::sync::broadcast::channel(1);
    
    let server = axum::serve(listener, app.with_state(state.clone()))
        .with_graceful_shutdown(async move {
            rx.recv().await.ok();
        });

    // Listen for SIGTERM
    tokio::spawn(async move {
        signal::unix::signal(signal::unix::SignalKind::terminate())
            .expect("failed to install signal handler")
            .recv()
            .await;
        let _ = tx.send(());
    });
    
    // Listen for SIGINT
    tokio::spawn(async move {
        signal::unix::signal(signal::unix::SignalKind::interrupt())
            .expect("failed to install signal handler")
            .recv()
            .await;
        let _ = tx.send(());
    });

    server.await.unwrap();
}
```