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

FILE: src/main/java/com/example/orderservice/OrdersApplication.java
```java
package com.example.orderservice;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
```

FILE: src/main/java/com/example/orderservice/dto/CreateOrderRequest.java
```java
package com.example.orderservice.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.util.List;

@JsonInclude(JsonInclude.Include.NON_NULL)
public class CreateOrderRequest {

    @NotBlank(message = "customerId is required")
    @Size(min = 1, max = 64, message = "customerId must be between 1 and 64 characters")
    private String customerId;

    @NotEmpty(message = "items must not be empty")
    @Size(min = 1, max = 50, message = "items must have between 1 and 50 entries")
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

    public static class OrderItem {
        @NotBlank(message = "sku is required")
        @Size(min = 1, max = 32, message = "sku must be between 1 and 32 characters")
        private String sku;

        @NotNull(message = "quantity is required")
        @Min(value = 1, message = "quantity must be at least 1")
        @Max(value = 100, message = "quantity must be at most 100")
        private Integer quantity;

        @NotNull(message = "unitPriceCents is required")
        @Min(value = 1, message = "unitPriceCents must be at least 1")
        @Max(value = 1000000, message = "unitPriceCents must be at most 1000000")
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
}
```

FILE: src/main/java/com/example/orderservice/dto/OrderResponse.java
```java
package com.example.orderservice.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import java.util.List;

@JsonInclude(JsonInclude.Include.NON_NULL)
public class OrderResponse {

    private String id;
    private String customerId;
    private List<CreateOrderRequest.OrderItem> items;
    private Long totalCents;
    private String createdAt;

    public OrderResponse() {
    }

    public OrderResponse(String id, String customerId, List<CreateOrderRequest.OrderItem> items, Long totalCents, String createdAt) {
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

    public List<CreateOrderRequest.OrderItem> getItems() {
        return items;
    }

    public void setItems(List<CreateOrderRequest.OrderItem> items) {
        this.items = items;
    }

    public Long getTotalCents() {
        return totalCents;
    }

    public void setTotalCents(Long totalCents) {
        this.totalCents = totalCents;
    }

    public String getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(String createdAt) {
        this.createdAt = createdAt;
    }
}
```

FILE: src/main/java/com/example/orderservice/dto/ErrorResponse.java
```java
package com.example.orderservice.dto;

public class ErrorResponse {
    private String error;

    public ErrorResponse(String error) {
        this.error = error;
    }

    public String getError() {
        return error;
    }

    public void setError(String error) {
        this.error = error;
    }
}
```

FILE: src/main/java/com/example/orderservice/service/OrderStore.java
```java
package com.example.orderservice.service;

import com.example.orderservice.dto.CreateOrderRequest;
import com.example.orderservice.dto.OrderResponse;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

@Component
public class OrderStore {

    private final Map<String, OrderRecord> orders = new ConcurrentHashMap<>();

    public OrderResponse createOrder(CreateOrderRequest request) {
        String id = UUID.randomUUID().toString();
        String customerId = request.getCustomerId();
        List<CreateOrderRequest.OrderItem> items = request.getItems();
        
        long totalCents = items.stream()
                .mapToLong(item -> item.getQuantity() * item.getUnitPriceCents())
                .sum();

        String createdAt = Instant.now().atZone(ZoneOffset.UTC).format(DateTimeFormatter.ISO_INSTANT);

        OrderRecord record = new OrderRecord(id, customerId, items, totalCents, createdAt);
        orders.put(id, record);

        return new OrderResponse(id, customerId, items, totalCents, createdAt);
    }

    public Optional<OrderResponse> getOrder(String id) {
        return Optional.ofNullable(orders.get(id)).map(this::toResponse);
    }

    private OrderResponse toResponse(OrderRecord record) {
        return new OrderResponse(
                record.id,
                record.customerId,
                record.items,
                record.totalCents,
                record.createdAt
        );
    }

    private static class OrderRecord {
        final String id;
        final String customerId;
        final List<CreateOrderRequest.OrderItem> items;
        final Long totalCents;
        final String createdAt;

        OrderRecord(String id, String customerId, List<CreateOrderRequest.OrderItem> items, Long totalCents, String createdAt) {
            this.id = id;
            this.customerId = customerId;
            this.items = items;
            this.totalCents = totalCents;
            this.createdAt = createdAt;
        }
    }
}
```

FILE: src/main/java/com/example/orderservice/controller/OrdersController.java
```java
package com.example.orderservice.controller;

import com.example.orderservice.dto.CreateOrderRequest;
import com.example.orderservice.dto.ErrorResponse;
import com.example.orderservice.dto.OrderResponse;
import com.example.orderservice.service.OrderStore;
import jakarta.validation.Valid;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.net.URI;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

@RestController
@RequestMapping("/orders")
public class OrdersController {

    private static final Logger log = LoggerFactory.getLogger(OrdersController.class);
    private final OrderStore orderStore;

    public OrdersController(OrderStore orderStore) {
        this.orderStore = orderStore;
    }

    @PostMapping
    public ResponseEntity<?> createOrder(@Valid @RequestBody CreateOrderRequest request) {
        OrderResponse response = orderStore.createOrder(request);
        return ResponseEntity.created(URI.create("/orders/" + response.getId()))
                .body(response);
    }

    @GetMapping("/{id}")
    public ResponseEntity<?> getOrder(@PathVariable String id) {
        Optional<OrderResponse> order = orderStore.getOrder(id);
        if (order.isPresent()) {
            return ResponseEntity.ok(order.get());
        } else {
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                    .body(new ErrorResponse("Order not found"));
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

FILE: src/main/java/com/example/orderservice/config/GlobalExceptionHandler.java
```java
package com.example.orderservice.config;

import com.example.orderservice.dto.ErrorResponse;
import jakarta.servlet.http.HttpServletRequest;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.HashMap;
import java.util.Map;

@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ErrorResponse> handleValidationExceptions(MethodArgumentNotValidException ex, HttpServletRequest request) {
        List<String> errors = new ArrayList<>();
        for (FieldError fieldError : ex.getBindingResult().getFieldErrors()) {
            errors.add(fieldError.getField() + ": " + fieldError.getDefaultMessage());
        }
        String message = "Validation failed: " + String.join(", ", errors);
        log.warn("Validation error on {}: {}", request.getMethod(), request.getRequestURI(), ex);
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(new ErrorResponse(message));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ErrorResponse> handleHttpMessageNotReadable(HttpMessageNotReadableException ex, HttpServletRequest request) {
        String message = "Invalid JSON: " + ex.getMessage();
        log.warn("Invalid JSON on {}: {}", request.getMethod(), request.getRequestURI(), ex);
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(new ErrorResponse(message));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ErrorResponse> handleGeneral(Exception ex, HttpServletRequest request) {
        log.error("Unexpected error on {}: {}", request.getMethod(), request.getRequestURI(), ex);
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(new ErrorResponse("Internal server error"));
    }
    
    private static class List<T> extends java.util.ArrayList<T> {}
}
```

FILE: src/main/java/com/example/orderservice/config/RequestLoggingFilter.java
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
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

@Component
public class RequestLoggingFilter extends OncePerRequestFilter {

    private static final Logger log = LoggerFactory.getLogger(RequestLoggingFilter.class);

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {
        
        long startTime = Instant.now().toEpochMilli();
        
        try {
            filterChain.doFilter(request, response);
        } finally {
            long endTime = Instant.now().toEpochMilli();
            long durationMs = endTime - startTime;
            
            Map<String, Object> logEntry = new LinkedHashMap<>();
            logEntry.put("method", request.getMethod());
            logEntry.put("path", request.getRequestURI());
            logEntry.put("status", response.getStatus());
            logEntry.put("durationMs", durationMs);
            
            log.info("{}", logEntry);
        }
    }
}
```

FILE: src/main/java/com/example/orderservice/config/WebConfig.java
```java
package com.example.orderservice.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

import java.util.List;

@Configuration
public class WebConfig implements WebMvcConfigurer {

    @Override
    public void configureMessageConverters(List<HttpMessageConverter<?>> converters) {
        // Ensure we only use Jackson for JSON
        converters.clear();
        converters.add(new MappingJackson2HttpMessageConverter());
    }
}
```

FILE: src/main/resources/application.properties
```properties
server.port=${PORT:8080}
logging.level.root=INFO
logging.pattern.console=%clr(%d{yyyy-MM-dd HH:mm:ss.SSS}){faint} %clr(%5p) %clr(${PID}){magenta} %clr(---){faint} %clr([%15.15t]){faint} %clr(%-40.40logger{39}){cyan} %clr(:){faint} %m%n%wEx
```

FILE: src/test/java/com/example/orderservice/OrdersServiceApplicationTests.java
```java
package com.example.orderservice;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class OrdersServiceApplicationTests {

    @Test
    void contextLoads() {
    }

}
```

FILE: src/test/java/com/example/orderservice/controller/OrdersControllerTest.java
```java
package com.example.orderservice.controller;

import com.example.orderservice.dto.CreateOrderRequest;
import com.example.orderservice.dto.OrderResponse;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class OrdersControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Test
    void createOrderSuccess() throws Exception {
        CreateOrderRequest request = new CreateOrderRequest();
        request.setCustomerId("c-1");
        
        CreateOrderRequest.OrderItem item = new CreateOrderRequest.OrderItem();
        item.setSku("A-1");
        item.setQuantity(2);
        item.setUnitPriceCents(1250L);
        
        request.setItems(List.of(item));

        String json = objectMapper.writeValueAsString(request);

        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isCreated())
                .andExpect(header().exists("Location"))
                .andExpect(jsonPath("$.id").isNotEmpty())
                .andExpect(jsonPath("$.customerId").value("c-1"))
                .andExpect(jsonPath("$.items[0].sku").value("A-1"))
                .andExpect(jsonPath("$.items[0].quantity").value(2))
                .andExpect(jsonPath("$.items[0].unitPriceCents").value(1250))
                .andExpect(jsonPath("$.totalCents").value(2500))
                .andExpect(jsonPath("$.createdAt").isNotEmpty());
    }

    @Test
    void createOrderMissingCustomerId() throws Exception {
        CreateOrderRequest request = new CreateOrderRequest();
        request.setItems(List.of(new CreateOrderRequest.OrderItem()));

        String json = objectMapper.writeValueAsString(request);

        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").exists());
    }

    @Test
    void createOrderEmptyItems() throws Exception {
        CreateOrderRequest request = new CreateOrderRequest();
        request.setCustomerId("c-1");
        request.setItems(List.of());

        String json = objectMapper.writeValueAsString(request);

        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").exists());
    }

    @Test
    void createOrderInvalidQuantity() throws Exception {
        CreateOrderRequest request = new CreateOrderRequest();
        request.setCustomerId("c-1");
        
        CreateOrderRequest.OrderItem item = new CreateOrderRequest.OrderItem();
        item.setSku("A-1");
        item.setQuantity(0);
        item.setUnitPriceCents(1250L);
        
        request.setItems(List.of(item));

        String json = objectMapper.writeValueAsString(request);

        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").exists());
    }

    @Test
    void createOrderInvalidJson() throws Exception {
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{invalid json"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").exists());
    }

    @Test
    void getOrderSuccess() throws Exception {
        CreateOrderRequest request = new CreateOrderRequest();
        request.setCustomerId("c-1");
        
        CreateOrderRequest.OrderItem item = new CreateOrderRequest.OrderItem();
        item.setSku("A-1");
        item.setQuantity(1);
        item.setUnitPriceCents(1000L);
        
        request.setItems(List.of(item));

        String json = objectMapper.writeValueAsString(request);

        String location = mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isCreated())
                .andReturn()
                .getResponse()
                .getHeader("Location");

        String orderId = location.substring(location.lastIndexOf("/") + 1);

        mockMvc.perform(get("/orders/" + orderId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(orderId))
                .andExpect(jsonPath("$.customerId").value("c-1"));
    }

    @Test
    void getOrderNotFound() throws Exception {
        mockMvc.perform(get("/orders/non-existent-id"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error").value("Order not found"));
    }
}
```