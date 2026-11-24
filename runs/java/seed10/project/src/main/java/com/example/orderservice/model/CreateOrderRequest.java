package com.example.orderservice.model;

import java.util.List;

public class CreateOrderRequest {

    private String customerId;
    private List<OrderItemRequest> items;

    public String getCustomerId() {
        return customerId;
    }

    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public List<OrderItemRequest> getItems() {
        return items;
    }

    public void setItems(List<OrderItemRequest> items) {
        this.items = items;
    }

    public static class OrderItemRequest {
        private String sku;
        private int quantity;
        private long unitPriceCents;

        public String getSku() {
            return sku;
        }

        public void setSku(String sku) {
            this.sku = sku;
        }

        public int getQuantity() {
            return quantity;
        }

        public void setQuantity(int quantity) {
            this.quantity = quantity;
        }

        public long getUnitPriceCents() {
            return unitPriceCents;
        }

        public void setUnitPriceCents(long unitPriceCents) {
            this.unitPriceCents = unitPriceCents;
        }
    }
}
