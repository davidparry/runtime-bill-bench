package com.example.orders;

import com.example.orders.dto.CreateOrderRequest;
import com.example.orders.dto.OrderItem;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ValidationRulesTest {

    @Autowired
    private TestRestTemplate restTemplate;

    @Test
    void customerIdTooLong() {
        CreateOrderRequest request = new CreateOrderRequest();
        request.setCustomerId("a".repeat(65)); // Max 64
        request.setItems(List.of(new OrderItem()));

        ResponseEntity<Map> response = restTemplate.postForEntity("/orders", request, Map.class);
        assertEquals(HttpStatus.BAD_REQUEST, response.getStatusCode());
    }

    @Test
    void skuTooLong() {
        CreateOrderRequest request = new CreateOrderRequest();
        request.setCustomerId("c-1");
        
        OrderItem item = new OrderItem();
        item.setSku("a".repeat(33)); // Max 32
        item.setQuantity(1);
        item.setUnitPriceCents(100L);
        request.setItems(List.of(item));

        ResponseEntity<Map> response = restTemplate.postForEntity("/orders", request, Map.class);
        assertEquals(HttpStatus.BAD_REQUEST, response.getStatusCode());
    }

    @Test
    void quantityTooHigh() {
        CreateOrderRequest request = new CreateOrderRequest();
        request.setCustomerId("c-1");
        
        OrderItem item = new OrderItem();
        item.setSku("A-1");
        item.setQuantity(101); // Max 100
        item.setUnitPriceCents(100L);
        request.setItems(List.of(item));

        ResponseEntity<Map> response = restTemplate.postForEntity("/orders", request, Map.class);
        assertEquals(HttpStatus.BAD_REQUEST, response.getStatusCode());
    }

    @Test
    void unitPriceCentsTooHigh() {
        CreateOrderRequest request = new CreateOrderRequest();
        request.setCustomerId("c-1");
        
        OrderItem item = new OrderItem();
        item.setSku("A-1");
        item.setQuantity(1);
        item.setUnitPriceCents(1000001L); // Max 1000000
        request.setItems(List.of(item));

        ResponseEntity<Map> response = restTemplate.postForEntity("/orders", request, Map.class);
        assertEquals(HttpStatus.BAD_REQUEST, response.getStatusCode());
    }
    
    @Test
    void itemsTooMany() {
        CreateOrderRequest request = new CreateOrderRequest();
        request.setCustomerId("c-1");
        
        List<OrderItem> items = new java.util.ArrayList<>();
        for (int i = 0; i < 51; i++) {
            OrderItem item = new OrderItem();
            item.setSku("A-" + i);
            item.setQuantity(1);
            item.setUnitPriceCents(100L);
            items.add(item);
        }
        request.setItems(items);

        ResponseEntity<Map> response = restTemplate.postForEntity("/orders", request, Map.class);
        assertEquals(HttpStatus.BAD_REQUEST, response.getStatusCode());
    }
}
