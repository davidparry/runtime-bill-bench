FILE: src/handlers.rs
```rust
use crate::state::{AppState, CreateOrderRequest, OrderResponse};
use axum::{
    extract::{Path, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use chrono::Utc;
use serde_json::json;
use uuid::Uuid;

#[derive(Debug)]
pub enum AppError {
    BadRequest(String),
    NotFound(String),
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        let (status, message) = match self {
            AppError::BadRequest(msg) => (StatusCode::BAD_REQUEST, msg),
            AppError::NotFound(msg) => (StatusCode::NOT_FOUND, msg),
        };

        let body = Json(json!({"error": message}));
        let mut res = body.into_response();
        res.headers_mut()
            .insert(
                axum::http::header::CONTENT_TYPE,
                axum::http::HeaderValue::from_static("application/json"),
            );
        res
    }
}

pub async fn create_order(
    State(state): State<AppState>,
    Json(payload): Json<CreateOrderRequest>,
) -> Result<Response, AppError> {
    if payload.customer_id.len() < 1 || payload.customer_id.len() > 64 {
        return Err(AppError::BadRequest(
            "customerId must be 1 to 64 characters".into(),
        ));
    }

    if payload.items.len() < 1 || payload.items.len() > 50 {
        return Err(AppError::BadRequest(
            "items must contain 1 to 50 entries".into(),
        ));
    }

    let mut total_cents: i64 = 0;
    let mut validated_items = Vec::with_capacity(payload.items.len());

    for item in &payload.items {
        if item.sku.len() < 1 || item.sku.len() > 32 {
            return Err(AppError::BadRequest(
                "sku must be 1 to 32 characters".into(),
            ));
        }
        if item.quantity < 1 || item.quantity > 100 {
            return Err(AppError::BadRequest(
                "quantity must be 1 to 100".into(),
            ));
        }
        if item.unit_price_cents < 1 || item.unit_price_cents > 1_000_000 {
            return Err(AppError::BadRequest(
                "unitPriceCents must be 1 to 1000000".into(),
            ));
        }

        let item_total = item.quantity * item.unit_price_cents;
        if item_total < 0 {
            return Err(AppError::BadRequest("item total overflow".into()));
        }

        total_cents = total_cents
            .checked_add(item_total)
            .ok_or_else(|| AppError::BadRequest("totalCents overflow".into()))?;
        
        validated_items.push(item.clone());
    }

    let order_id = Uuid::new_v4().to_string();
    let created_at = Utc::now().to_rfc3339();

    let response = OrderResponse {
        id: order_id.clone(),
        customer_id: payload.customer_id,
        items: validated_items,
        total_cents,
        created_at: created_at.clone(),
    };

    {
        let mut store = state.orders.lock().unwrap();
        store.insert(order_id.clone(), response.clone());
    }

    let mut res = (
        StatusCode::CREATED,
        [
            (
                axum::http::header::LOCATION,
                format!("/orders/{}", order_id),
            ),
        ],
        Json(response),
    )
    .into_response();

    res.headers_mut()
        .insert(
            axum::http::header::CONTENT_TYPE,
            axum::http::HeaderValue::from_static("application/json"),
        );

    Ok(res)
}

pub async fn get_order(
    State(state): State<AppState>,
    Path(order_id): Path<String>,
) -> Result<Json<OrderResponse>, AppError> {
    let store = state.orders.lock().unwrap();
    match store.get(&order_id) {
        Some(order) => Ok(Json(order.clone())),
        None => Err(AppError::NotFound(format!("Order {} not found", order_id))),
    }
}

pub async fn health_check() -> Json<serde_json::Value> {
    Json(json!({"status": "ok"}))
}
```

FILE: src/middleware.rs
```rust
use axum::http::Request;
use serde_json::json;
use std::time::Instant;
use tower::Layer;
use tower::Service;
use tower::ServiceExt;

#[derive(Clone)]
pub struct JsonLogger;

impl<S> Layer<S> for JsonLogger {
    type Service = JsonLoggerLayer<S>;

    fn layer(&self, service: S) -> Self::Service {
        JsonLoggerLayer { service }
    }
}

#[derive(Clone)]
pub struct JsonLoggerLayer<S> {
    service: S,
}

impl<S, B> Service<Request<B>> for JsonLoggerLayer<S>
where
    S: Service<Request<B>, Response = axum::http::Response<B>> + Clone + Send + 'static,
    S::Error: std::fmt::Display,
    S::Future: Send + 'static,
    B: Send + 'static,
{
    type Response = axum::http::Response<B>;
    type Error = S::Error;
    type Future =
        std::pin::Pin<Box<dyn std::future::Future<Output = Result<Self::Response, Self::Error>> + Send>>;

    fn poll_ready(
        &mut self,
        cx: &mut std::task::Context<'_>,
    ) -> std::task::Poll<Result<(), Self::Error>> {
        self.service.poll_ready(cx)
    }

    fn call(&mut self, mut req: Request<B>) -> Self::Future {
        let method = req.method().to_string();
        let path = req.uri().path().to_string();
        let start = Instant::now();

        let service = self.service.clone();
        Box::pin(async move {
            let res = service.oneshot(req).await?;
            let duration = start.elapsed();
            let status = res.status().as_u16();

            let log_entry = json!({
                "method": method,
                "path": path,
                "status": status,
                "durationMs": duration.as_millis()
            });

            println!("{}", serde_json::to_string(&log_entry).unwrap());

            Ok(res)
        })
    }
}
```