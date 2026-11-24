package com.example.orderservice.model;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

public class Order {

    private final String id;
    private final String customerId;
    private final List<OrderItem> items;
    private final long totalCents;
    private final Instant createdAt;

    public Order(String id, String customerId, List<OrderItem> items, long totalCents, Instant createdAt) {
        this.id = Objects.requireNonNull(id);
        this.customerId = Objects.requireNonNull(customerId);
        this.items = List.copyOf(Objects.requireNonNull(items));
        this.totalCents = totalCents;
        this.createdAt = Objects.requireNonNull(createdAt);
    }

    public String getId() {
        return id;
    }

    public String getCustomerId() {
        return customerId;
    }

    public List<OrderItem> getItems() {
        return items;
    }

    public long getTotalCents() {
        return totalCents;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public static class OrderItem {
        private final String sku;
        private final int quantity;
        private final long unitPriceCents;

        public OrderItem(String sku, int quantity, long unitPriceCents) {
            this.sku = Objects.requireNonNull(sku);
            this.quantity = quantity;
            this.unitPriceCents = unitPriceCents;
        }

        public String getSku() {
            return sku;
        }

        public int getQuantity() {
            return quantity;
        }

        public long getUnitPriceCents() {
            return unitPriceCents;
        }
    }
}
