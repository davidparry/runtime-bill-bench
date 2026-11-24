package com.example.orderservice.service;

import com.example.orderservice.model.Order;
import com.example.orderservice.model.OrderItem;
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

    private final Map<String, Order> orderStore = new ConcurrentHashMap<>();

    public Order createOrder(String customerId, List<OrderItem> items) {
        // Validate items constraints
        if (items == null || items.isEmpty()) {
            throw new IllegalArgumentException("Items must not be empty");
        }
        if (items.size() > 50) {
            throw new IllegalArgumentException("Items must not exceed 50 entries");
        }

        long totalCents = 0;
        List<OrderItem> validatedItems = new ArrayList<>();

        for (OrderItem item : items) {
            if (item.getSku() == null || item.getSku().length() < 1 || item.getSku().length() > 32) {
                throw new IllegalArgumentException("SKU must be between 1 and 32 characters");
            }
            if (item.getQuantity() == null || item.getQuantity() < 1 || item.getQuantity() > 100) {
                throw new IllegalArgumentException("Quantity must be between 1 and 100");
            }
            if (item.getUnitPriceCents() == null || item.getUnitPriceCents() < 1 || item.getUnitPriceCents() > 1000000) {
                throw new IllegalArgumentException("Unit price must be between 1 and 1000000");
            }

            // Calculate total carefully to avoid overflow if needed, though Long max is huge
            long itemTotal = item.getQuantity() * item.getUnitPriceCents();
            totalCents += itemTotal;
            
            // Deep copy item to ensure immutability from caller side if needed
            OrderItem copy = new OrderItem();
            copy.setSku(item.getSku());
            copy.setQuantity(item.getQuantity());
            copy.setUnitPriceCents(item.getUnitPriceCents());
            validatedItems.add(copy);
        }

        String orderId = UUID.randomUUID().toString();
        String createdAt = Instant.now().atZone(ZoneOffset.UTC).format(DateTimeFormatter.ISO_INSTANT);

        Order order = new Order();
        order.setId(orderId);
        order.setCustomerId(customerId);
        order.setItems(validatedItems);
        order.setTotalCents(totalCents);
        order.setCreatedAt(createdAt);

        orderStore.put(orderId, order);
        return order;
    }

    public Order getOrder(String id) {
        return orderStore.get(id);
    }
}
