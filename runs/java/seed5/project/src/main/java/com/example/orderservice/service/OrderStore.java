package com.example.orderservice.service;

import com.example.orderservice.dto.CreateOrderRequest;
import com.example.orderservice.dto.OrderResponse;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

@Component
public class OrderStore {

    private final Map<String, OrderRecord> orders = new ConcurrentHashMap<>();

    public OrderResponse createOrder(CreateOrderRequest request) {
        String id = UUID.randomUUID().toString();
        String customerId = request.getCustomerId();
        List<CreateOrderRequest.OrderItem> items = request.getItems();
        
        long totalCents = items.stream()
                .mapToLong(item -> item.getQuantity() * item.getUnitPriceCents())
                .sum();

        String createdAt = Instant.now().atZone(ZoneOffset.UTC).format(DateTimeFormatter.ISO_INSTANT);

        OrderRecord record = new OrderRecord(id, customerId, items, totalCents, createdAt);
        orders.put(id, record);

        return new OrderResponse(id, customerId, items, totalCents, createdAt);
    }

    public Optional<OrderResponse> getOrder(String id) {
        return Optional.ofNullable(orders.get(id)).map(this::toResponse);
    }

    private OrderResponse toResponse(OrderRecord record) {
        return new OrderResponse(
                record.id,
                record.customerId,
                record.items,
                record.totalCents,
                record.createdAt
        );
    }

    private static class OrderRecord {
        final String id;
        final String customerId;
        final List<CreateOrderRequest.OrderItem> items;
        final Long totalCents;
        final String createdAt;

        OrderRecord(String id, String customerId, List<CreateOrderRequest.OrderItem> items, Long totalCents, String createdAt) {
            this.id = id;
            this.customerId = customerId;
            this.items = items;
            this.totalCents = totalCents;
            this.createdAt = createdAt;
        }
    }
}
