package com.example.orders.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.util.List;

public class CreateOrderRequest {

    @NotBlank
    @Size(min = 1, max = 64)
    private String customerId;

    @NotEmpty
    @Size(max = 50)
    @Valid
    private List<OrderItem> items;

    public String getCustomerId() {
        return customerId;
    }

    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public List<OrderItem> getItems() {
        return items;
    }

    public void setItems(List<OrderItem> items) {
        this.items = items;
    }
}
