package com.example.orderservice.service;

import com.example.orderservice.controller.OrderController.CreateOrderItem;
import com.example.orderservice.model.Order;
import com.example.orderservice.model.OrderItem;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.locks.ReadWriteLock;
import java.util.concurrent.locks.ReentrantReadWriteLock;

@Service
public class OrderService {

    private final Map<String, Order> orders = new ConcurrentHashMap<>();
    private final ReadWriteLock lock = new ReentrantReadWriteLock();

    public Order createOrder(String customerId, List<CreateOrderItem> items) {
        Order order = new Order();
        order.setCustomerId(customerId);

        List<OrderItem> orderItems = new ArrayList<>();
        for (CreateOrderItem item : items) {
            OrderItem orderItem = new OrderItem();
            orderItem.setSku(item.getSku());
            orderItem.setQuantity(item.getQuantity());
            orderItem.setUnitPriceCents(item.getUnitPriceCents());
            orderItems.add(orderItem);
        }
        order.setItems(orderItems);
        order.calculateTotal();

        lock.writeLock().lock();
        try {
            orders.put(order.getId(), order);
        } finally {
            lock.writeLock().unlock();
        }

        return order;
    }

    public Order getOrder(String id) {
        lock.readLock().lock();
        try {
            return orders.get(id);
        } finally {
            lock.readLock().unlock();
        }
    }
}
