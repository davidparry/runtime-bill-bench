package com.example.orders.service;

import com.example.orders.dto.CreateOrderRequest;
import com.example.orders.dto.OrderItem;
import com.example.orders.dto.OrderResponse;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

@Service
public class OrderService {

    private final Map<String, OrderResponse> store = new ConcurrentHashMap<>();

    public OrderResponse createOrder(CreateOrderRequest request) {
        String id = UUID.randomUUID().toString();
        List<OrderItem> items = request.getItems();
        
        long totalCents = 0;
        List<OrderItem> responseItems = new ArrayList<>();
        
        for (OrderItem item : items) {
            long itemTotal = item.getQuantity() * item.getUnitPriceCents();
            totalCents += itemTotal;
            // Create a copy to ensure immutability in store if needed, 
            // though simple POJOs in this context are usually safe if not mutated later.
            // We'll just store the reference as per simple requirements, but good practice 
            // would be deep copy if items are mutable. Here they are simple DTOs.
            responseItems.add(item);
        }

        String createdAt = DateTimeFormatter.ISO_INSTANT.format(Instant.now());

        OrderResponse response = new OrderResponse(id, request.getCustomerId(), responseItems, totalCents, createdAt);
        store.put(id, response);
        return response;
    }

    public OrderResponse getOrder(String id) {
        return store.get(id);
    }
}
