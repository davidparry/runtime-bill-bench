package com.example.orderservice.model;

import java.math.BigDecimal;
import java.util.Objects;
import java.util.UUID;
import java.time.Instant;

public class Order {

    private final String id;
    private final String customerId;
    private final java.util.List<OrderItem> items;
    private final long totalCents;
    private final Instant createdAt;

    public Order(String customerId, java.util.List<OrderItem> items) {
        this.id = UUID.randomUUID().toString();
        this.customerId = customerId;
        this.items = java.util.Collections.unmodifiableList(new java.util.ArrayList<>(items));
        this.totalCents = calculateTotalCents(items);
        this.createdAt = Instant.now();
    }

    private long calculateTotalCents(java.util.List<OrderItem> items) {
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

    public java.util.List<OrderItem> getItems() {
        return items;
    }

    public long getTotalCents() {
        return totalCents;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public String getCreatedAtIso() {
        return java.time.format.DateTimeFormatter.ISO_INSTANT.format(createdAt);
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
}
