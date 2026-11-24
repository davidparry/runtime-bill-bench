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
