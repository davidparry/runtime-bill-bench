package com.example.orders.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.annotation.JsonSerialize;
import com.fasterxml.jackson.databind.ser.std.NumberSerializer;

import java.util.List;
import java.math.BigDecimal;
import java.util.UUID;

public class OrderResponse {

    private String id;
    private String customerId;
    private List<OrderItem> items;
    
    @JsonSerialize(using = NumberSerializer.class)
    private long totalCents;
    
    private String createdAt;

    public OrderResponse(String id, String customerId, List<OrderItem> items, long totalCents, String createdAt) {
        this.id = id;
        this.customerId = customerId;
        this.items = items;
        this.totalCents = totalCents;
        this.createdAt = createdAt;
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

    public String getCreatedAt() {
        return createdAt;
    }
}
