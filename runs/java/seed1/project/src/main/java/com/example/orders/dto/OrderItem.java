package com.example.orders.dto;

import jakarta.validation.constraints.*;

public class OrderItem {

    @NotBlank
    @Size(min = 1, max = 32)
    private String sku;

    @Min(1)
    @Max(100)
    private Integer quantity;

    @Min(1)
    @Max(1000000)
    private Long unitPriceCents;

    public String getSku() {
        return sku;
    }

    public void setSku(String sku) {
        this.sku = sku;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }

    public Long getUnitPriceCents() {
        return unitPriceCents;
    }

    public void setUnitPriceCents(Long unitPriceCents) {
        this.unitPriceCents = unitPriceCents;
    }
}
