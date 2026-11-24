package com.example.orderservice.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import java.util.List;

@JsonInclude(JsonInclude.Include.NON_NULL)
public class OrderResponse {

    private String id;
    private String customerId;
    private List<CreateOrderRequest.OrderItem> items;
    private Long totalCents;
    private String createdAt;

    public OrderResponse() {
    }

    public OrderResponse(String id, String customerId, List<CreateOrderRequest.OrderItem> items, Long totalCents, String createdAt) {
        this.id = id;
        this.customerId = customerId;
        this.items = items;
        this.totalCents = totalCents;
        this.createdAt = createdAt;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getCustomerId() {
        return customerId;
    }

    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public List<CreateOrderRequest.OrderItem> getItems() {
        return items;
    }

    public void setItems(List<CreateOrderRequest.OrderItem> items) {
        this.items = items;
    }

    public Long getTotalCents() {
        return totalCents;
    }

    public void setTotalCents(Long totalCents) {
        this.totalCents = totalCents;
    }

    public String getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(String createdAt) {
        this.createdAt = createdAt;
    }
}
