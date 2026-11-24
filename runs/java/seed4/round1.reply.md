FILE: pom.xml
```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.2.4</version>
        <relativePath/> <!-- lookup parent from repository -->
    </parent>

    <groupId>com.example</groupId>
    <artifactId>orders-service</artifactId>
    <version>1.0.0-SNAPSHOT</version>
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

import java.math.BigDecimal;
import java.util.Objects;
import java.util.UUID;
import java.time.Instant;

public class Order {

    private final String id;
    private final String customerId;
    private final java.util.List<OrderItem> items;
    private final long totalCents;
    private final Instant createdAt;

    public Order(String customerId, java.util.List<OrderItem> items) {
        this.id = UUID.randomUUID().toString();
        this.customerId = customerId;
        this.items = java.util.Collections.unmodifiableList(new java.util.ArrayList<>(items));
        this.totalCents = calculateTotalCents(items);
        this.createdAt = Instant.now();
    }

    private long calculateTotalCents(java.util.List<OrderItem> items) {
        long total = 0;
        for (OrderItem item : items) {
            total += item.getQuantity() * item.getUnitPriceCents();
        }
        return total;
    }

    public String getId() {
        return id;
    }

    public String getCustomerId() {
        return customerId;
    }

    public java.util.List<OrderItem> getItems() {
        return items;
    }

    public long getTotalCents() {
        return totalCents;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public String getCreatedAtIso() {
        return java.time.format.DateTimeFormatter.ISO_INSTANT.format(createdAt);
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (o == null || getClass() != o.getClass()) return false;
        Order order = (Order) o;
        return Objects.equals(id, order.id);
    }

    @Override
    public int hashCode() {
        return Objects.hash(id);
    }
}
```

FILE: src/main/java/com/example/orderservice/model/OrderItem.java
```java
package com.example.orderservice.model;

import com.fasterxml.jackson.annotation.JsonProperty;

public class OrderItem {

    private String sku;
    private int quantity;
    private int unitPriceCents;

    public OrderItem() {
    }

    public OrderItem(String sku, int quantity, int unitPriceCents) {
        this.sku = sku;
        this.quantity = quantity;
        this.unitPriceCents = unitPriceCents;
    }

    @JsonProperty("sku")
    public String getSku() {
        return sku;
    }

    public void setSku(String sku) {
        this.sku = sku;
    }

    @JsonProperty("quantity")
    public int getQuantity() {
        return quantity;
    }

    public void setQuantity(int quantity) {
        this.quantity = quantity;
    }

    @JsonProperty("unitPriceCents")
    public int getUnitPriceCents() {
        return unitPriceCents;
    }

    public void setUnitPriceCents(int unitPriceCents) {
        this.unitPriceCents = unitPriceCents;
    }
}
```

FILE: src/main/java/com/example/orderservice/controller/OrdersController.java
```java
package com.example.orderservice.controller;

import com.example.orderservice.model.Order;
import com.example.orderservice.model.OrderItem;
import com.example.orderservice.service.OrderStore;
import jakarta.validation.constraints.*;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.validation.annotation.Validated;
import org.springframework.validation.annotation.Valid;

import java.util.List;
import java.util.Map;
import java.util.HashMap;
import java.util.UUID;

@RestController
@RequestMapping("/orders")
public class OrdersController {

    private final OrderStore orderStore;

    public OrdersController(OrderStore orderStore) {
        this.orderStore = orderStore;
    }

    @PostMapping
    public ResponseEntity<?> createOrder(@RequestBody @Valid CreateOrderRequest request) {
        List<OrderItem> items = request.getItems();
        Order order = new Order(request.getCustomerId(), items);
        orderStore.save(order);
        
        Map<String, Object> response = new HashMap<>();
        response.put("id", order.getId());
        response.put("customerId", order.getCustomerId());
        response.put("items", order.getItems());
        response.put("totalCents", order.getTotalCents());
        response.put("createdAt", order.getCreatedAtIso());

        return ResponseEntity
                .status(HttpStatus.CREATED)
                .header("Location", "/orders/" + order.getId())
                .body(response);
    }

    @GetMapping("/{id}")
    public ResponseEntity<?> getOrder(@PathVariable String id) {
        Order order = orderStore.findById(id);
        if (order == null) {
            Map<String, String> error = new HashMap<>();
            error.put("error", "Order not found");
            return ResponseEntity.status(HttpStatus.NOT_FOUND).body(error);
        }

        Map<String, Object> response = new HashMap<>();
        response.put("id", order.getId());
        response.put("customerId", order.getCustomerId());
        response.put("items", order.getItems());
        response.put("totalCents", order.getTotalCents());
        response.put("createdAt", order.getCreatedAtIso());

        return ResponseEntity.ok(response);
    }
}

class CreateOrderRequest {
    private String customerId;
    private List<OrderItem> items;

    // Getters and Setters for Jackson
    public String getCustomerId() { return customerId; }
    public void setCustomerId(String customerId) { this.customerId = customerId; }
    public List<OrderItem> getItems() { return items; }
    public void setItems(List<OrderItem> items) { this.items = items; }
}
```

FILE: src/main/java/com/example/orderservice/service/OrderStore.java
```java
package com.example.orderservice.service;

import com.example.orderservice.model.Order;
import org.springframework.stereotype.Service;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.Optional;

@Service
public class OrderStore {

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
import org.springframework.web.bind.MissingServletRequestParameterException;

import java.util.HashMap;
import java.util.Map;
import java.util.stream.Collectors;

@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, String>> handleValidationExceptions(MethodArgumentNotValidException ex) {
        String errors = ex.getBindingResult().getFieldErrors().stream()
                .map(error -> error.getField() + ": " + error.getDefaultMessage())
                .collect(Collectors.joining(", "));
        
        Map<String, String> error = new HashMap<>();
        error.put("error", "Validation failed: " + errors);
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(error);
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<Map<String, String>> handleGenericExceptions(Exception ex) {
        Map<String, String> error = new HashMap<>();
        error.put("error", "Internal server error: " + ex.getMessage());
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(error);
    }
}
```

FILE: src/main/java/com/example/orderservice/config/LoggingFilter.java
```java
package com.example.orderservice.config;

import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

@Component
public class LoggingFilter implements Filter {

    private static final Logger logger = LoggerFactory.getLogger(LoggingFilter.class);

    @Override
    public void doFilter(jakarta.servlet.FilterChain filterChain, 
                         jakarta.servlet.ServletRequest servletRequest, 
                         jakarta.servlet.ServletResponse servletResponse) 
                         throws IOException, ServletException {
        
        HttpServletRequest request = (HttpServletRequest) servletRequest;
        HttpServletResponse response = (HttpServletResponse) servletResponse;
        
        String method = request.getMethod();
        String path = request.getRequestURI();
        long startTime = System.currentTimeMillis();
        
        // Wrap response to capture status code
        HttpServletResponseWrapper responseWrapper = new HttpServletResponseWrapper(response);
        
        try {
            filterChain.doFilter(request, responseWrapper);
        } finally {
            long durationMs = System.currentTimeMillis() - startTime;
            int status = responseWrapper.getStatus();
            
            Map<String, Object> logEntry = new LinkedHashMap<>();
            logEntry.put("method", method);
            logEntry.put("path", path);
            logEntry.put("status", status);
            logEntry.put("durationMs", durationMs);
            
            logger.info("{}", toJson(logEntry));
        }
    }

    private String toJson(Map<String, Object> map) {
        StringBuilder sb = new StringBuilder();
        sb.append("{");
        boolean first = true;
        for (Map.Entry<String, Object> entry : map.entrySet()) {
            if (!first) sb.append(",");
            sb.append("\"").append(entry.getKey()).append("\":");
            if (entry.getValue() instanceof String) {
                sb.append("\"").append(escapeJson((String) entry.getValue())).append("\"");
            } else {
                sb.append(entry.getValue());
            }
            first = false;
        }
        sb.append("}");
        return sb.toString();
    }

    private String escapeJson(String s) {
        return s.replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace("\t", "\\t");
    }
}
```

FILE: src/main/java/com/example/orderservice/config/HttpServletResponseWrapper.java
```java
package com.example.orderservice.config;

import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpServletResponseWrapper;

public class HttpServletResponseWrapper extends HttpServletResponseWrapper {

    private int status = 200;

    public HttpServletResponseWrapper(HttpServletResponse response) {
        super(response);
    }

    @Override
    public void setStatus(int sc) {
        super.setStatus(sc);
        this.status = sc;
    }

    @Override
    public void setStatus(int sc, String sm) {
        super.setStatus(sc, sm);
        this.status = sc;
    }

    @Override
    public int getStatus() {
        return this.status;
    }
}
```

FILE: src/main/java/com/example/orderservice/config/ShutdownConfig.java
```java
package com.example.orderservice.config;

import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.stereotype.Component;

import java.util.Arrays;
import java.util.concurrent.TimeUnit;

@Component
public class ShutdownConfig {

    private static final Logger logger = LoggerFactory.getLogger(ShutdownConfig.class);

    @PreDestroy
    public void shutdown() {
        logger.info("Application is shutting down...");
        // Spring Boot handles the actual shutdown lifecycle, but we can log here.
    }
}
```

FILE: src/main/resources/application.properties
```properties
spring.application.name=orders-service
server.port=${PORT:8080}
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=10s
```

FILE: src/test/java/com/example/orderservice/OrderValidationTest.java
```java
package com.example.orderservice;

import com.example.orderservice.config.GlobalExceptionHandler;
import com.example.orderservice.model.OrderItem;
import com.example.orderservice.service.OrderStore;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.util.List;
import java.util.Map;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

@SpringBootTest
@AutoConfigureMockMvc
class OrderValidationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private OrderStore orderStore;

    @Test
    void shouldReturn400WhenCustomerIdIsEmpty() throws Exception {
        String json = """
            {
              "customerId": "",
              "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]
            }
            """;
        
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldReturn400WhenCustomerIdTooLong() throws Exception {
        String longId = "a".repeat(65);
        String json = """
            {
              "customerId": "%s",
              "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]
            }
            """.formatted(longId);
        
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldReturn400WhenItemsIsEmpty() throws Exception {
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
    void shouldReturn400WhenSkuIsEmpty() throws Exception {
        String json = """
            {
              "customerId": "c-1",
              "items": [{"sku": "", "quantity": 1, "unitPriceCents": 100}]
            }
            """;
        
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldReturn400WhenQuantityIsZero() throws Exception {
        String json = """
            {
              "customerId": "c-1",
              "items": [{"sku": "A-1", "quantity": 0, "unitPriceCents": 100}]
            }
            """;
        
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldReturn400WhenQuantityIs101() throws Exception {
        String json = """
            {
              "customerId": "c-1",
              "items": [{"sku": "A-1", "quantity": 101, "unitPriceCents": 100}]
            }
            """;
        
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldReturn400WhenUnitPriceCentsIsZero() throws Exception {
        String json = """
            {
              "customerId": "c-1",
              "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 0}]
            }
            """;
        
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldReturn400WhenUnitPriceCentsIsTooLarge() throws Exception {
        String json = """
            {
              "customerId": "c-1",
              "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 1000001}]
            }
            """;
        
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldReturn400WhenInvalidJSON() throws Exception {
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{ invalid json }"))
                .andExpect(status().isBadRequest());
    }
}
```

FILE: src/test/java/com/example/orderservice/OrderNotFoundTest.java
```java
package com.example.orderservice;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

@SpringBootTest
@AutoConfigureMockMvc
class OrderNotFoundTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void shouldReturn404WhenOrderNotFound() throws Exception {
        mockMvc.perform(get("/orders/non-existent-id"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error").exists());
    }
}
```