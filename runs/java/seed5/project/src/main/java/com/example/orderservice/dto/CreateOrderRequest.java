package com.example.orderservice.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.util.List;

@JsonInclude(JsonInclude.Include.NON_NULL)
public class CreateOrderRequest {

    @NotBlank(message = "customerId is required")
    @Size(min = 1, max = 64, message = "customerId must be between 1 and 64 characters")
    private String customerId;

    @NotEmpty(message = "items must not be empty")
    @Size(min = 1, max = 50, message = "items must have between 1 and 50 entries")
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

    public static class OrderItem {
        @NotBlank(message = "sku is required")
        @Size(min = 1, max = 32, message = "sku must be between 1 and 32 characters")
        private String sku;

        @NotNull(message = "quantity is required")
        @Min(value = 1, message = "quantity must be at least 1")
        @Max(value = 100, message = "quantity must be at most 100")
        private Integer quantity;

        @NotNull(message = "unitPriceCents is required")
        @Min(value = 1, message = "unitPriceCents must be at least 1")
        @Max(value = 1000000, message = "unitPriceCents must be at most 1000000")
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
}
