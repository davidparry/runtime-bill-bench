package com.example.orderservice.controller;

import com.example.orderservice.model.Order;
import com.example.orderservice.model.OrderItem;
import com.example.orderservice.service.OrderStore;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;
import java.util.HashMap;

@RestController
@RequestMapping("/orders")
public class OrdersController {

    private final OrderStore orderStore;

    public OrdersController(OrderStore orderStore) {
        this.orderStore = orderStore;
    }

    @PostMapping
    public ResponseEntity<?> createOrder(@Valid @RequestBody CreateOrderRequest request) {
        List<OrderItem> items = request.getItems();
        Order order = new Order(request.getCustomerId(), items);
        orderStore.save(order);
        
        Map<String, Object> response = new HashMap<>();
        response.put("id", order.getId());
        response.put("customerId", order.getCustomerId());
        response.put("items", order.getItems());
        response.put("totalCents", order.getTotalCents());
        response.put("createdAt", order.getCreatedAtIso());

        return ResponseEntity
                .status(HttpStatus.CREATED)
                .header("Location", "/orders/" + order.getId())
                .body(response);
    }

    @GetMapping("/{id}")
    public ResponseEntity<?> getOrder(@PathVariable String id) {
        Order order = orderStore.findById(id);
        if (order == null) {
            Map<String, String> error = new HashMap<>();
            error.put("error", "Order not found");
            return ResponseEntity.status(HttpStatus.NOT_FOUND).body(error);
        }

        Map<String, Object> response = new HashMap<>();
        response.put("id", order.getId());
        response.put("customerId", order.getCustomerId());
        response.put("items", order.getItems());
        response.put("totalCents", order.getTotalCents());
        response.put("createdAt", order.getCreatedAtIso());

        return ResponseEntity.ok(response);
    }
}

class CreateOrderRequest {
    private String customerId;
    private List<OrderItem> items;

    // Getters and Setters for Jackson
    public String getCustomerId() { return customerId; }
    public void setCustomerId(String customerId) { this.customerId = customerId; }
    public List<OrderItem> getItems() { return items; }
    public void setItems(List<OrderItem> items) { this.items = items; }
}
