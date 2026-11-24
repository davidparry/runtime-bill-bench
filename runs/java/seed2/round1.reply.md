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
        <relativePath/>
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

import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;

public class Order {
    private String id;
    private String customerId;
    private List<OrderItem> items;
    private Long totalCents;
    private String createdAt;

    public Order() {
    }

    public Order(String id, String customerId, List<OrderItem> items, Long totalCents, String createdAt) {
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

FILE: src/main/java/com/example/orderservice/model/OrderItem.java
```java
package com.example.orderservice.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public class OrderItem {
    private String sku;
    private Integer quantity;
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

FILE: src/main/java/com/example/orderservice/controller/OrderController.java
```java
package com.example.orderservice.controller;

import com.example.orderservice.model.Order;
import com.example.orderservice.model.OrderItem;
import com.example.orderservice.service.OrderService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.ArrayList;
import java.util.List;

@RestController
@RequestMapping("/orders")
@Validated
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    public ResponseEntity<Order> createOrder(@Valid @RequestBody CreateOrderRequest request) {
        Order createdOrder = orderService.createOrder(request.getCustomerId(), request.getItems());
        
        HttpHeaders headers = new HttpHeaders();
        headers.set(HttpHeaders.LOCATION, "/orders/" + createdOrder.getId());
        
        return new ResponseEntity<>(createdOrder, headers, HttpStatus.CREATED);
    }

    @GetMapping("/{id}")
    public ResponseEntity<Order> getOrder(@PathVariable String id) {
        Order order = orderService.getOrder(id);
        if (order == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(order);
    }
}
```

FILE: src/main/java/com/example/orderservice/controller/CreateOrderRequest.java
```java
package com.example.orderservice.controller;

import com.example.orderservice.model.OrderItem;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.util.List;

public class CreateOrderRequest {

    @NotNull
    @Size(min = 1, max = 64)
    private String customerId;

    @NotNull
    @NotEmpty
    @Size(min = 1, max = 50)
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
        ex.getBindingResult().getFieldErrors().forEach(error -> 
            errors.put(error.getField(), error.getDefaultMessage())
        );
        return ResponseEntity.badRequest().body(errors);
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<Map<String, String>> handleGeneralExceptions(Exception ex) {
        Map<String, String> errors = new HashMap<>();
        errors.put("error", ex.getMessage());
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(errors);
    }
}
```

FILE: src/main/java/com/example/orderservice/service/OrderService.java
```java
package com.example.orderservice.service;

import com.example.orderservice.model.Order;
import com.example.orderservice.model.OrderItem;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
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

FILE: src/main/java/com/example/orderservice/logging/LoggingFilter.java
```java
package com.example.orderservice.logging;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.HashMap;
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
            long duration = System.currentTimeMillis() - startTime;
            Map<String, Object> logEntry = new HashMap<>();
            logEntry.put("method", request.getMethod());
            logEntry.put("path", request.getRequestURI());
            logEntry.put("status", response.getStatus());
            logEntry.put("durationMs", duration);
            
            // Simple JSON formatting for log line
            StringBuilder sb = new StringBuilder("{");
            sb.append("\"method\":\"").append(logEntry.get("method")).append("\",");
            sb.append("\"path\":\"").append(logEntry.get("path")).append("\",");
            sb.append("\"status\":").append(logEntry.get("status")).append(",");
            sb.append("\"durationMs\":").append(logEntry.get("durationMs"));
            sb.append("}");
            
            logger.info(sb.toString());
        }
    }
}
```

FILE: src/main/resources/application.properties
```properties
server.port=${PORT:8080}
logging.level.root=INFO
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
                .andExpect(jsonPath("$.customerId").exists());
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
                .andExpect(status().isBadRequest());
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
                .andExpect(status().isBadRequest());
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
                .andExpect(status().isBadRequest());
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
                .andExpect(status().isBadRequest());
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
                .andExpect(status().isBadRequest());
    }

    @Test
    void getOrder_notFound() throws Exception {
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