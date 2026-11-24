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

    public Order(String customerId, List<OrderItem> items) {
        this.id = UUID.randomUUID().toString();
        this.customerId = customerId;
        this.items = List.copyOf(items); // Immutable copy
        this.totalCents = calculateTotalCents(items);
        this.createdAt = Instant.now();
    }

    private long calculateTotalCents(List<OrderItem> items) {
        long total = 0;
        for (OrderItem item : items) {
            total += item.getQuantity() * item.getUnitPriceCents();
        }
        return total;
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

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (o == null || getClass() != o.getClass()) return false;
        Order order = (Order) o;
        return Objects.equals(id, order.id);
    }

    @Override
    public int hashCode() {
        return Objects.hash(id);
    }

    public static class OrderItem {
        private final String sku;
        private final int quantity;
        private final int unitPriceCents;

        public OrderItem(String sku, int quantity, int unitPriceCents) {
            this.sku = sku;
            this.quantity = quantity;
            this.unitPriceCents = unitPriceCents;
        }

        public String getSku() {
            return sku;
        }

        public int getQuantity() {
            return quantity;
        }

        public int getUnitPriceCents() {
            return unitPriceCents;
        }

        @Override
        public boolean equals(Object o) {
            if (this == o) return true;
            if (o == null || getClass() != o.getClass()) return false;
            OrderItem that = (OrderItem) o;
            return quantity == that.quantity
                    && unitPriceCents == that.unitPriceCents
                    && Objects.equals(sku, that.sku);
        }

        @Override
        public int hashCode() {
            return Objects.hash(sku, quantity, unitPriceCents);
        }
    }
}
