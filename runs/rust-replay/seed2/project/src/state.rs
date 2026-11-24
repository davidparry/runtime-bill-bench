use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::{Arc, Mutex};

#[derive(Debug, Deserialize)]
pub struct CreateOrderRequest {
    pub customer_id: String,
    pub items: Vec<OrderItem>,
}

#[derive(Debug, Deserialize, Clone, Serialize)]
pub struct OrderItem {
    pub sku: String,
    pub quantity: i64,
    pub unit_price_cents: i64,
}

#[derive(Debug, Clone, Serialize)]
pub struct OrderResponse {
    pub id: String,
    pub customer_id: String,
    pub items: Vec<OrderItem>,
    pub total_cents: i64,
    pub created_at: String,
}

#[derive(Clone)]
pub struct AppState {
    pub orders: Arc<Mutex<HashMap<String, OrderResponse>>>,
}

impl AppState {
    pub fn new() -> Self {
        AppState {
            orders: Arc::new(Mutex::new(HashMap::new())),
        }
    }
}
