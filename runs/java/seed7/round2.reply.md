FILE: src/main/java/com/example/ordersservice/controller/OrderController.java
```java
package com.example.ordersservice.controller;

import com.example.ordersservice.model.Order;
import com.example.ordersservice.model.OrderItem;
import com.example.ordersservice.service.OrderService;
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
import org.springframework.web.bind.annotation.RestController;

import java.util.ArrayList;
import java.util.List;

@RestController
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping("/orders")
    public ResponseEntity<Order> createOrder(@Valid @RequestBody CreateOrderRequest request) {
        Order createdOrder = orderService.createOrder(request.getCustomerId(), request.getItems());
        String location = "/orders/" + createdOrder.getId();
        return ResponseEntity.created(java.net.URI.create(location))
                .header(HttpHeaders.CONTENT_TYPE, "application/json")
                .body(createdOrder);
    }

    @GetMapping("/orders/{id}")
    public ResponseEntity<Object> getOrder(@PathVariable String id) {
        Order order = orderService.getOrder(id);
        if (order == null) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                    .body(new ErrorResponse("Order not found"));
        }
        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_TYPE, "application/json")
                .body(order);
    }

    @GetMapping("/health")
    public ResponseEntity<HealthResponse> health() {
        return ResponseEntity.ok(new HealthResponse("ok"));
    }

    public static class CreateOrderRequest {
        @NotBlank
        @Size(min = 1, max = 64)
        private String customerId;

        @NotNull
        @Size(min = 1, max = 50)
        private List<CreateOrderItemRequest> items;

        public String getCustomerId() {
            return customerId;
        }

        public void setCustomerId(String customerId) {
            this.customerId = customerId;
        }

        public List<CreateOrderItemRequest> getItems() {
            return items;
        }

        public void setItems(List<CreateOrderItemRequest> items) {
            this.items = items;
        }
    }

    public static class CreateOrderItemRequest {
        @NotBlank
        @Size(min = 1, max = 32)
        private String sku;

        @NotNull
        @Min(1)
        @Max(100)
        private Integer quantity;

        @NotNull
        @Min(1)
        @Max(1000000)
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

    public static class HealthResponse {
        private String status;

        public HealthResponse(String status) {
            this.status = status;
        }

        public String getStatus() {
            return status;
        }
    }

    public static class ErrorResponse {
        private String error;

        public ErrorResponse(String error) {
            this.error = error;
        }

        public String getError() {
            return error;
        }
    }
}
```