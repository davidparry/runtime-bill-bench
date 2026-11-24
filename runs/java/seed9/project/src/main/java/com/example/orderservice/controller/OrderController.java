package com.example.orderservice.controller;

import com.example.orderservice.model.Order;
import com.example.orderservice.model.OrderItem;
import com.example.orderservice.service.OrderService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicLong;

@RestController
@RequestMapping("/orders")
@Validated
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    public ResponseEntity<Order> createOrder(@Valid @RequestBody OrderRequest request) {
        List<OrderItem> items = new ArrayList<>();
        for (OrderItemRequest itemReq : request.getItems()) {
            items.add(new OrderItem(itemReq.getSku(), itemReq.getQuantity(), itemReq.getUnitPriceCents()));
        }

        String orderId = UUID.randomUUID().toString();
        long totalCents = 0;
        for (OrderItemRequest itemReq : request.getItems()) {
            totalCents += (long) itemReq.getQuantity() * itemReq.getUnitPriceCents();
        }
        
        Order order = new Order(
                orderId,
                request.getCustomerId(),
                items,
                totalCents,
                Instant.now()
        );
        
        orderService.save(order);

        HttpHeaders headers = new HttpHeaders();
        headers.set(HttpHeaders.LOCATION, "/orders/" + orderId);
        
        return new ResponseEntity<>(order, headers, HttpStatus.CREATED);
    }

    @GetMapping("/{id}")
    public ResponseEntity<Order> getOrder(@PathVariable("id") String id) {
        Order order = orderService.findById(id);
        if (order == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(order);
    }

    // Request DTOs with validation annotations
    
    public static class OrderRequest {
        @NotBlank
        @Size(min = 1, max = 64)
        private String customerId;
        
        @NotEmpty
        @Size(min = 1, max = 50)
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
    }

    public static class OrderItemRequest {
        @NotBlank
        @Size(min = 1, max = 32)
        private String sku;
        
        @Min(1)
        @Max(100)
        private int quantity;
        
        @Min(1)
        @Max(1000000)
        private long unitPriceCents;

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

        public long getUnitPriceCents() {
            return unitPriceCents;
        }

        public void setUnitPriceCents(long unitPriceCents) {
            this.unitPriceCents = unitPriceCents;
        }
    }
}
