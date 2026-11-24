package com.example.orderservice;

import com.example.orderservice.controller.OrdersController.CreateOrderRequest;
import com.example.orderservice.controller.OrdersController.CreateOrderRequest.OrderItemRequest;
import com.example.orderservice.model.Order;
import com.example.orderservice.service.OrderService;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class OrdersServiceTest {

    private final OrderService orderService = new OrderService();

    @Test
    void shouldCreateOrderWithCorrectTotalCents() {
        CreateOrderRequest request = new CreateOrderRequest();
        request.setCustomerId("c-1");
        
        OrderItemRequest item1 = new OrderItemRequest();
        item1.setSku("A-1");
        item1.setQuantity(2);
        item1.setUnitPriceCents(100);
        
        OrderItemRequest item2 = new OrderItemRequest();
        item2.setSku("B-2");
        item2.setQuantity(3);
        item2.setUnitPriceCents(200);
        
        request.setItems(List.of(item1, item2));

        Order order = orderService.createOrder(request.getCustomerId(), request.getItems());

        assertThat(order.getId()).isNotNull();
        assertThat(order.getCustomerId()).isEqualTo("c-1");
        assertThat(order.getTotalCents()).isEqualTo(800L); // 2*100 + 3*200
        assertThat(order.getCreatedAt()).isNotNull();
        assertThat(order.getItems()).hasSize(2);
    }

    @Test
    void shouldHandleLargeTotalCents() {
        CreateOrderRequest request = new CreateOrderRequest();
        request.setCustomerId("c-1");
        
        OrderItemRequest item = new OrderItemRequest();
        item.setSku("A-1");
        item.setQuantity(100);
        item.setUnitPriceCents(1000000);
        
        request.setItems(List.of(item));

        Order order = orderService.createOrder(request.getCustomerId(), request.getItems());

        assertThat(order.getTotalCents()).isEqualTo(100000000L);
    }
}
