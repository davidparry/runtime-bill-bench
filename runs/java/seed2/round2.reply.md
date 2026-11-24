FILE: src/main/java/com/example/orderservice/controller/GlobalExceptionHandler.java
```java
package com.example.orderservice.controller;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.HashMap;
import java.util.Map;

@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, String>> handleValidationExceptions(MethodArgumentNotValidException ex) {
        Map<String, String> errors = new HashMap<>();
        errors.put("error", "Validation failed");
        return ResponseEntity.badRequest().body(errors);
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> handleIllegalArgument(IllegalArgumentException ex) {
        Map<String, String> errors = new HashMap<>();
        errors.put("error", ex.getMessage());
        return ResponseEntity.badRequest().body(errors);
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<Map<String, String>> handleGeneralExceptions(Exception ex) {
        Map<String, String> errors = new HashMap<>();
        errors.put("error", "Internal server error");
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(errors);
    }
}
```

FILE: src/main/java/com/example/orderservice/controller/HealthController.java
```java
package com.example.orderservice.controller;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
public class HealthController {

    @GetMapping("/health")
    public ResponseEntity<Map<String, String>> health() {
        return ResponseEntity.ok(Map.of("status", "ok"));
    }
}
```

FILE: src/main/java/com/example/orderservice/service/OrderService.java
```java
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
```

FILE: src/test/java/com/example/orderservice/OrderControllerTest.java
```java
package com.example.orderservice;

import com.example.orderservice.model.OrderItem;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void createOrder_success() throws Exception {
        String json = """
            {
                "customerId": "c-1",
                "items": [
                    {"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}
                ]
            }
            """;

        MvcResult result = mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json))
                .andExpect(status().isCreated())
                .andExpect(header().exists("Location"))
                .andExpect(jsonPath("$.customerId").value("c-1"))
                .andExpect(jsonPath("$.items[0].sku").value("A-1"))
                .andExpect(jsonPath("$.items[0].quantity").value(2))
                .andExpect(jsonPath("$.totalCents").value(2500))
                .andExpect(jsonPath("$.createdAt").isNotEmpty())
                .andReturn();

        String location = result.getResponse().getHeader("Location");
        assertThat(location).startsWith("/orders/");
        
        // Extract ID from location
        String orderId = location.substring(location.lastIndexOf('/') + 1);
        
        // Verify GET retrieves it
        mockMvc.perform(get("/orders/" + orderId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(orderId))
                .andExpect(jsonPath("$.totalCents").value(2500));
    }

    @Test
    void createOrder_invalidCustomerId() throws Exception {
        String json = """
            {
                "customerId": "",
                "items": [
                    {"sku": "A-1", "quantity": 1, "unitPriceCents": 100}
                ]
            }
            """;

        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").exists());
    }

    @Test
    void createOrder_invalidSku() throws Exception {
        String json = """
            {
                "customerId": "c-1",
                "items": [
                    {"sku": "", "quantity": 1, "unitPriceCents": 100}
                ]
            }
            """;

        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").exists());
    }

    @Test
    void createOrder_invalidQuantity() throws Exception {
        String json = """
            {
                "customerId": "c-1",
                "items": [
                    {"sku": "A-1", "quantity": 0, "unitPriceCents": 100}
                ]
            }
            """;

        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").exists());
    }

    @Test
    void createOrder_invalidUnitPrice() throws Exception {
        String json = """
            {
                "customerId": "c-1",
                "items": [
                    {"sku": "A-1", "quantity": 1, "unitPriceCents": 0}
                ]
            }
            """;

        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").exists());
    }

    @Test
    void createOrder_missingCustomerId() throws Exception {
        String json = """
            {
                "items": [
                    {"sku": "A-1", "quantity": 1, "unitPriceCents": 100}
                ]
            }
            """;

        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").exists());
    }

    @Test
    void createOrder_missingItems() throws Exception {
        String json = """
            {
                "customerId": "c-1"
            }
            """;

        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").exists());
    }

    @Test
    void getOrder_notFound() throws Exception {
        mockMvc.perform(get("/orders/non-existent-id"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error").exists());
    }

    @Test
    void healthCheck() throws Exception {
        mockMvc.perform(get("/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("ok"));
    }
}
```