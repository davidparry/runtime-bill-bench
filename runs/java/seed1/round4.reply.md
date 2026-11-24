FILE: src/test/java/com/example/orders/OrdersControllerIntegrationTest.java
```java
package com.example.orders;

import com.example.orders.dto.CreateOrderRequest;
import com.example.orders.dto.OrderItem;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrdersControllerIntegrationTest {

    @Autowired
    private TestRestTemplate restTemplate;

    @LocalServerPort
    private int port;

    @Test
    void createOrder_success() {
        CreateOrderRequest request = new CreateOrderRequest();
        request.setCustomerId("c-1");
        
        OrderItem item = new OrderItem();
        item.setSku("A-1");
        item.setQuantity(2);
        item.setUnitPriceCents(1250L);
        request.setItems(List.of(item));

        ResponseEntity<Map> response = restTemplate.postForEntity("/orders", request, Map.class);

        assertEquals(HttpStatus.CREATED, response.getStatusCode());
        assertNotNull(response.getHeaders().getLocation());
        assertTrue(response.getHeaders().getLocation().toString().endsWith("/orders/" + response.getBody().get("id")));
        
        Map<String, Object> body = response.getBody();
        assertNotNull(body.get("id"));
        assertEquals("c-1", body.get("customerId"));
        // totalCents is long, but Jackson might deserialize to Integer if it fits. 
        // Using assertEquals with correct type or checking value.
        // The spec says totalCents can reach 5B, so it's long. 
        // Jackson usually maps to Long for 64-bit ints if configured, but default might vary.
        // Let's just check the numeric value.
        assertEquals(2500L, body.get("totalCents"));
        assertNotNull(body.get("createdAt"));
        
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> items = (List<Map<String, Object>>) body.get("items");
        assertEquals(1, items.size());
        Map<String, Object> itemMap = items.get(0);
        assertEquals("A-1", itemMap.get("sku"));
        assertEquals(2, itemMap.get("quantity"));
        assertEquals(1250L, itemMap.get("unitPriceCents"));
    }

    @Test
    void createOrder_invalidCustomerId() {
        CreateOrderRequest request = new CreateOrderRequest();
        request.setCustomerId(""); // Blank
        request.setItems(List.of(new OrderItem()));

        ResponseEntity<Map> response = restTemplate.postForEntity("/orders", request, Map.class);

        assertEquals(HttpStatus.BAD_REQUEST, response.getStatusCode());
        assertNotNull(response.getBody().get("error"));
    }

    @Test
    void createOrder_invalidQuantity() {
        CreateOrderRequest request = new CreateOrderRequest();
        request.setCustomerId("c-1");
        
        OrderItem item = new OrderItem();
        item.setSku("A-1");
        item.setQuantity(0); // Too low
        item.setUnitPriceCents(100L);
        request.setItems(List.of(item));

        ResponseEntity<Map> response = restTemplate.postForEntity("/orders", request, Map.class);

        assertEquals(HttpStatus.BAD_REQUEST, response.getStatusCode());
        assertNotNull(response.getBody().get("error"));
    }

    @Test
    void getOrder_notFound() {
        ResponseEntity<Map> response = restTemplate.getForEntity("/orders/non-existent-id", Map.class);

        assertEquals(HttpStatus.NOT_FOUND, response.getStatusCode());
        assertNotNull(response.getBody().get("error"));
    }

    @Test
    void createOrder_invalidJson() {
        ResponseEntity<Map> response = restTemplate.postForEntity("/orders", "{invalid json}", Map.class);

        assertEquals(HttpStatus.BAD_REQUEST, response.getStatusCode());
        assertNotNull(response.getBody().get("error"));
    }
}
```

FILE: src/main/java/com/example/orders/controller/OrdersController.java
```java
package com.example.orders.controller;

import com.example.orders.dto.CreateOrderRequest;
import com.example.orders.dto.OrderResponse;
import com.example.orders.service.OrderService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.resource.NoResourceFoundException;

import java.net.URI;
import java.util.Map;

@RestController
@RequestMapping("/orders")
public class OrdersController {

    private final OrderService orderService;

    public OrdersController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    public ResponseEntity<?> createOrder(@Valid @RequestBody CreateOrderRequest request) {
        OrderResponse response = orderService.createOrder(request);
        return ResponseEntity
                .created(URI.create("/orders/" + response.getId()))
                .body(response);
    }

    @GetMapping("/{id}")
    public ResponseEntity<?> getOrder(@PathVariable String id) {
        OrderResponse response = orderService.getOrder(id);
        if (response == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(response);
    }
    
    @ExceptionHandler(NoResourceFoundException.class)
    public ResponseEntity<Map<String, String>> handleNotFound(NoResourceFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("error", "No order found"));
    }
}
```