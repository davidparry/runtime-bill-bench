package com.example.orderservice.controller;

import com.example.orderservice.dto.CreateOrderRequest;
import com.example.orderservice.dto.ErrorResponse;
import com.example.orderservice.dto.OrderResponse;
import com.example.orderservice.service.OrderStore;
import jakarta.validation.Valid;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.net.URI;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

@RestController
@RequestMapping("/orders")
public class OrdersController {

    private static final Logger log = LoggerFactory.getLogger(OrdersController.class);
    private final OrderStore orderStore;

    public OrdersController(OrderStore orderStore) {
        this.orderStore = orderStore;
    }

    @PostMapping
    public ResponseEntity<?> createOrder(@Valid @RequestBody CreateOrderRequest request) {
        OrderResponse response = orderStore.createOrder(request);
        return ResponseEntity.created(URI.create("/orders/" + response.getId()))
                .body(response);
    }

    @GetMapping("/{id}")
    public ResponseEntity<?> getOrder(@PathVariable String id) {
        Optional<OrderResponse> order = orderStore.getOrder(id);
        if (order.isPresent()) {
            return ResponseEntity.ok(order.get());
        } else {
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                    .body(new ErrorResponse("Order not found"));
        }
    }
}
