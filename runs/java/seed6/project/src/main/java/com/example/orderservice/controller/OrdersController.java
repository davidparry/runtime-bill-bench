package com.example.orderservice.controller;

import com.example.orderservice.model.Order;
import com.example.orderservice.service.OrderService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/orders")
public class OrdersController {

    private final OrderService orderService;

    public OrdersController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    public ResponseEntity<?> createOrder(@RequestBody @Valid CreateOrderRequest request) {
        Order createdOrder = orderService.createOrder(request.getCustomerId(), request.getItems());
        
        HttpHeaders headers = new HttpHeaders();
        headers.set(HttpHeaders.LOCATION, "/orders/" + createdOrder.getId());
        
        return new ResponseEntity<>(createdOrder, headers, HttpStatus.CREATED);
    }

    @GetMapping("/{id}")
    public ResponseEntity<?> getOrder(@PathVariable String id) {
        // Validate UUID format first to avoid unnecessary service lookup if invalid
        try {
            UUID.fromString(id);
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest().body(new ErrorResponse("Invalid order ID format"));
        }

        Order order = orderService.getOrder(id);
        if (order == null) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                    .body(new ErrorResponse("Order not found: " + id));
        }
        return ResponseEntity.ok(order);
    }

    // DTO for request validation
    public static class CreateOrderRequest {
        @NotBlank(message = "customerId is required")
        @Size(min = 1, max = 64, message = "customerId must be between 1 and 64 characters")
        private String customerId;

        @NotNull(message = "items is required")
        @Valid
        @Size(min = 1, max = 50, message = "items must contain between 1 and 50 entries")
        private List<OrderItemRequest> items;

        public String getCustomerId() {
            return customerId;
        }

        public void setCustomerId(String customerId) {
            this.customerId = customerId;
        }

        public List<OrderItemRequest> getItems() {
            return items;
        }

        public void setItems(List<OrderItemRequest> items) {
            this.items = items;
        }

        public static class OrderItemRequest {
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
            private Integer unitPriceCents;

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

            public Integer getUnitPriceCents() {
                return unitPriceCents;
            }

            public void setUnitPriceCents(Integer unitPriceCents) {
                this.unitPriceCents = unitPriceCents;
            }
        }
    }

    public static class ErrorResponse {
        private final String error;

        public ErrorResponse(String error) {
            this.error = error;
        }

        public String getError() {
            return error;
        }
    }
}
