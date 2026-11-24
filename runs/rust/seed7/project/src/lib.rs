use axum::extract::State;
use axum::routing::{get, post};
use axum::Json;
use axum::response::{IntoResponse, Response};
use axum::http::StatusCode;
use std::collections::HashMap;
use std::sync::Arc;
use uuid::Uuid;
use serde::{Deserialize, Serialize};
use chrono::Utc;
use tower::ServiceBuilder;
use tower_http::trace::TraceLayer;
use tokio::sync::RwLock;

#[derive(Debug, Deserialize)]
pub struct CreateOrderRequest {
    customer_id: String,
    items: Vec<OrderItem>,
}

#[derive(Debug, Deserialize, Clone, Serialize)]
pub struct OrderItem {
    pub sku: String,
    pub quantity: u64,
    pub unit_price_cents: u64,
}

#[derive(Debug, Serialize, Clone)]
pub struct OrderResponse {
    pub id: String,
    pub customer_id: String,
    pub items: Vec<OrderItem>,
    pub total_cents: u64,
    pub created_at: String,
}

#[derive(Debug, Deserialize)]
pub struct ErrorResponse {
    pub error: String,
}

#[derive(Debug, Clone)]
pub struct AppState {
    pub orders: Arc<RwLock<HashMap<String, OrderResponse>>>,
}

impl IntoResponse for ErrorResponse {
    fn into_response(self) -> Response {
        (StatusCode::BAD_REQUEST, Json(self)).into_response()
    }
}

impl IntoResponse for (StatusCode, ErrorResponse) {
    fn into_response(self) -> Response {
        (self.0, Json(self.1)).into_response()
    }
}

pub fn validate_create_request(req: CreateOrderRequest) -> Result<(), ErrorResponse> {
    if req.customer_id.len() < 1 || req.customer_id.len() > 64 {
        return Err(ErrorResponse {
            error: "customer_id must be between 1 and 64 characters".to_string(),
        });
    }

    if req.items.is_empty() || req.items.len() > 50 {
        return Err(ErrorResponse {
            error: "items must contain between 1 and 50 entries".to_string(),
        });
    }

    for (i, item) in req.items.iter().enumerate() {
        if item.sku.len() < 1 || item.sku.len() > 32 {
            return Err(ErrorResponse {
                error: format!("item[{}].sku must be between 1 and 32 characters", i),
            });
        }
        if item.quantity < 1 || item.quantity > 100 {
            return Err(ErrorResponse {
                error: format!("item[{}].quantity must be between 1 and 100", i),
            });
        }
        if item.unit_price_cents < 1 || item.unit_price_cents > 1_000_000 {
            return Err(ErrorResponse {
                error: format!("item[{}].unit_price_cents must be between 1 and 1000000", i),
            });
        }
    }

    Ok(())
}

pub async fn create_order(
    State(state): State<AppState>,
    Json(req): Json<CreateOrderRequest>,
) -> Result<impl IntoResponse, (StatusCode, ErrorResponse)> {
    if let Err(err) = validate_create_request(req) {
        return Err((StatusCode::BAD_REQUEST, err));
    }

    let id = Uuid::new_v4().to_string();
    let customer_id = req.customer_id.clone();
    let items = req.items.clone();
    
    let total_cents: u64 = items.iter().map(|i| i.quantity * i.unit_price_cents).sum();
    let created_at = Utc::now().to_rfc3339();

    let order = OrderResponse {
        id: id.clone(),
        customer_id,
        items,
        total_cents,
        created_at,
    };

    let mut orders = state.orders.write().await;
    orders.insert(id.clone(), order);

    let response = Response::builder()
        .status(StatusCode::CREATED)
        .header(axum::http::header::LOCATION, format!("/orders/{}", id))
        .body(axum::body::Body::from(serde_json::to_string(&OrderResponse {
            id: id.clone(),
            customer_id: req.customer_id.clone(),
            items: req.items.clone(),
            total_cents: total_cents,
            created_at: created_at,
        }).unwrap()))
        .unwrap();

    Ok(response)
}

pub async fn get_order(
    State(state): State<AppState>,
    axum::extract::Path(id): axum::extract::Path<String>,
) -> Result<impl IntoResponse, (StatusCode, ErrorResponse)> {
    let orders = state.orders.read().await;
    match orders.get(&id) {
        Some(order) => Ok(Json(order.clone())),
        None => Err((StatusCode::NOT_FOUND, ErrorResponse {
            error: format!("Order with id {} not found", id),
        })),
    }
}

pub async fn health() -> Json<&'static str> {
    Json("ok")
}

pub fn create_app() -> axum::Router<AppState> {
    let orders: Arc<RwLock<HashMap<String, OrderResponse>>> = Arc::new(RwLock::new(HashMap::new()));
    let state = AppState { orders };

    axum::Router::new()
        .route("/orders", post(create_order))
        .route("/orders/{id}", get(get_order))
        .route("/health", get(health))
        .with_state(state)
        .layer(TraceLayer::new_for_http())
}
