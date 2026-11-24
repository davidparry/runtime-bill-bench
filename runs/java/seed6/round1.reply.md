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
        <version>3.3.4</version>
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

FILE: src/main/java/com/example/orderservice/model/Order.java
```java
package com.example.orderservice.model;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

public class Order {

    private final String id;
    private final String customerId;
    private final List<OrderItem> items;
    private final long totalCents;
    private final Instant createdAt;

    public Order(String customerId, List<OrderItem> items) {
        this.id = UUID.randomUUID().toString();
        this.customerId = customerId;
        this.items = List.copyOf(items); // Immutable copy
        this.totalCents = calculateTotalCents(items);
        this.createdAt = Instant.now();
    }

    private long calculateTotalCents(List<OrderItem> items) {
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

    public List<OrderItem> getItems() {
        return items;
    }

    public long getTotalCents() {
        return totalCents;
    }

    public Instant getCreatedAt() {
        return createdAt;
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

    public static class OrderItem {
        private final String sku;
        private final int quantity;
        private final int unitPriceCents;

        public OrderItem(String sku, int quantity, int unitPriceCents) {
            this.sku = sku;
            this.quantity = quantity;
            this.unitPriceCents = unitPriceCents;
        }

        public String getSku() {
            return sku;
        }

        public int getQuantity() {
            return quantity;
        }

        public int getUnitPriceCents() {
            return unitPriceCents;
        }

        @Override
        public boolean equals(Object o) {
            if (this == o) return true;
            if (o == null || getClass() != o.getClass()) return false;
            OrderItem that = (OrderItem) o;
            return quantity == that.quantity
                    && unitPriceCents == that.unitPriceCents
                    && Objects.equals(sku, that.sku);
        }

        @Override
        public int hashCode() {
            return Objects.hash(sku, quantity, unitPriceCents);
        }
    }
}
```

FILE: src/main/java/com/example/orderservice/controller/OrdersController.java
```java
package com.example.orderservice.controller;

import com.example.orderservice.model.Order;
import com.example.orderservice.service.OrderService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/orders")
public class OrdersController {

    private final OrderService orderService;

    public OrdersController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    public ResponseEntity<?> createOrder(@RequestBody @Valid CreateOrderRequest request) {
        Order createdOrder = orderService.createOrder(request.getCustomerId(), request.getItems());
        
        HttpHeaders headers = new HttpHeaders();
        headers.set(HttpHeaders.LOCATION, "/orders/" + createdOrder.getId());
        
        return new ResponseEntity<>(createdOrder, headers, HttpStatus.CREATED);
    }

    @GetMapping("/{id}")
    public ResponseEntity<?> getOrder(@PathVariable String id) {
        // Validate UUID format first to avoid unnecessary service lookup if invalid
        try {
            UUID.fromString(id);
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest().body(new ErrorResponse("Invalid order ID format"));
        }

        Order order = orderService.getOrder(id);
        if (order == null) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                    .body(new ErrorResponse("Order not found: " + id));
        }
        return ResponseEntity.ok(order);
    }

    // DTO for request validation
    public static class CreateOrderRequest {
        @NotBlank(message = "customerId is required")
        @Size(min = 1, max = 64, message = "customerId must be between 1 and 64 characters")
        private String customerId;

        @NotNull(message = "items is required")
        @Size(min = 1, max = 50, message = "items must contain between 1 and 50 entries")
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

        public static class OrderItemRequest {
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
            private Integer unitPriceCents;

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

            public Integer getUnitPriceCents() {
                return unitPriceCents;
            }

            public void setUnitPriceCents(Integer unitPriceCents) {
                this.unitPriceCents = unitPriceCents;
            }
        }
    }

    public static class ErrorResponse {
        private final String error;

        public ErrorResponse(String error) {
            this.error = error;
        }

        public String getError() {
            return error;
        }
    }
}
```

FILE: src/main/java/com/example/orderservice/service/OrderService.java
```java
package com.example.orderservice.service;

import com.example.orderservice.model.Order;
import org.springframework.stereotype.Service;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

@Service
public class OrderService {

    private final Map<String, Order> orderStore = new ConcurrentHashMap<>();

    public Order createOrder(String customerId, java.util.List<com.example.orderservice.controller.OrdersController.CreateOrderRequest.OrderItemRequest> requestItems) {
        java.util.List<Order.OrderItem> items = requestItems.stream()
                .map(req -> new Order.OrderItem(req.getSku(), req.getQuantity(), req.getUnitPriceCents()))
                .toList();
        
        Order order = new Order(customerId, items);
        orderStore.put(order.getId(), order);
        return order;
    }

    public Order getOrder(String id) {
        return orderStore.get(id);
    }
}
```

FILE: src/main/java/com/example/orderservice/config/GlobalExceptionHandler.java
```java
package com.example.orderservice.config;

import com.example.orderservice.controller.OrdersController;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.stream.Collectors;

@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<OrdersController.ErrorResponse> handleValidationExceptions(MethodArgumentNotValidException ex) {
        String errors = ex.getBindingResult().getFieldErrors().stream()
                .map(error -> error.getField() + ": " + error.getDefaultMessage())
                .collect(Collectors.joining(", "));
        
        return ResponseEntity.badRequest()
                .body(new OrdersController.ErrorResponse("Validation failed: " + errors));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<OrdersController.ErrorResponse> handleGeneralExceptions(Exception ex) {
        // In a real app, we might log this
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(new OrdersController.ErrorResponse("Internal server error"));
    }
}
```

FILE: src/main/java/com/example/orderservice/config/LoggingFilter.java
```java
package com.example.orderservice.config;

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
import java.util.LinkedHashMap;
import java.util.Map;

@Component
public class LoggingFilter implements Filter {

    private static final Logger logger = LoggerFactory.getLogger(LoggingFilter.class);

    @Override
    public void doFilter(ServletRequest request, ServletResponse response, FilterChain chain)
            throws IOException, ServletException {
        
        HttpServletRequest httpRequest = (HttpServletRequest) request;
        HttpServletResponse httpResponse = (HttpServletResponse) response;

        long startTime = System.currentTimeMillis();
        
        try {
            chain.doFilter(request, response);
        } finally {
            long duration = System.currentTimeMillis() - startTime;
            
            Map<String, Object> logEntry = new LinkedHashMap<>();
            logEntry.put("method", httpRequest.getMethod());
            logEntry.put("path", httpRequest.getRequestURI());
            logEntry.put("status", httpResponse.getStatus());
            logEntry.put("durationMs", duration);
            
            // Using simple JSON construction to avoid dependency on Jackson in filter if possible,
            // but since Spring Boot includes Jackson, we could use ObjectMapper.
            // However, to keep it lightweight and robust without extra serialization overhead in critical path:
            StringBuilder sb = new StringBuilder();
            sb.append("{");
            sb.append("\"method\":\"").append(escapeJson(httpRequest.getMethod())).append("\",");
            sb.append("\"path\":\"").append(escapeJson(httpRequest.getRequestURI())).append("\",");
            sb.append("\"status\":").append(httpResponse.getStatus()).append(",");
            sb.append("\"durationMs\":").append(duration);
            sb.append("}");
            
            logger.info(sb.toString());
        }
    }

    private String escapeJson(String value) {
        if (value == null) return "";
        return value.replace("\\", "\\\\")
                    .replace("\"", "\\\"")
                    .replace("\n", "\\n")
                    .replace("\r", "\\r")
                    .replace("\t", "\\t");
    }
}
```

FILE: src/main/resources/application.properties
```properties
spring.application.name=orders-service
server.port=${PORT:8080}
```

FILE: src/test/java/com/example/orderservice/OrdersControllerTest.java
```java
package com.example.orderservice;

import com.example.orderservice.controller.OrdersController;
import com.example.orderservice.controller.OrdersController.CreateOrderRequest;
import com.example.orderservice.controller.OrdersController.CreateOrderRequest.OrderItemRequest;
import com.example.orderservice.service.OrderService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrdersControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private OrderService orderService;

    @Test
    void shouldCreateOrderSuccessfully() throws Exception {
        CreateOrderRequest request = new CreateOrderRequest();
        request.setCustomerId("c-1");
        
        OrderItemRequest item = new OrderItemRequest();
        item.setSku("A-1");
        item.setQuantity(2);
        item.setUnitPriceCents(1250);
        
        request.setItems(List.of(item));

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

        MvcResult result = mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isCreated())
                .andExpect(header().exists("Location"))
                .andExpect(jsonPath("$.customerId").value("c-1"))
                .andExpect(jsonPath("$.items[0].sku").value("A-1"))
                .andExpect(jsonPath("$.items[0].quantity").value(2))
                .andExpect(jsonPath("$.items[0].unitPriceCents").value(1250))
                .andExpect(jsonPath("$.totalCents").value(2500))
                .andExpect(jsonPath("$.createdAt").exists())
                .andReturn();

        String location = result.getResponse().getHeader("Location");
        assertThat(location).startsWith("/orders/");
    }

    @Test
    void shouldRejectOrderWithMissingCustomerId() throws Exception {
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
                .andExpect(jsonPath("$.error").exists());
    }

    @Test
    void shouldRejectOrderWithInvalidQuantity() throws Exception {
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
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").exists());
    }

    @Test
    void shouldRejectOrderWithInvalidUnitPriceCents() throws Exception {
        String json = """
            {
                "customerId": "c-1",
                "items": [
                    {
                        "sku": "A-1",
                        "quantity": 1,
                        "unitPriceCents": 0
                    }
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
    void shouldReturn404ForNonExistentOrder() throws Exception {
        String nonExistentId = UUID.randomUUID().toString();

        mockMvc.perform(get("/orders/" + nonExistentId))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error").exists());
    }

    @Test
    void shouldReturn404ForInvalidIdFormat() throws Exception {
        String invalidId = "not-a-uuid";

        mockMvc.perform(get("/orders/" + invalidId))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").exists());
    }
    
    @Test
    void shouldIgnoreUnknownFields() throws Exception {
        String json = """
            {
                "customerId": "c-1",
                "items": [
                    {
                        "sku": "A-1",
                        "quantity": 1,
                        "unitPriceCents": 100,
                        "unknownField": "ignored"
                    }
                ],
                "unknownRootField": "ignored"
            }
            """;

        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isCreated());
    }
}
```

FILE: src/test/java/com/example/orderservice/OrdersServiceTest.java
```java
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
```