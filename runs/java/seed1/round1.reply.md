FILE: pom.xml
```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
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
    <version>1.0.0</version>
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

FILE: src/main/java/com/example/orders/OrdersServiceApplication.java
```java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersServiceApplication.class, args);
    }

}
```

FILE: src/main/java/com/example/orders/config/LoggingFilter.java
```java
package com.example.orders.config;

import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.util.HashMap;
import java.util.Map;

@Component
public class LoggingFilter implements Filter {

    private static final Logger log = LoggerFactory.getLogger(LoggingFilter.class);

    @Override
    public void doFilter(ServletRequest request, ServletResponse response, FilterChain chain)
            throws IOException, ServletException {
        
        HttpServletRequest httpRequest = (HttpServletRequest) request;
        HttpServletResponse httpResponse = (HttpServletResponse) response;
        
        long start = System.currentTimeMillis();
        
        try {
            chain.doFilter(request, response);
        } finally {
            long duration = System.currentTimeMillis() - start;
            
            Map<String, Object> logEntry = new HashMap<>();
            logEntry.put("method", httpRequest.getMethod());
            logEntry.put("path", httpRequest.getRequestURI());
            logEntry.put("status", httpResponse.getStatus());
            logEntry.put("durationMs", duration);
            
            // Simple JSON serialization for the log line
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
            
            log.info(sb.toString());
        }
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
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

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
}
```

FILE: src/main/java/com/example/orders/controller/HealthController.java
```java
package com.example.orders.controller;

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

FILE: src/main/java/com/example/orders/dto/CreateOrderRequest.java
```java
package com.example.orders.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.util.List;

public class CreateOrderRequest {

    @NotBlank
    @Size(min = 1, max = 64)
    private String customerId;

    @NotEmpty
    @Size(max = 50)
    @Valid
    private List<OrderItem> items;

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
}
```

FILE: src/main/java/com/example/orders/dto/OrderItem.java
```java
package com.example.orders.dto;

import jakarta.validation.constraints.*;

public class OrderItem {

    @NotBlank
    @Size(min = 1, max = 32)
    private String sku;

    @Min(1)
    @Max(100)
    private Integer quantity;

    @Min(1)
    @Max(1000000)
    private Long unitPriceCents;

    public String getSku() {
        return sku;
    }

    public void setSku(String sku) {
        this.sku = sku;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }

    public Long getUnitPriceCents() {
        return unitPriceCents;
    }

    public void setUnitPriceCents(Long unitPriceCents) {
        this.unitPriceCents = unitPriceCents;
    }
}
```

FILE: src/main/java/com/example/orders/dto/OrderResponse.java
```java
package com.example.orders.dto;

import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;

public class OrderResponse {

    private String id;
    private String customerId;
    private List<OrderItem> items;
    private long totalCents;
    private String createdAt;

    public OrderResponse(String id, String customerId, List<OrderItem> items, long totalCents, String createdAt) {
        this.id = id;
        this.customerId = customerId;
        this.items = items;
        this.totalCents = totalCents;
        this.createdAt = createdAt;
    }

    public String getId() {
        return id;
    }

    public String getCustomerId() {
        return customerId;
    }

    public List<OrderItem> getItems() {
        return items;
    }

    public long getTotalCents() {
        return totalCents;
    }

    public String getCreatedAt() {
        return createdAt;
    }
}
```

FILE: src/main/java/com/example/orders/service/OrderService.java
```java
package com.example.orders.service;

import com.example.orders.dto.CreateOrderRequest;
import com.example.orders.dto.OrderItem;
import com.example.orders.dto.OrderResponse;
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

    private final Map<String, OrderResponse> store = new ConcurrentHashMap<>();

    public OrderResponse createOrder(CreateOrderRequest request) {
        String id = UUID.randomUUID().toString();
        List<OrderItem> items = request.getItems();
        
        long totalCents = 0;
        List<OrderItem> responseItems = new ArrayList<>();
        
        for (OrderItem item : items) {
            long itemTotal = item.getQuantity() * item.getUnitPriceCents();
            totalCents += itemTotal;
            // Create a copy to ensure immutability in store if needed, 
            // though simple POJOs in this context are usually safe if not mutated later.
            // We'll just store the reference as per simple requirements, but good practice 
            // would be deep copy if items are mutable. Here they are simple DTOs.
            responseItems.add(item);
        }

        String createdAt = DateTimeFormatter.ISO_INSTANT.format(Instant.now());

        OrderResponse response = new OrderResponse(id, request.getCustomerId(), responseItems, totalCents, createdAt);
        store.put(id, response);
        return response;
    }

    public OrderResponse getOrder(String id) {
        return store.get(id);
    }
}
```

FILE: src/main/java/com/example/orders/exception/GlobalExceptionHandler.java
```java
package com.example.orders.exception;

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
        // Combine errors into a single message string for simplicity as per spec {"error": "<message>"}
        // Or return the map if allowed. Spec says {"error": "<message>"}. 
        // Let's return a combined message.
        StringBuilder sb = new StringBuilder();
        boolean first = true;
        for (Map.Entry<String, String> entry : errors.entrySet()) {
            if (!first) sb.append("; ");
            sb.append(entry.getKey()).append(": ").append(entry.getValue());
            first = false;
        }
        return ResponseEntity.badRequest().body(Map.of("error", sb.toString()));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<Map<String, String>> handleGenericException(Exception ex) {
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(Map.of("error", ex.getMessage()));
    }
}
```

FILE: src/main/java/com/example/orders/exception/NotFoundExceptionHandler.java
```java
package com.example.orders.exception;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.servlet.resource.NoResourceFoundException;

import java.util.Map;

@RestControllerAdvice
public class NotFoundExceptionHandler {

    @ExceptionHandler(NoResourceFoundException.class)
    public ResponseEntity<Map<String, String>> handleNotFound(NoResourceFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("error", "No order found"));
    }
}
```

FILE: src/main/resources/application.properties
```properties
server.port=${PORT:8080}
```

FILE: src/test/java/com/example/orders/OrdersControllerIntegrationTest.java
```java
package com.example.orders;

import com.example.orders.dto.CreateOrderRequest;
import com.example.orders.dto.OrderItem;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.ActiveProfiles;

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
        assertEquals(2500L, body.get("totalCents"));
        assertNotNull(body.get("createdAt"));
        
        List<?> items = (List<?>) body.get("items");
        assertEquals(1, items.size());
        Map<?, ?> itemMap = (Map<?, ?>) items.get(0);
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

FILE: src/test/java/com/example/orders/ValidationRulesTest.java
```java
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
```