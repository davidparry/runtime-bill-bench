package com.example.ordersservice.service;

import com.example.ordersservice.controller.OrderController.CreateOrderItemRequest;
import com.example.ordersservice.model.Order;
import com.example.ordersservice.model.OrderItem;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

@Service
public class OrderService {

    private final Map<String, Order> orders = new ConcurrentHashMap<>();

    public Order createOrder(String customerId, List<CreateOrderItemRequest> items) {
        Order order = new Order();
        order.setCustomerId(customerId);

        long totalCents = 0;
        List<OrderItem> orderItems = new ArrayList<>(items.size());

        for (CreateOrderItemRequest itemReq : items) {
            OrderItem item = new OrderItem();
            item.setSku(itemReq.getSku());
            item.setQuantity(itemReq.getQuantity());
            item.setUnitPriceCents(itemReq.getUnitPriceCents());
            
            long itemTotal = (long) itemReq.getQuantity() * itemReq.getUnitPriceCents();
            totalCents += itemTotal;
            
            orderItems.add(item);
        }

        order.setItems(orderItems);
        order.setTotalCents(totalCents);

        orders.put(order.getId(), order);
        return order;
    }

    public Order getOrder(String id) {
        return orders.get(id);
    }
}
