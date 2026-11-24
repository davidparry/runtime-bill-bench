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
tower = "0.5"
tower-http = { version = "0.5", features = ["trace"] }
futures-util = "0.3"

[dev-dependencies]
reqwest = { version = "0.11", features = ["json"] }
tokio = { version = "1", features = ["full", "test-util"] }
```

FILE: src/main.rs
```rust
use axum::extract::{Path, State};
use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::Json;
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;
use uuid::Uuid;

// --- Models ---

#[derive(Debug, Deserialize, Clone)]
pub struct CreateOrderRequest {
    customer_id: String,
    items: Vec<OrderItem>,
}

#[derive(Debug, Deserialize, Clone, Serialize)]
pub struct OrderItem {
    sku: String,
    quantity: i64,
    unit_price_cents: i64,
}

#[derive(Debug, Serialize, Clone)]
pub struct OrderResponse {
    id: String,
    customer_id: String,
    items: Vec<OrderItem>,
    total_cents: i64,
    created_at: DateTime<Utc>,
}

// --- State ---

#[derive(Clone)]
pub struct AppState {
    pub orders: Arc<RwLock<HashMap<String, OrderResponse>>>,
}

// --- Handlers ---

pub async fn health() -> impl IntoResponse {
    Json(serde_json::json!({ "status": "ok" }))
}

pub async fn create_order(
    State(state): State<AppState>,
    Json(req): Json<CreateOrderRequest>,
) -> Result<impl IntoResponse, AppError> {
    // Validation
    validate_create_order_request(&req)?;

    let id = Uuid::new_v4().to_string();
    let customer_id = req.customer_id;
    let items = req.items;
    
    let total_cents: i64 = items
        .iter()
        .map(|item| item.quantity * item.unit_price_cents)
        .sum();

    let created_at = Utc::now();

    let response = OrderResponse {
        id: id.clone(),
        customer_id: customer_id.clone(),
        items: items.clone(),
        total_cents,
        created_at,
    };

    {
        let mut store = state.orders.write().await;
        store.insert(id.clone(), response.clone());
    }

    let mut res = Json(response).into_response();
    res.headers_mut()
        .insert("Location", format!("/orders/{}", id).parse().unwrap());
    Ok(res)
}

pub async fn get_order(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<impl IntoResponse, AppError> {
    let store = state.orders.read().await;
    
    match store.get(&id) {
        Some(order) => Ok(Json(order.clone()).into_response()),
        None => Err(AppError::not_found(format!("Order with id {} not found", id))),
    }
}

// --- Validation & Error Handling ---

#[derive(Debug)]
pub struct AppError {
    status: StatusCode,
    message: String,
}

impl AppError {
    pub fn bad_request(msg: impl Into<String>) -> Self {
        AppError {
            status: StatusCode::BAD_REQUEST,
            message: msg.into(),
        }
    }

    pub fn not_found(msg: impl Into<String>) -> Self {
        AppError {
            status: StatusCode::NOT_FOUND,
            message: msg.into(),
        }
    }
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        (self.status, Json(serde_json::json!({ "error": self.message }))).into_response()
    }
}

pub fn validate_create_order_request(req: &CreateOrderRequest) -> Result<(), AppError> {
    // Customer ID rules
    if req.customer_id.is_empty() || req.customer_id.len() > 64 {
        return Err(AppError::bad_request("customerId must be between 1 and 64 characters"));
    }

    // Items rules
    if req.items.is_empty() || req.items.len() > 50 {
        return Err(AppError::bad_request("items must contain between 1 and 50 entries"));
    }

    for (i, item) in req.items.iter().enumerate() {
        // SKU rules
        if item.sku.is_empty() || item.sku.len() > 32 {
            return Err(AppError::bad_request(format!("items[{}].sku must be between 1 and 32 characters", i)));
        }

        // Quantity rules
        if item.quantity < 1 || item.quantity > 100 {
            return Err(AppError::bad_request(format!("items[{}].quantity must be between 1 and 100", i)));
        }

        // Unit Price rules
        if item.unit_price_cents < 1 || item.unit_price_cents > 1_000_000 {
            return Err(AppError::bad_request(format!("items[{}].unitPriceCents must be between 1 and 1000000", i)));
        }
    }

    Ok(())
}

// --- Middleware for Logging ---

async fn log_request(
    req: axum::extract::Request,
    next: axum::next::Next<axum::extract::Request>,
) -> Response {
    let method = req.method().clone();
    let path = req.uri().path().to_string();
    let start = std::time::Instant::now();

    let response = next.run(req).await;
    let duration = start.elapsed();
    let status = response.status().as_u16();

    let log_entry = serde_json::json!({
        "method": method.to_string(),
        "path": path,
        "status": status,
        "durationMs": duration.as_millis()
    });

    println!("{}", serde_json::to_string(&log_entry).unwrap());

    response
}

// --- Main ---

#[tokio::main]
async fn main() {
    let orders = Arc::new(RwLock::new(HashMap::new()));
    let state = AppState { orders };

    let app = axum::Router::new()
        .route("/health", get(health))
        .route("/orders", post(create_order))
        .route("/orders/{id}", get(get_order))
        .layer(axum::middleware::from_fn(log_request))
        .with_state(state);

    let listener = tokio::net::TcpListener::bind("0.0.0.0:8080")
        .await
        .expect("Failed to bind to port 8080");

    println!("Listening on 0.0.0.0:8080");

    // Graceful shutdown
    let shutdown_handle = async {
        tokio::signal::ctrl_c().await.ok();
        println!("Received shutdown signal");
    };

    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_handle)
        .await
        .expect("Server error");
        
    println!("Server shut down gracefully.");
}
```

FILE: src/tests.rs
```rust
#[cfg(test)]
mod validation_tests {
    use crate::create_order::CreateOrderRequest;
    use crate::validate_create_order_request;
    use crate::OrderItem;

    #[test]
    fn test_validate_customer_id_empty() {
        let req = CreateOrderRequest {
            customer_id: "".to_string(),
            items: vec![OrderItem {
                sku: "A".to_string(),
                quantity: 1,
                unit_price_cents: 10,
            }],
        };
        let res = validate_create_order_request(&req);
        assert!(res.is_err());
    }

    #[test]
    fn test_validate_customer_id_too_long() {
        let req = CreateOrderRequest {
            customer_id: "a".repeat(65),
            items: vec![OrderItem {
                sku: "A".to_string(),
                quantity: 1,
                unit_price_cents: 10,
            }],
        };
        let res = validate_create_order_request(&req);
        assert!(res.is_err());
    }

    #[test]
    fn test_validate_items_empty() {
        let req = CreateOrderRequest {
            customer_id: "c-1".to_string(),
            items: vec![],
        };
        let res = validate_create_order_request(&req);
        assert!(res.is_err());
    }

    #[test]
    fn test_validate_items_too_many() {
        let items: Vec<OrderItem> = (0..51).map(|i| OrderItem {
            sku: format!("A-{}", i),
            quantity: 1,
            unit_price_cents: 10,
        }).collect();
        
        let req = CreateOrderRequest {
            customer_id: "c-1".to_string(),
            items: items,
        };
        let res = validate_create_order_request(&req);
        assert!(res.is_err());
    }

    #[test]
    fn test_validate_item_sku_empty() {
        let req = CreateOrderRequest {
            customer_id: "c-1".to_string(),
            items: vec![OrderItem {
                sku: "".to_string(),
                quantity: 1,
                unit_price_cents: 10,
            }],
        };
        let res = validate_create_order_request(&req);
        assert!(res.is_err());
    }

    #[test]
    fn test_validate_item_quantity_zero() {
        let req = CreateOrderRequest {
            customer_id: "c-1".to_string(),
            items: vec![OrderItem {
                sku: "A".to_string(),
                quantity: 0,
                unit_price_cents: 10,
            }],
        };
        let res = validate_create_order_request(&req);
        assert!(res.is_err());
    }

    #[test]
    fn test_validate_item_quantity_too_high() {
        let req = CreateOrderRequest {
            customer_id: "c-1".to_string(),
            items: vec![OrderItem {
                sku: "A".to_string(),
                quantity: 101,
                unit_price_cents: 10,
            }],
        };
        let res = validate_create_order_request(&req);
        assert!(res.is_err());
    }

    #[test]
    fn test_validate_item_price_zero() {
        let req = CreateOrderRequest {
            customer_id: "c-1".to_string(),
            items: vec![OrderItem {
                sku: "A".to_string(),
                quantity: 1,
                unit_price_cents: 0,
            }],
        };
        let res = validate_create_order_request(&req);
        assert!(res.is_err());
    }

    #[test]
    fn test_validate_item_price_too_high() {
        let req = CreateOrderRequest {
            customer_id: "c-1".to_string(),
            items: vec![OrderItem {
                sku: "A".to_string(),
                quantity: 1,
                unit_price_cents: 1_000_001,
            }],
        };
        let res = validate_create_order_request(&req);
        assert!(res.is_err());
    }

    #[test]
    fn test_validate_success() {
        let req = CreateOrderRequest {
            customer_id: "c-1".to_string(),
            items: vec![OrderItem {
                sku: "A-1".to_string(),
                quantity: 2,
                unit_price_cents: 1250,
            }],
        };
        let res = validate_create_order_request(&req);
        assert!(res.is_ok());
    }
}
```

FILE: tests/integration.rs
```rust
use axum::routing::get;
use axum::Router;
use serde::Deserialize;
use serde_json::json;
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;

// Re-export necessary types for testing
use orders::AppState;
use orders::create_order;
use orders::get_order;

#[derive(Deserialize)]
struct ErrorResponse {
    error: String,
}

#[derive(Deserialize)]
struct OrderResponse {
    id: String,
    customer_id: String,
    items: Vec<orders::OrderItem>,
    total_cents: i64,
    created_at: String,
}

#[tokio::test]
async fn test_get_order_not_found() {
    let orders = Arc::new(RwLock::new(HashMap::new()));
    let state = AppState { orders };

    let app = Router::new()
        .route("/orders/{id}", get(get_order))
        .with_state(state);

    let client = reqwest::Client::new();
    
    let res = client
        .get("http://localhost:8080/orders/non-existent-id")
        .send()
        .await
        .unwrap();

    assert_eq!(res.status(), reqwest::StatusCode::NOT_FOUND);
    
    let json: serde_json::Value = res.json().await.unwrap();
    assert!(json.get("error").is_some());
}

#[tokio::test]
async fn test_create_and_get_order() {
    let orders = Arc::new(RwLock::new(HashMap::new()));
    let state = AppState { orders };

    let app = Router::new()
        .route("/orders", axum::routing::post(create_order))
        .route("/orders/{id}", get(get_order))
        .with_state(state);

    let client = reqwest::Client::new();
    let body = json!({
        "customerId": "c-1",
        "items": [
            { "sku": "A-1", "quantity": 2, "unitPriceCents": 1250 }
        ]
    });

    let res = client
        .post("http://localhost:8080/orders")
        .json(&body)
        .send()
        .await
        .unwrap();

    assert_eq!(res.status(), reqwest::StatusCode::CREATED);
    
    let location = res.headers().get("Location").unwrap().to_str().unwrap();
    let order_id = location.trim_start_matches("/orders/");

    // Get the order
    let get_res = client
        .get(format!("http://localhost:8080/orders/{}", order_id))
        .send()
        .await
        .unwrap();

    assert_eq!(get_res.status(), reqwest::StatusCode::OK);
    
    let json: serde_json::Value = get_res.json().await.unwrap();
    assert_eq!(json["id"], order_id);
    assert_eq!(json["customerId"], "c-1");
    assert_eq!(json["totalCents"], 2500);
}
```