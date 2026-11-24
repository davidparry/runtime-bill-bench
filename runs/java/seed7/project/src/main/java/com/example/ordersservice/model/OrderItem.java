package com.example.ordersservice.model;

import java.io.Serializable;

public class OrderItem implements Serializable {
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

    public int getUnitPriceCents() {
        return unitPriceCents;
    }

    public void setUnitPriceCents(int unitPriceCents) {
        this.unitPriceCents = unitPriceCents;
    }
}
