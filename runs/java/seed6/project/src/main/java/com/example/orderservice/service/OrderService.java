package com.example.orderservice.service;

import com.example.orderservice.model.Order;
import org.springframework.stereotype.Service;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

@Service
public class OrderService {

    private final Map<String, Order> orderStore = new ConcurrentHashMap<>();

    public Order createOrder(String customerId, java.util.List<com.example.orderservice.controller.OrdersController.CreateOrderRequest.OrderItemRequest> requestItems) {
        java.util.List<Order.OrderItem> items = requestItems.stream()
                .map(req -> new Order.OrderItem(req.getSku(), req.getQuantity(), req.getUnitPriceCents()))
                .toList();
        
        Order order = new Order(customerId, items);
        orderStore.put(order.getId(), order);
        return order;
    }

    public Order getOrder(String id) {
        return orderStore.get(id);
    }
}
