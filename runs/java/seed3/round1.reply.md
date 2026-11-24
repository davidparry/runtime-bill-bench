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
        <version>3.4.1</version>
        <relativePath/>
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

FILE: src/main/java/com/example/orderservice/model/OrderRequest.java
```java
package com.example.orderservice.model;

import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.util.List;

public class OrderRequest {

    @NotBlank
    @Size(min = 1, max = 64)
    private String customerId;

    @NotEmpty
    @Size(min = 1, max = 50)
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

FILE: src/main/java/com/example/orderservice/model/OrderItem.java
```java
package com.example.orderservice.model;

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

FILE: src/main/java/com/example/orderservice/model/OrderResponse.java
```java
package com.example.orderservice.model;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;
import java.util.Objects;

public class OrderResponse {

    private String id;
    private String customerId;
    private List<OrderItem> items;
    private Long totalCents;
    private String createdAt;

    public OrderResponse(String id, String customerId, List<OrderItem> items, Long totalCents, String createdAt) {
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

    public Long getTotalCents() {
        return totalCents;
    }

    public String getCreatedAt() {
        return createdAt;
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (o == null || getClass() != o.getClass()) return false;
        OrderResponse that = (OrderResponse) o;
        return Objects.equals(id, that.id) &&
                Objects.equals(customerId, that.customerId) &&
                Objects.equals(items, that.items) &&
                Objects.equals(totalCents, that.totalCents) &&
                Objects.equals(createdAt, that.createdAt);
    }

    @Override
    public int hashCode() {
        return Objects.hash(id, customerId, items, totalCents, createdAt);
    }
}
```

FILE: src/main/java/com/example/orderservice/controller/OrderController.java
```java
package com.example.orderservice.controller;

import com.example.orderservice.model.OrderRequest;
import com.example.orderservice.model.OrderResponse;
import com.example.orderservice.service.OrderService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

import java.util.Map;

@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    public ResponseEntity<OrderResponse> createOrder(@Valid @RequestBody OrderRequest request) {
        OrderResponse order = orderService.createOrder(request);
        
        ResponseEntity.BodyBuilder responseBuilder = ResponseEntity
                .status(HttpStatus.CREATED)
                .header("Location", ServletUriComponentsBuilder
                        .fromCurrentContextPath()
                        .path("/orders/{id}")
                        .buildAndExpand(order.getId())
                        .toUriString());
        
        return responseBuilder.body(order);
    }

    @GetMapping("/{id}")
    public ResponseEntity<OrderResponse> getOrder(@PathVariable String id) {
        OrderResponse order = orderService.getOrder(id);
        if (order == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(order);
    }
}
```

FILE: src/main/java/com/example/orderservice/service/OrderService.java
```java
package com.example.orderservice.service;

import com.example.orderservice.model.OrderItem;
import com.example.orderservice.model.OrderRequest;
import com.example.orderservice.model.OrderResponse;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

@Service
public class OrderService {

    private final Map<String, OrderResponse> orders = new ConcurrentHashMap<>();
    private static final DateTimeFormatter FORMATTER = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'")
            .withZone(ZoneOffset.UTC);

    public OrderResponse createOrder(OrderRequest request) {
        String id = UUID.randomUUID().toString();
        String createdAt = Instant.now().format(FORMATTER);
        
        long totalCents = 0;
        for (OrderItem item : request.getItems()) {
            totalCents += item.getQuantity() * item.getUnitPriceCents();
        }

        OrderResponse order = new OrderResponse(
                id,
                request.getCustomerId(),
                request.getItems(),
                totalCents,
                createdAt
        );

        orders.put(id, order);
        return order;
    }

    public OrderResponse getOrder(String id) {
        return orders.get(id);
    }
}
```

FILE: src/main/java/com/example/orderservice/config/GlobalExceptionHandler.java
```java
package com.example.orderservice.config;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
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
        errors.put("error", "Validation failed: " + ex.getBindingResult().getFieldError().getDefaultMessage());
        return ResponseEntity.badRequest().body(errors);
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<Map<String, String>> handleBadRequest(HttpMessageNotReadableException ex) {
        Map<String, String> errors = new HashMap<>();
        errors.put("error", "Invalid JSON: " + ex.getLocalizedMessage());
        return ResponseEntity.badRequest().body(errors);
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<Map<String, String>> handleGeneralException(Exception ex) {
        Map<String, String> errors = new HashMap<>();
        errors.put("error", "Internal server error: " + ex.getLocalizedMessage());
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(errors);
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

@Component
public class LoggingFilter implements Filter {

    private static final Logger logger = LoggerFactory.getLogger(LoggingFilter.class);

    @Override
    public void doFilter(jakarta.servlet.FilterChain filterChain) throws IOException, ServletException {
        HttpServletRequest request = (HttpServletRequest) filterChain.getRequest();
        HttpServletResponse response = (HttpServletResponse) filterChain.getResponse();
        
        long startTime = System.currentTimeMillis();
        String method = request.getMethod();
        String path = request.getRequestURI();
        
        filterChain.doFilter(request, response);
        
        long duration = System.currentTimeMillis() - startTime;
        
        Map<String, Object> logEntry = new LinkedHashMap<>();
        logEntry.put("method", method);
        logEntry.put("path", path);
        logEntry.put("status", response.getStatus());
        logEntry.put("durationMs", duration);
        
        // Simple JSON formatting without external library to avoid dependency complexity
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
```

FILE: src/main/resources/application.properties
```properties
server.port=${PORT:8080}
```

FILE: src/test/java/com/example/orderservice/OrderControllerTest.java
```java
package com.example.orderservice;

import com.example.orderservice.model.OrderRequest;
import com.example.orderservice.model.OrderResponse;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.JsonNode;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
class OrderControllerTest {

    @Autowired
    private WebApplicationContext context;

    private MockMvc mockMvc;

    @org.junit.jupiter.api.BeforeEach
    void setUp() {
        this.mockMvc = MockMvcBuilders.webAppContextSetup(context).build();
    }

    @Test
    void createOrderSuccess() throws Exception {
        OrderRequest request = new OrderRequest();
        request.setCustomerId("c-1");
        request.setItems(List.of(
                Map.of("sku", "A-1", "quantity", 2, "unitPriceCents", 1250)
        ));
        
        // Reconstruct request object properly for serialization
        // Since Map.of doesn't map perfectly to POJOs without custom deserializer, 
        // we use raw JSON string or a proper POJO builder. 
        // For simplicity in test, let's use JSON string directly in body.
        
        String json = """
                {
                  "customerId": "c-1",
                  "items": [
                    {"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}
                  ]
                }
                """;

        mockMvc.perform(post("/orders")
                .contentType("application/json")
                .content(json))
                .andExpect(status().isCreated())
                .andExpect(header().exists("Location"))
                .andExpect(jsonPath("$.customerId").value("c-1"))
                .andExpect(jsonPath("$.items[0].sku").value("A-1"))
                .andExpect(jsonPath("$.totalCents").value(2500));
    }

    @Test
    void createOrderInvalidCustomerId() throws Exception {
        String json = """
                {
                  "customerId": "",
                  "items": [
                    {"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}
                  ]
                }
                """;

        mockMvc.perform(post("/orders")
                .contentType("application/json")
                .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void createOrderInvalidQuantity() throws Exception {
        String json = """
                {
                  "customerId": "c-1",
                  "items": [
                    {"sku": "A-1", "quantity": 0, "unitPriceCents": 1250}
                  ]
                }
                """;

        mockMvc.perform(post("/orders")
                .contentType("application/json")
                .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void createOrderInvalidUnitPrice() throws Exception {
        String json = """
                {
                  "customerId": "c-1",
                  "items": [
                    {"sku": "A-1", "quantity": 2, "unitPriceCents": 0}
                  ]
                }
                """;

        mockMvc.perform(post("/orders")
                .contentType("application/json")
                .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void createOrderInvalidJson() throws Exception {
        mockMvc.perform(post("/orders")
                .contentType("application/json")
                .content("{ invalid json }"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void getOrderSuccess() throws Exception {
        // Create an order first
        String json = """
                {
                  "customerId": "c-1",
                  "items": [
                    {"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}
                  ]
                }
                """;

        MvcResult result = mockMvc.perform(post("/orders")
                .contentType("application/json")
                .content(json))
                .andExpect(status().isCreated())
                .andReturn();

        String location = result.getResponse().getHeader("Location");
        String orderId = location.substring(location.lastIndexOf('/') + 1);

        mockMvc.perform(get("/orders/" + orderId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(orderId));
    }

    @Test
    void getOrderNotFound() throws Exception {
        mockMvc.perform(get("/orders/non-existent-id"))
                .andExpect(status().isNotFound());
    }

    @Test
    void healthCheck() throws Exception {
        mockMvc.perform(get("/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("ok"));
    }
}
```