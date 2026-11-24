#[cfg(test)]
mod tests {
    use super::super::*;
    use axum::body::Body;
    use axum::http::{Request, StatusCode};
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
        let client = reqwest::Client::new();
        
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
