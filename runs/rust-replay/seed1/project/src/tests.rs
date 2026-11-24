#[cfg(test)]
mod tests {
    use std::collections::HashMap;
    use std::sync::{Arc, Mutex};

    #[derive(Debug, Serialize)]
    struct OrderResponse {
        id: String,
        customer_id: String,
        items: Vec<OrderItem>,
        total_cents: u64,
        created_at: String,
    }

    #[derive(Debug, Deserialize, Serialize, Clone)]
    struct OrderItem {
        sku: String,
        quantity: u32,
        unit_price_cents: u32,
    }

    fn validate_create_request(customer_id: &str, items: &Vec<OrderItem>) -> Result<(), String> {
        if customer_id.len() < 1 || customer_id.len() > 64 {
            return Err("customer_id must be between 1 and 64 characters".to_string());
        }

        if items.is_empty() || items.len() > 50 {
            return Err("items must contain between 1 and 50 entries".to_string());
        }

        for (i, item) in items.iter().enumerate() {
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
        assert!(validate_create_request("", &items).is_err());
    }

    #[test]
    fn test_validate_customer_id_too_long() {
        let items = vec![OrderItem {
            sku: "A".to_string(),
            quantity: 1,
            unit_price_cents: 100,
        }];
        let long_id = "a".repeat(65);
        assert!(validate_create_request(&long_id, &items).is_err());
    }

    #[test]
    fn test_validate_items_empty() {
        let items: Vec<OrderItem> = vec![];
        assert!(validate_create_request("c-1", &items).is_err());
    }

    #[test]
    fn test_validate_items_too_many() {
        let items: Vec<OrderItem> = (0..51).map(|i| OrderItem {
            sku: format!("S{}", i),
            quantity: 1,
            unit_price_cents: 100,
        }).collect();
        assert!(validate_create_request("c-1", &items).is_err());
    }

    #[test]
    fn test_validate_sku_too_short() {
        let items = vec![OrderItem {
            sku: "".to_string(),
            quantity: 1,
            unit_price_cents: 100,
        }];
        assert!(validate_create_request("c-1", &items).is_err());
    }

    #[test]
    fn test_validate_quantity_zero() {
        let items = vec![OrderItem {
            sku: "A".to_string(),
            quantity: 0,
            unit_price_cents: 100,
        }];
        assert!(validate_create_request("c-1", &items).is_err());
    }

    #[test]
    fn test_validate_price_zero() {
        let items = vec![OrderItem {
            sku: "A".to_string(),
            quantity: 1,
            unit_price_cents: 0,
        }];
        assert!(validate_create_request("c-1", &items).is_err());
    }

    #[test]
    fn test_validate_success() {
        let items = vec![OrderItem {
            sku: "A-1".to_string(),
            quantity: 2,
            unit_price_cents: 1250,
        }];
        assert!(validate_create_request("c-1", &items).is_ok());
    }
}
