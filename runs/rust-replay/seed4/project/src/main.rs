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
    #[serde(rename = "customerId")]
    pub customer_id: String,
    pub items: Vec<OrderItem>,
}

#[derive(Debug, Deserialize, Clone, Serialize)]
pub struct OrderItem {
    pub sku: String,
    pub quantity: i64,
    #[serde(rename = "unitPriceCents")]
    pub unit_price_cents: i64,
}

#[derive(Debug, Serialize, Clone)]
pub struct OrderResponse {
    pub id: String,
    #[serde(rename = "customerId")]
    pub customer_id: String,
    pub items: Vec<OrderItem>,
    #[serde(rename = "totalCents")]
    pub total_cents: i64,
    #[serde(rename = "createdAt")]
    pub created_at: DateTime<Utc>,
}

// --- State ---

#[derive(Clone)]
pub struct AppState {
    pub orders: Arc<RwLock<HashMap<String, OrderResponse>>>,
}

// --- Handlers ---

async fn health() -> impl IntoResponse {
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
        None => Err(AppError::NotFound(format!("Order with id {} not found", id))),
    }
}

// --- Validation & Error Handling ---

#[derive(Debug)]
pub struct AppError {
    pub status: StatusCode,
    pub message: String,
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
    request: axum::extract::Request,
    next: axum::middleware::Next,
) -> Response {
    let method = request.method().clone();
    let path = request.uri().path().to_string();
    let start = std::time::Instant::now();

    let response = next.run(request).await;
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
