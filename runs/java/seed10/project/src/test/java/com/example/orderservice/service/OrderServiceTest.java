package com.example.orderservice.service;

import com.example.orderservice.model.Order;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

class OrderServiceTest {

    @Test
    void saveAndFindById() {
        OrderService orderService = new OrderService();
        String id = UUID.randomUUID().toString();
        Order order = new Order(id, "c-1", List.of(), 0, Instant.now());
        
        orderService.save(order);
        
        Order found = orderService.findById(id);
        assertNotNull(found);
        assertEquals(id, found.getId());
    }

    @Test
    void findNonExistentById() {
        OrderService orderService = new OrderService();
        Order found = orderService.findById("non-existent");
        assertNull(found);
    }
}
