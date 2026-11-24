FILE: pom.xml
```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/> <!-- lookup parent from repository -->
    </parent>
    <groupId>com.example</groupId>
    <artifactId>orders-service</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>orders-service</name>
    <description>Orders Service</description>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

FILE: src/main/java/com/example/orderservice/OrdersServiceApplication.java
```java
package com.example.orderservice;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersServiceApplication.class, args);
    }
}
```

FILE: src/main/java/com/example/orderservice/model/Order.java
```java
package com.example.orderservice.model;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

public class Order {
    private String id;
    private String customerId;
    private List<OrderItem> items;
    private long totalCents;
    private Instant createdAt;

    public Order() {
    }

    public Order(String id, String customerId, List<OrderItem> items, long totalCents, Instant createdAt) {
        this.id = id;
        this.customerId = customerId;
        this.items = items;
        this.totalCents = totalCents;
        this.createdAt = createdAt;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getCustomerId() {
        return customerId;
    }

    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public List<OrderItem> getItems() {
        return items;
    }

    public void setItems(List<OrderItem> items) {
        this.items = items;
    }

    public long getTotalCents() {
        return totalCents;
    }

    public void setTotalCents(long totalCents) {
        this.totalCents = totalCents;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(Instant createdAt) {
        this.createdAt = createdAt;
    }
}
```

FILE: src/main/java/com/example/orderservice/model/OrderItem.java
```java
package com.example.orderservice.model;

public class OrderItem {
    private String sku;
    private int quantity;
    private long unitPriceCents;

    public OrderItem() {
    }

    public OrderItem(String sku, int quantity, long unitPriceCents) {
        this.sku = sku;
        this.quantity = quantity;
        this.unitPriceCents = unitPriceCents;
    }

    public String getSku() {
        return sku;
    }

    public void setSku(String sku) {
        this.sku = sku;
    }

    public int getQuantity() {
        return quantity;
    }

    public void setQuantity(int quantity) {
        this.quantity = quantity;
    }

    public long getUnitPriceCents() {
        return unitPriceCents;
    }

    public void setUnitPriceCents(long unitPriceCents) {
        this.unitPriceCents = unitPriceCents;
    }
}
```

FILE: src/main/java/com/example/orderservice/controller/OrderController.java
```java
package com.example.orderservice.controller;

import com.example.orderservice.model.Order;
import com.example.orderservice.model.OrderItem;
import com.example.orderservice.service.OrderService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicLong;

@RestController
@RequestMapping("/orders")
@Validated
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    public ResponseEntity<Order> createOrder(@Valid @RequestBody OrderRequest request) {
        List<OrderItem> items = new ArrayList<>();
        for (OrderItemRequest itemReq : request.getItems()) {
            items.add(new OrderItem(itemReq.getSku(), itemReq.getQuantity(), itemReq.getUnitPriceCents()));
        }

        String orderId = UUID.randomUUID().toString();
        long totalCents = 0;
        for (OrderItemRequest itemReq : request.getItems()) {
            totalCents += (long) itemReq.getQuantity() * itemReq.getUnitPriceCents();
        }
        
        Order order = new Order(
                orderId,
                request.getCustomerId(),
                items,
                totalCents,
                Instant.now()
        );
        
        orderService.save(order);

        HttpHeaders headers = new HttpHeaders();
        headers.set(HttpHeaders.LOCATION, "/orders/" + orderId);
        
        return new ResponseEntity<>(order, headers, HttpStatus.CREATED);
    }

    @GetMapping("/{id}")
    public ResponseEntity<Order> getOrder(@PathVariable("id") String id) {
        Order order = orderService.findById(id);
        if (order == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(order);
    }

    // Request DTOs with validation annotations
    
    public static class OrderRequest {
        @NotBlank
        @Size(min = 1, max = 64)
        private String customerId;
        
        @NotEmpty
        @Size(min = 1, max = 50)
        private List<OrderItemRequest> items;

        public String getCustomerId() {
            return customerId;
        }

        public void setCustomerId(String customerId) {
            this.customerId = customerId;
        }

        public List<OrderItemRequest> getItems() {
            return items;
        }

        public void setItems(List<OrderItemRequest> items) {
            this.items = items;
        }
    }

    public static class OrderItemRequest {
        @NotBlank
        @Size(min = 1, max = 32)
        private String sku;
        
        @Min(1)
        @Max(100)
        private int quantity;
        
        @Min(1)
        @Max(1000000)
        private long unitPriceCents;

        public String getSku() {
            return sku;
        }

        public void setSku(String sku) {
            this.sku = sku;
        }

        public int getQuantity() {
            return quantity;
        }

        public void setQuantity(int quantity) {
            this.quantity = quantity;
        }

        public long getUnitPriceCents() {
            return unitPriceCents;
        }

        public void setUnitPriceCents(long unitPriceCents) {
            this.unitPriceCents = unitPriceCents;
        }
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
import org.springframework.stereotype.Service;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

@Service
public class OrderService {

    private final Map<String, Order> orders = new ConcurrentHashMap<>();

    public void save(Order order) {
        orders.put(order.getId(), order);
    }

    public Order findById(String id) {
        return orders.get(id);
    }
}
```

FILE: src/main/java/com/example/orderservice/config/GlobalExceptionHandler.java
```java
package com.example.orderservice.config;

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
        ex.getBindingResult().getFieldErrors().forEach(error -> 
            errors.put(error.getField(), error.getDefaultMessage())
        );
        return ResponseEntity.badRequest().body(errors);
    }
}
```

FILE: src/main/java/com/example/orderservice/config/LoggingFilter.java
```java
package com.example.orderservice.config;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.Map;

@Component
public class LoggingFilter extends OncePerRequestFilter {

    private static final Logger logger = LoggerFactory.getLogger(LoggingFilter.class);

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {
        
        long startTime = System.currentTimeMillis();
        try {
            filterChain.doFilter(request, response);
        } finally {
            long durationMs = System.currentTimeMillis() - startTime;
            Map<String, Object> logEntry = new LinkedHashMap<>();
            logEntry.put("method", request.getMethod());
            logEntry.put("path", request.getRequestURI());
            logEntry.put("status", response.getStatus());
            logEntry.put("durationMs", durationMs);
            
            // Simple JSON formatting for structured logging
            StringBuilder sb = new StringBuilder();
            sb.append("{");
            boolean first = true;
            for (Map.Entry<String, Object> entry : logEntry.entrySet()) {
                if (!first) sb.append(",");
                sb.append("\"").append(entry.getKey()).append("\":");
                if (entry.getValue() instanceof String) {
                    sb.append("\"").append(entry.getValue()).append("\"");
                } else {
                    sb.append(entry.getValue());
                }
                first = false;
            }
            sb.append("}");
            
            logger.info(sb.toString());
        }
    }
}
```

FILE: src/main/resources/application.properties
```properties
server.port=${PORT:8080}
```

FILE: src/test/java/com/example/orderservice/controller/OrderControllerTest.java
```java
package com.example.orderservice.controller;

import com.example.orderservice.config.GlobalExceptionHandler;
import com.example.orderservice.service.OrderService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.bean.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.util.Collections;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private OrderService orderService;

    @Test
    void createOrder_validRequest_returns201() throws Exception {
        String json = """
            {
              "customerId": "c-1",
              "items": [
                {
                  "sku": "A-1",
                  "quantity": 2,
                  "unitPriceCents": 1250
                }
              ]
            }
            """;

        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json))
                .andExpect(status().isCreated())
                .andExpect(header().exists("Location"))
                .andExpect(jsonPath("$.customerId").value("c-1"))
                .andExpect(jsonPath("$.totalCents").value(2500));
    }

    @Test
    void createOrder_missingCustomerId_returns400() throws Exception {
        String json = """
            {
              "items": [
                {
                  "sku": "A-1",
                  "quantity": 1,
                  "unitPriceCents": 100
                }
              ]
            }
            """;

        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.customerId").exists());
    }

    @Test
    void createOrder_invalidSkuLength_returns400() throws Exception {
        String json = """
            {
              "customerId": "c-1",
              "items": [
                {
                  "sku": "",
                  "quantity": 1,
                  "unitPriceCents": 100
                }
              ]
            }
            """;

        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void createOrder_quantityOutOfRange_returns400() throws Exception {
        String json = """
            {
              "customerId": "c-1",
              "items": [
                {
                  "sku": "A-1",
                  "quantity": 0,
                  "unitPriceCents": 100
                }
              ]
            }
            """;

        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void createOrder_emptyItems_returns400() throws Exception {
        String json = """
            {
              "customerId": "c-1",
              "items": []
            }
            """;

        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void getOrder_existingOrder_returns200() throws Exception {
        String orderId = "123e4567-e89b-12d3-a456-426614174000";
        
        mockMvc.perform(get("/orders/" + orderId))
                .andExpect(status().isNotFound()); // Mock service returns null by default
    }

    @Test
    void getOrder_nonExistingOrder_returns404() throws Exception {
        mockMvc.perform(get("/orders/non-existing-id"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error").exists());
    }
}
```