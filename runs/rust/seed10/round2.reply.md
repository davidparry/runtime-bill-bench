FILE: Cargo.toml
```toml
[package]
name = "orders"
version = "0.1.0"
edition = "2021"

[dependencies]
axum = { version = "0.7", features = ["json"] }
tokio = { version = "1", features = ["full"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
uuid = { version = "1", features = ["v4", "serde"] }
chrono = { version = "0.4", features = ["serde"] }

[dev-dependencies]
reqwest = { version = "0.11", features = ["json"] }
tokio = { version = "1", features = ["full"] }
```

FILE: src/main.rs
```rust
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
    sync::{Arc, RwLock},
    time::Instant,
};
use uuid::Uuid;

#[derive(Deserialize, Debug, PartialEq)]
struct CreateOrderRequest {
    customer_id: String,
    items: Vec<OrderItem>,
}

#[derive(Deserialize, Debug, PartialEq, Clone, Serialize)]
struct OrderItem {
    sku: String,
    quantity: u32,
    unit_price_cents: u64,
}

#[derive(Serialize, Debug, PartialEq, Clone)]
struct OrderResponse {
    id: String,
    customer_id: String,
    items: Vec<OrderItem>,
    total_cents: u64,
    created_at: String,
}

#[derive(Serialize, Debug)]
struct ErrorResponse {
    error: String,
}

#[derive(Clone)]
struct AppState {
    orders: Arc<RwLock<HashMap<String, OrderResponse>>>,
}

#[tokio::main]
async fn main() {
    let orders = Arc::new(RwLock::new(HashMap::new()));
    let state = AppState { orders };

    let app = Router::new()
        .route("/orders", post(create_order))
        .route("/orders/{id}", get(get_order))
        .route("/health", get(health))
        .with_state(state);

    let port: u16 = std::env::var("PORT")
        .ok()
        .and_then(|p| p.parse().ok())
        .unwrap_or(8080);

    let listener = tokio::net::TcpListener::bind(format!("0.0.0.0:{}", port))
        .await
        .unwrap();

    println!("Listening on 0.0.0.0:{}", port);

    let shutdown_signal = async {
        let mut sigterm = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
            .expect("Failed to set up SIGTERM handler");
        
        let mut sigint = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::interrupt())
            .expect("Failed to set up SIGINT handler");

        tokio::select! {
            _ = sigterm.recv() => {
                println!("Received SIGTERM");
            }
            _ = sigint.recv() => {
                println!("Received SIGINT");
            }
        }
    };

    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal)
        .await
        .unwrap();
}

async fn health() -> impl IntoResponse {
    let body = serde_json::json!({ "status": "ok" });
    (StatusCode::OK, Json(body)).into_response()
}

async fn create_order(
    State(state): State<AppState>,
    Json(payload): Json<CreateOrderRequest>,
) -> impl IntoResponse {
    let start = Instant::now();
    
    // Validation
    let validation_result = validate_create_order(&payload);
    if let Err(e) = validation_result {
        let duration = start.elapsed().as_millis();
        log_request("POST", "/orders", 400, duration);
        return (StatusCode::BAD_REQUEST, Json(ErrorResponse { error: e })).into_response();
    }

    let id = Uuid::new_v4().to_string();
    let total_cents: u64 = payload
        .items
        .iter()
        .map(|item| item.quantity as u64 * item.unit_price_cents)
        .sum();

    let created_at = Utc::now().to_rfc3339();

    let response = OrderResponse {
        id: id.clone(),
        customer_id: payload.customer_id,
        items: payload.items,
        total_cents,
        created_at,
    };

    // Store in memory
    let mut orders = state.orders.write().unwrap();
    orders.insert(id.clone(), response.clone());

    let duration = start.elapsed().as_millis();
    log_request("POST", "/orders", 201, duration);

    let mut res = (StatusCode::CREATED, Json(response)).into_response();
    res.headers_mut()
        .insert(
            HeaderName::from_static("location"),
            format!("/orders/{}", id).parse().unwrap(),
        );
    res
}

async fn get_order(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> impl IntoResponse {
    let start = Instant::now();

    let orders = state.orders.read().unwrap();
    
    if let Some(order) = orders.get(&id) {
        let duration = start.elapsed().as_millis();
        log_request("GET", &format!("/orders/{}", id), 200, duration);
        return (StatusCode::OK, Json(order)).into_response();
    }

    let duration = start.elapsed().as_millis();
    log_request("GET", &format!("/orders/{}", id), 404, duration);
    (StatusCode::NOT_FOUND, Json(ErrorResponse { error: "Order not found".to_string() })).into_response()
}

fn validate_create_order(payload: &CreateOrderRequest) -> Result<(), String> {
    // Validate customerId
    if payload.customer_id.is_empty() || payload.customer_id.len() > 64 {
        return Err("customerId must be between 1 and 64 characters".to_string());
    }

    // Validate items
    if payload.items.is_empty() || payload.items.len() > 50 {
        return Err("items must be an array with 1 to 50 entries".to_string());
    }

    for (i, item) in payload.items.iter().enumerate() {
        if item.sku.is_empty() || item.sku.len() > 32 {
            return Err(format!("items[{}].sku must be between 1 and 32 characters", i));
        }
        if item.quantity < 1 || item.quantity > 100 {
            return Err(format!("items[{}].quantity must be between 1 and 100", i));
        }
        if item.unit_price_cents < 1 || item.unit_price_cents > 1000000 {
            return Err(format!("items[{}].unitPriceCents must be between 1 and 1000000", i));
        }
    }

    Ok(())
}

fn log_request(method: &str, path: &str, status: u16, duration_ms: u128) {
    let log_line = serde_json::json!({
        "method": method,
        "path": path,
        "status": status,
        "durationMs": duration_ms
    });
    println!("{}", log_line);
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_request(customer_id: &str, items: Vec<OrderItem>) -> CreateOrderRequest {
        CreateOrderRequest {
            customer_id: customer_id.to_string(),
            items,
        }
    }

    #[test]
    fn test_validate_valid_order() {
        let items = vec![OrderItem {
            sku: "A-1".to_string(),
            quantity: 2,
            unit_price_cents: 1250,
        }];
        let req = make_request("c-1", items);
        assert!(validate_create_order(&req).is_ok());
    }

    #[test]
    fn test_validate_customer_id_too_long() {
        let items = vec![OrderItem {
            sku: "A-1".to_string(),
            quantity: 1,
            unit_price_cents: 100,
        }];
        let req = make_request(&"a".repeat(65), items);
        let err = validate_create_order(&req).unwrap_err();
        assert!(err.contains("customerId"));
    }

    #[test]
    fn test_validate_customer_id_empty() {
        let items = vec![OrderItem {
            sku: "A-1".to_string(),
            quantity: 1,
            unit_price_cents: 100,
        }];
        let req = make_request("", items);
        let err = validate_create_order(&req).unwrap_err();
        assert!(err.contains("customerId"));
    }

    #[test]
    fn test_validate_items_empty() {
        let req = make_request("c-1", vec![]);
        let err = validate_create_order(&req).unwrap_err();
        assert!(err.contains("items"));
    }

    #[test]
    fn test_validate_items_too_many() {
        let items: Vec<OrderItem> = (0..51).map(|i| OrderItem {
            sku: format!("S-{}", i),
            quantity: 1,
            unit_price_cents: 100,
        }).collect();
        let req = make_request("c-1", items);
        let err = validate_create_order(&req).unwrap_err();
        assert!(err.contains("items"));
    }

    #[test]
    fn test_validate_sku_empty() {
        let items = vec![OrderItem {
            sku: "".to_string(),
            quantity: 1,
            unit_price_cents: 100,
        }];
        let req = make_request("c-1", items);
        let err = validate_create_order(&req).unwrap_err();
        assert!(err.contains("sku"));
    }

    #[test]
    fn test_validate_quantity_zero() {
        let items = vec![OrderItem {
            sku: "A-1".to_string(),
            quantity: 0,
            unit_price_cents: 100,
        }];
        let req = make_request("c-1", items);
        let err = validate_create_order(&req).unwrap_err();
        assert!(err.contains("quantity"));
    }

    #[test]
    fn test_validate_price_zero() {
        let items = vec![OrderItem {
            sku: "A-1".to_string(),
            quantity: 1,
            unit_price_cents: 0,
        }];
        let req = make_request("c-1", items);
        let err = validate_create_order(&req).unwrap_err();
        assert!(err.contains("unitPriceCents"));
    }
}
```