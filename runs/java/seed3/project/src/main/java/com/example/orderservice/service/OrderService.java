package com.example.orderservice.service;

import com.example.orderservice.model.OrderItem;
import com.example.orderservice.model.OrderRequest;
import com.example.orderservice.model.OrderResponse;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

@Service
public class OrderService {

    private final Map<String, OrderResponse> orders = new ConcurrentHashMap<>();
    private static final DateTimeFormatter FORMATTER = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'")
            .withZone(ZoneOffset.UTC);

    public OrderResponse createOrder(OrderRequest request) {
        String id = UUID.randomUUID().toString();
        String createdAt = Instant.now().atZone(ZoneOffset.UTC).format(FORMATTER);
        
        long totalCents = 0;
        for (OrderItem item : request.getItems()) {
            totalCents += item.getQuantity() * item.getUnitPriceCents();
        }

        OrderResponse order = new OrderResponse(
                id,
                request.getCustomerId(),
                request.getItems(),
                totalCents,
                createdAt
        );

        orders.put(id, order);
        return order;
    }

    public OrderResponse getOrder(String id) {
        return orders.get(id);
    }
}
