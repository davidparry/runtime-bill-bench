FILE: src/main.rs
```rust
use axum::extract::{Path, State};
use axum::http::{HeaderName, HeaderValue, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::Json;
use chrono::Utc;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::net::SocketAddr;
use std::sync::Arc;
use tokio::sync::RwLock;
use tracing::{info};
use uuid::Uuid;

/// The main application state, holding the in-memory order store.
#[derive(Clone)]
struct AppState {
    orders: Arc<RwLock<HashMap<String, Order>>>,
}

/// Represents a single order in the system.
#[derive(Clone, Debug, Deserialize, Serialize)]
struct Order {
    id: String,
    customer_id: String,
    items: Vec<OrderItem>,
    total_cents: i64,
    created_at: String,
}

/// Represents a single line item in an order.
#[derive(Clone, Debug, Deserialize, Serialize)]
struct OrderItem {
    sku: String,
    quantity: u32,
    unit_price_cents: u32,
}

/// Request payload for creating an order.
#[derive(Deserialize)]
struct CreateOrderRequest {
    customer_id: String,
    items: Vec<OrderItem>,
}

/// Error response body.
#[derive(Serialize)]
struct ErrorResponse {
    error: String,
}

fn error_response(status: StatusCode, message: &str) -> Response {
    let body = serde_json::to_string(&ErrorResponse {
        error: message.to_string(),
    }).unwrap();
    
    (status, [(HeaderName::from_static("content-type"), HeaderValue::from_static("application/json"))], body).into_response()
}

/// Validates the create order request.
fn validate_create_request(req: &CreateOrderRequest) -> Result<(), String> {
    // Validate customerId
    if req.customer_id.len() < 1 || req.customer_id.len() > 64 {
        return Err("customerId must be between 1 and 64 characters".to_string());
    }

    // Validate items array
    if req.items.len() < 1 || req.items.len() > 50 {
        return Err("items must contain between 1 and 50 entries".to_string());
    }

    for (i, item) in req.items.iter().enumerate() {
        // Validate sku
        if item.sku.len() < 1 || item.sku.len() > 32 {
            return Err(format!("items[{}].sku must be between 1 and 32 characters", i));
        }

        // Validate quantity
        if item.quantity < 1 || item.quantity > 100 {
            return Err(format!("items[{}].quantity must be between 1 and 100", i));
        }

        // Validate unitPriceCents
        if item.unit_price_cents < 1 || item.unit_price_cents > 1_000_000 {
            return Err(format!("items[{}].unitPriceCents must be between 1 and 1000000", i));
        }
    }

    Ok(())
}

/// Calculates the total cents for an order.
fn calculate_total(items: &[OrderItem]) -> i64 {
    items
        .iter()
        .map(|item| (item.quantity as i64) * (item.unit_price_cents as i64))
        .sum()
}

/// Handler for POST /orders
async fn create_order(
    State(state): State<AppState>,
    Json(req): Json<CreateOrderRequest>,
) -> impl IntoResponse {
    // Validate input
    if let Err(e) = validate_create_request(&req) {
        return error_response(StatusCode::BAD_REQUEST, &e);
    }

    let order_id = Uuid::new_v4().to_string();
    let total_cents = calculate_total(&req.items);
    let created_at = Utc::now().to_rfc3339();

    let new_order = Order {
        id: order_id.clone(),
        customer_id: req.customer_id,
        items: req.items,
        total_cents,
        created_at: created_at.clone(),
    };

    {
        let mut store = state.orders.write().await;
        store.insert(order_id.clone(), new_order);
    }

    let location = format!("/orders/{}", order_id);
    let body = serde_json::to_string(&Order {
        id: order_id,
        customer_id: new_order.customer_id,
        items: new_order.items,
        total_cents: new_order.total_cents,
        created_at,
    }).unwrap();

    (
        StatusCode::CREATED,
        [(HeaderName::from_static("location"), HeaderValue::from_str(&location).unwrap())],
        body
    ).into_response()
}

/// Handler for GET /orders/{id}
async fn get_order(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> impl IntoResponse {
    let store = state.orders.read().await;
    match store.get(&id) {
        Some(order) => {
            let body = serde_json::to_string(order).unwrap();
            (StatusCode::OK, [(HeaderName::from_static("content-type"), HeaderValue::from_static("application/json"))], body).into_response()
        },
        None => error_response(StatusCode::NOT_FOUND, &format!("Order with id '{}' not found", id)),
    }
}

/// Handler for GET /health
async fn health_check() -> impl IntoResponse {
    let body = serde_json::to_string(&serde_json::json!({ "status": "ok" })).unwrap();
    (StatusCode::OK, [(HeaderName::from_static("content-type"), HeaderValue::from_static("application/json"))], body).into_response()
}

#[tokio::main]
async fn main() {
    // Initialize tracing for structured logging
    tracing_subscriber::fmt()
        .json()
        .with_max_level(tracing::Level::INFO)
        .init();

    let orders = Arc::new(RwLock::new(HashMap::new()));
    let state = AppState { orders };

    let app = axum::Router::new()
        .route("/orders", post(create_order))
        .route("/orders/{id}", get(get_order))
        .route("/health", get(health_check))
        .with_state(state);

    let port = std::env::var("PORT").unwrap_or_else(|_| "8080".to_string());
    let addr: SocketAddr = format!("0.0.0.0:{}", port)
        .parse()
        .expect("Invalid PORT value");

    info!("Starting server on {}", addr);

    let listener = tokio::net::TcpListener::bind(&addr).await.unwrap();
    
    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal())
        .await
        .unwrap();
        
    info!("Server shut down gracefully.");
}

async fn shutdown_signal() {
    let ctrl_c = async {
        tokio::signal::ctrl_c().await.ok();
    };
    
    #[cfg(unix)]
    let terminate = async {
        tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
            .unwrap()
            .recv()
            .await;
    };

    #[cfg(not(unix))]
    let terminate = async {
        // Fallback for non-unix systems, typically just Ctrl+C
        ctrl_c.await;
    };

    tokio::select! {
        _ = ctrl_c => {},
        _ = terminate => {},
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::body::Body;
    use axum::http::Request;
    use axum::routing::Router;
    use axum::body::to_bytes;
    use serde_json::json;
    use std::collections::HashMap;
    use std::sync::Arc;
    use tokio::sync::RwLock;

    fn create_test_state() -> AppState {
        AppState {
            orders: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    fn create_test_app() -> Router<AppState> {
        let state = create_test_state();
        Router::new()
            .route("/orders", post(create_order))
            .route("/orders/{id}", get(get_order))
            .route("/health", get(health_check))
            .with_state(state)
    }

    #[tokio::test]
    async fn test_create_order_success() {
        let app = create_test_app();
        
        let body = json!({
            "customerId": "c-1",
            "items": [
                {
                    "sku": "A-1",
                    "quantity": 2,
                    "unitPriceCents": 1250
                }
            ]
        });

        let response = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/orders")
                    .header("content-type", "application/json")
                    .body(Body::from(serde_json::to_string(&body).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::CREATED);
        
        let body_bytes = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        let json: serde_json::Value = serde_json::from_slice(&body_bytes).unwrap();
        
        assert!(json.get("id").is_some());
        assert_eq!(json["customerId"], "c-1");
        assert_eq!(json["totalCents"], 2500);
        assert!(json.get("createdAt").is_some());
    }

    #[tokio::test]
    async fn test_create_order_missing_customer_id() {
        let app = create_test_app();
        
        let body = json!({
            "items": [
                {
                    "sku": "A-1",
                    "quantity": 1,
                    "unitPriceCents": 100
                }
            ]
        });

        let response = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/orders")
                    .header("content-type", "application/json")
                    .body(Body::from(serde_json::to_string(&body).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn test_create_order_invalid_quantity() {
        let app = create_test_app();
        
        let body = json!({
            "customerId": "c-1",
            "items": [
                {
                    "sku": "A-1",
                    "quantity": 0,
                    "unitPriceCents": 100
                }
            ]
        });

        let response = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/orders")
                    .header("content-type", "application/json")
                    .body(Body::from(serde_json::to_string(&body).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn test_create_order_invalid_unit_price() {
        let app = create_test_app();
        
        let body = json!({
            "customerId": "c-1",
            "items": [
                {
                    "sku": "A-1",
                    "quantity": 1,
                    "unitPriceCents": 0
                }
            ]
        });

        let response = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/orders")
                    .header("content-type", "application/json")
                    .body(Body::from(serde_json::to_string(&body).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn test_get_order_404() {
        let app = create_test_app();
        
        let response = app
            .oneshot(
                Request::builder()
                    .method("GET")
                    .uri("/orders/non-existent-id")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::NOT_FOUND);
        
        let body_bytes = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        let json: serde_json::Value = serde_json::from_slice(&body_bytes).unwrap();
        assert_eq!(json["error"], "Order with id 'non-existent-id' not found");
    }

    #[tokio::test]
    async fn test_health_check() {
        let app = create_test_app();
        
        let response = app
            .oneshot(
                Request::builder()
                    .method("GET")
                    .uri("/health")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        
        let body_bytes = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        let json: serde_json::Value = serde_json::from_slice(&body_bytes).unwrap();
        assert_eq!(json["status"], "ok");
    }
}
```