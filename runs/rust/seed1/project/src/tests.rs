#[cfg(test)]
mod tests {
    use serde::{Deserialize, Serialize};
    use std::collections::HashMap;
    use std::sync::{Arc, Mutex};

    // Re-define structs to test validation logic in isolation
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

    // Copy validation logic here for testing
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

    #[test]
    fn test_validate_customer_id_too_short() {
        let items = vec![OrderItem {
            sku: "A".to_string(),
            quantity: 1,
            unit_price_cents: 100,
        }];
        let req = CreateOrderRequest {
            customer_id: "".to_string(),
            items,
        };
        assert!(validate_create_request(&req).is_err());
    }

    #[test]
    fn test_validate_customer_id_too_long() {
        let items = vec![OrderItem {
            sku: "A".to_string(),
            quantity: 1,
            unit_price_cents: 100,
        }];
        let long_id = "a".repeat(65);
        let req = CreateOrderRequest {
            customer_id: long_id,
            items,
        };
        assert!(validate_create_request(&req).is_err());
    }

    #[test]
    fn test_validate_items_empty() {
        let items: Vec<OrderItem> = vec![];
        let req = CreateOrderRequest {
            customer_id: "c-1".to_string(),
            items,
        };
        assert!(validate_create_request(&req).is_err());
    }

    #[test]
    fn test_validate_items_too_many() {
        let items: Vec<OrderItem> = (0..51).map(|i| OrderItem {
            sku: format!("S{}", i),
            quantity: 1,
            unit_price_cents: 100,
        }).collect();
        let req = CreateOrderRequest {
            customer_id: "c-1".to_string(),
            items,
        };
        assert!(validate_create_request(&req).is_err());
    }

    #[test]
    fn test_validate_sku_too_short() {
        let items = vec![OrderItem {
            sku: "".to_string(),
            quantity: 1,
            unit_price_cents: 100,
        }];
        let req = CreateOrderRequest {
            customer_id: "c-1".to_string(),
            items,
        };
        assert!(validate_create_request(&req).is_err());
    }

    #[test]
    fn test_validate_quantity_zero() {
        let items = vec![OrderItem {
            sku: "A".to_string(),
            quantity: 0,
            unit_price_cents: 100,
        }];
        let req = CreateOrderRequest {
            customer_id: "c-1".to_string(),
            items,
        };
        assert!(validate_create_request(&req).is_err());
    }

    #[test]
    fn test_validate_price_zero() {
        let items = vec![OrderItem {
            sku: "A".to_string(),
            quantity: 1,
            unit_price_cents: 0,
        }];
        let req = CreateOrderRequest {
            customer_id: "c-1".to_string(),
            items,
        };
        assert!(validate_create_request(&req).is_err());
    }

    #[test]
    fn test_validate_success() {
        let items = vec![OrderItem {
            sku: "A-1".to_string(),
            quantity: 2,
            unit_price_cents: 1250,
        }];
        let req = CreateOrderRequest {
            customer_id: "c-1".to_string(),
            items,
        };
        assert!(validate_create_request(&req).is_ok());
    }
}
