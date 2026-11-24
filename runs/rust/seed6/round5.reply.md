FILE: src/main.rs
```rust
use axum::{
    extract::{Json, Path, State},
    http::{HeaderName, StatusCode},
    response::{IntoResponse, Response},
    routing::{get, post},
    Router,
};
use chrono::Utc;
use serde::{Deserialize, Serialize};
use std::{
    collections::HashMap,
    sync::{Arc, RwLock},
};
use tokio::signal;
use tower_http::trace::TraceLayer;
use tracing::{info, instrument, Level};

// Request structures
#[derive(Debug, Deserialize)]
struct CreateOrderRequest {
    customer_id: String,
    items: Vec<OrderItem>,
}

#[derive(Debug, Deserialize, Clone)]
struct OrderItem {
    sku: String,
    quantity: u64,
    unit_price_cents: u64,
}

// Response structures
#[derive(Debug, Serialize, Clone)]
struct OrderResponse {
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

// Application State
#[derive(Debug, Clone)]
struct AppState {
    orders: Arc<RwLock<HashMap<String, OrderResponse>>>,
}

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt()
        .json()
        .with_max_level(Level::INFO)
        .init();

    let state = AppState {
        orders: Arc::new(RwLock::new(HashMap::new())),
    };

    let app = Router::new()
        .route("/orders", post(create_order))
        .route("/orders/{id}", get(get_order))
        .route("/health", get(health_check))
        .with_state(state)
        .layer(TraceLayer::new_for_http());

    let port = std::env::var("PORT").unwrap_or_else(|_| "8080".to_string());
    let port: u16 = port.parse().unwrap_or(8080);
    let addr = format!("0.0.0.0:{}", port);

    let listener = tokio::net::TcpListener::bind(&addr).await.unwrap();
    info!("Listening on {}", addr);

    // Handle graceful shutdown
    let shutdown_signal = async {
        signal::ctrl_c().await.expect("failed to listen for ctrl+c");
        info!("Received SIGTERM (ctrl+c), shutting down gracefully...");
    };

    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal)
        .await
        .unwrap();
}

async fn health_check() -> impl IntoResponse {
    Json(serde_json::json!({"status": "ok"}))
}

#[instrument(name = "create_order", skip(state), fields(customer_id = %req.customer_id))]
async fn create_order(
    State(state): State<AppState>,
    Json(req): Json<CreateOrderRequest>,
) -> impl IntoResponse {
    // Validation: customerId
    if req.customer_id.len() < 1 || req.customer_id.len() > 64 {
        return (
            StatusCode::BAD_REQUEST,
            Json(ErrorResponse {
                error: "customerId must be between 1 and 64 characters".to_string(),
            }),
        )
        .into_response();
    }

    // Validation: items count
    if req.items.len() < 1 || req.items.len() > 50 {
        return (
            StatusCode::BAD_REQUEST,
            Json(ErrorResponse {
                error: "items must be between 1 and 50 entries".to_string(),
            }),
        )
        .into_response();
    }

    let mut total_cents: u64 = 0;
    for item in &req.items {
        // Validation: sku
        if item.sku.len() < 1 || item.sku.len() > 32 {
            return (
                StatusCode::BAD_REQUEST,
                Json(ErrorResponse {
                    error: "sku must be between 1 and 32 characters".to_string(),
                }),
            )
            .into_response();
        }
        // Validation: quantity
        if item.quantity < 1 || item.quantity > 100 {
            return (
                StatusCode::BAD_REQUEST,
                Json(ErrorResponse {
                    error: "quantity must be between 1 and 100".to_string(),
                }),
            )
            .into_response();
        }
        // Validation: unit_price_cents
        if item.unit_price_cents < 1 || item.unit_price_cents > 1_000_000 {
            return (
                StatusCode::BAD_REQUEST,
                Json(ErrorResponse {
                    error: "unitPriceCents must be between 1 and 1000000".to_string(),
                }),
            )
            .into_response();
        }
        
        // Calculate total
        match total_cents.checked_add(item.quantity * item.unit_price_cents) {
            Some(val) => total_cents = val,
            None => {
                return (
                    StatusCode::BAD_REQUEST,
                    Json(ErrorResponse {
                        error: "totalCents overflow".to_string(),
                    }),
                )
                .into_response();
            }
        }
    }

    let id = uuid::Uuid::new_v4().to_string();
    let created_at = Utc::now().to_rfc3339();

    let response = OrderResponse {
        id: id.clone(),
        customer_id: req.customer_id,
        items: req.items,
        total_cents,
        created_at,
    };

    {
        let mut orders = state.orders.write().unwrap();
        orders.insert(id.clone(), response.clone());
    }

    let mut res = (
        StatusCode::CREATED,
        Json(serde_json::to_value(&response).unwrap()),
    )
    .into_response();
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
    let orders = state.orders.read().unwrap();
    match orders.get(&id) {
        Some(order) => (StatusCode::OK, Json(serde_json::to_value(order).unwrap())).into_response(),
        None => (
            StatusCode::NOT_FOUND,
            Json(ErrorResponse {
                error: "Order not found".to_string(),
            }),
        )
        .into_response(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_validation_valid_order() {
        let req = CreateOrderRequest {
            customer_id: "c-1".to_string(),
            items: vec![OrderItem {
                sku: "A-1".to_string(),
                quantity: 2,
                unit_price_cents: 1250,
            }],
        };
        assert_eq!(validate_request(&req), Ok(()));
    }

    #[test]
    fn test_validation_empty_customer_id() {
        let req = CreateOrderRequest {
            customer_id: "".to_string(),
            items: vec![OrderItem {
                sku: "A-1".to_string(),
                quantity: 1,
                unit_price_cents: 100,
            }],
        };
        assert!(validate_request(&req).is_err());
    }

    #[test]
    fn test_validation_long_customer_id() {
        let req = CreateOrderRequest {
            customer_id: "a".repeat(65),
            items: vec![OrderItem {
                sku: "A-1".to_string(),
                quantity: 1,
                unit_price_cents: 100,
            }],
        };
        assert!(validate_request(&req).is_err());
    }

    #[test]
    fn test_validation_empty_items() {
        let req = CreateOrderRequest {
            customer_id: "c-1".to_string(),
            items: vec![],
        };
        assert!(validate_request(&req).is_err());
    }

    #[test]
    fn test_validation_too_many_items() {
        let items: Vec<OrderItem> = (0..51)
            .map(|i| OrderItem {
                sku: format!("SKU-{}", i),
                quantity: 1,
                unit_price_cents: 100,
            })
            .collect();
        let req = CreateOrderRequest {
            customer_id: "c-1".to_string(),
            items,
        };
        assert!(validate_request(&req).is_err());
    }

    #[test]
    fn test_validation_invalid_sku() {
        let req = CreateOrderRequest {
            customer_id: "c-1".to_string(),
            items: vec![OrderItem {
                sku: "a".repeat(33),
                quantity: 1,
                unit_price_cents: 100,
            }],
        };
        assert!(validate_request(&req).is_err());
    }

    #[test]
    fn test_validation_invalid_quantity() {
        let req = CreateOrderRequest {
            customer_id: "c-1".to_string(),
            items: vec![OrderItem {
                sku: "A-1".to_string(),
                quantity: 0,
                unit_price_cents: 100,
            }],
        };
        assert!(validate_request(&req).is_err());
    }

    #[test]
    fn test_validation_invalid_price() {
        let req = CreateOrderRequest {
            customer_id: "c-1".to_string(),
            items: vec![OrderItem {
                sku: "A-1".to_string(),
                quantity: 1,
                unit_price_cents: 0,
            }],
        };
        assert!(validate_request(&req).is_err());
    }

    fn validate_request(req: &CreateOrderRequest) -> Result<(), String> {
        if req.customer_id.len() < 1 || req.customer_id.len() > 64 {
            return Err("customerId must be between 1 and 64 characters".to_string());
        }
        if req.items.len() < 1 || req.items.len() > 50 {
            return Err("items must be between 1 and 50 entries".to_string());
        }
        for item in &req.items {
            if item.sku.len() < 1 || item.sku.len() > 32 {
                return Err("sku must be between 1 and 32 characters".to_string());
            }
            if item.quantity < 1 || item.quantity > 100 {
                return Err("quantity must be between 1 and 100".to_string());
            }
            if item.unit_price_cents < 1 || item.unit_price_cents > 1_000_000 {
                return Err("unitPriceCents must be between 1 and 1000000".to_string());
            }
        }
        Ok(())
    }
}
```