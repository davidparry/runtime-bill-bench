package com.example.orderservice.model;

import com.fasterxml.jackson.annotation.JsonProperty;

public class OrderItem {

    private String sku;
    private int quantity;
    private int unitPriceCents;

    public OrderItem() {
    }

    public OrderItem(String sku, int quantity, int unitPriceCents) {
        this.sku = sku;
        this.quantity = quantity;
        this.unitPriceCents = unitPriceCents;
    }

    @JsonProperty("sku")
    public String getSku() {
        return sku;
    }

    public void setSku(String sku) {
        this.sku = sku;
    }

    @JsonProperty("quantity")
    public int getQuantity() {
        return quantity;
    }

    public void setQuantity(int quantity) {
        this.quantity = quantity;
    }

    @JsonProperty("unitPriceCents")
    public int getUnitPriceCents() {
        return unitPriceCents;
    }

    public void setUnitPriceCents(int unitPriceCents) {
        this.unitPriceCents = unitPriceCents;
    }
}
