FILE: pom.xml
```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.2.5</version>
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

FILE: src/main/java/com/example/ordersservice/OrdersServiceApplication.java
```java
package com.example.ordersservice;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersServiceApplication.class, args);
    }
}
```

FILE: src/main/java/com/example/ordersservice/model/Order.java
```java
package com.example.ordersservice.model;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

public class Order {
    private String id;
    private String customerId;
    private List<OrderItem> items;
    private long totalCents;
    private Instant createdAt;

    public Order() {
        this.id = UUID.randomUUID().toString();
        this.createdAt = Instant.now();
        this.items = new ArrayList<>();
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

FILE: src/main/java/com/example/ordersservice/model/OrderItem.java
```java
package com.example.ordersservice.model;

import java.io.Serializable;

public class OrderItem implements Serializable {
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

    public int getUnitPriceCents() {
        return unitPriceCents;
    }

    public void setUnitPriceCents(int unitPriceCents) {
        this.unitPriceCents = unitPriceCents;
    }
}
```

FILE: src/main/java/com/example/ordersservice/controller/OrderController.java
```java
package com.example.ordersservice.controller;

import com.example.ordersservice.model.Order;
import com.example.ordersservice.model.OrderItem;
import com.example.ordersservice.service.OrderService;
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
import org.springframework.web.bind.annotation.RestController;

import java.util.ArrayList;
import java.util.List;

@RestController
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping("/orders")
    public ResponseEntity<Order> createOrder(@Valid @RequestBody CreateOrderRequest request) {
        Order createdOrder = orderService.createOrder(request.getCustomerId(), request.getItems());
        String location = "/orders/" + createdOrder.getId();
        return ResponseEntity.created(java.net.URI.create(location))
                .header(HttpHeaders.CONTENT_TYPE, "application/json")
                .body(createdOrder);
    }

    @GetMapping("/orders/{id}")
    public ResponseEntity<Order> getOrder(@PathVariable String id) {
        Order order = orderService.getOrder(id);
        if (order == null) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                    .body(new ErrorResponse("Order not found"));
        }
        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_TYPE, "application/json")
                .body(order);
    }

    @GetMapping("/health")
    public ResponseEntity<HealthResponse> health() {
        return ResponseEntity.ok(new HealthResponse("ok"));
    }

    public static class CreateOrderRequest {
        @NotBlank
        @Size(min = 1, max = 64)
        private String customerId;

        @NotNull
        @Size(min = 1, max = 50)
        private List<CreateOrderItemRequest> items;

        public String getCustomerId() {
            return customerId;
        }

        public void setCustomerId(String customerId) {
            this.customerId = customerId;
        }

        public List<CreateOrderItemRequest> getItems() {
            return items;
        }

        public void setItems(List<CreateOrderItemRequest> items) {
            this.items = items;
        }
    }

    public static class CreateOrderItemRequest {
        @NotBlank
        @Size(min = 1, max = 32)
        private String sku;

        @NotNull
        @Min(1)
        @Max(100)
        private Integer quantity;

        @NotNull
        @Min(1)
        @Max(1000000)
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

    public static class HealthResponse {
        private String status;

        public HealthResponse(String status) {
            this.status = status;
        }

        public String getStatus() {
            return status;
        }
    }

    public static class ErrorResponse {
        private String error;

        public ErrorResponse(String error) {
            this.error = error;
        }

        public String getError() {
            return error;
        }
    }
}
```

FILE: src/main/java/com/example/ordersservice/controller/GlobalExceptionHandler.java
```java
package com.example.ordersservice.controller;

import com.example.ordersservice.controller.OrderController.ErrorResponse;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.stream.Collectors;

@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ErrorResponse> handleValidationExceptions(MethodArgumentNotValidException ex) {
        String message = ex.getBindingResult().getFieldErrors().stream()
                .map(e -> e.getField() + ": " + e.getDefaultMessage())
                .collect(Collectors.joining(", "));
        return ResponseEntity.badRequest().body(new ErrorResponse(message));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ErrorResponse> handleHttpMessageNotReadable(HttpMessageNotReadableException ex) {
        return ResponseEntity.badRequest().body(new ErrorResponse("Invalid JSON body"));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ErrorResponse> handleGeneral(Exception ex) {
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(new ErrorResponse("Internal Server Error"));
    }
}
```

FILE: src/main/java/com/example/ordersservice/service/OrderService.java
```java
package com.example.ordersservice.service;

import com.example.ordersservice.controller.OrderController.CreateOrderItemRequest;
import com.example.ordersservice.model.Order;
import com.example.ordersservice.model.OrderItem;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

@Service
public class OrderService {

    private final Map<String, Order> orders = new ConcurrentHashMap<>();

    public Order createOrder(String customerId, List<CreateOrderItemRequest> items) {
        Order order = new Order();
        order.setCustomerId(customerId);

        long totalCents = 0;
        List<OrderItem> orderItems = new ArrayList<>(items.size());

        for (CreateOrderItemRequest itemReq : items) {
            OrderItem item = new OrderItem();
            item.setSku(itemReq.getSku());
            item.setQuantity(itemReq.getQuantity());
            item.setUnitPriceCents(itemReq.getUnitPriceCents());
            
            long itemTotal = (long) itemReq.getQuantity() * itemReq.getUnitPriceCents();
            totalCents += itemTotal;
            
            orderItems.add(item);
        }

        order.setItems(orderItems);
        order.setTotalCents(totalCents);

        orders.put(order.getId(), order);
        return order;
    }

    public Order getOrder(String id) {
        return orders.get(id);
    }
}
```

FILE: src/main/java/com/example/ordersservice/logging/RequestLoggingFilter.java
```java
package com.example.ordersservice.logging;

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
import java.util.Map;

@Component
public class RequestLoggingFilter implements Filter {

    private static final Logger logger = LoggerFactory.getLogger(RequestLoggingFilter.class);

    @Override
    public void doFilter(ServletRequest request, ServletResponse response, FilterChain chain)
            throws IOException, ServletException {
        
        HttpServletRequest httpRequest = (HttpServletRequest) request;
        HttpServletResponse httpResponse = (HttpServletResponse) response;
        
        long startTime = System.currentTimeMillis();
        String method = httpRequest.getMethod();
        String path = httpRequest.getRequestURI();
        
        try {
            chain.doFilter(request, response);
        } finally {
            long duration = System.currentTimeMillis() - startTime;
            int status = httpResponse.getStatus();
            
            // Simple JSON log line
            String logEntry = String.format(
                "{\"method\":\"%s\",\"path\":\"%s\",\"status\":%d,\"durationMs\":%d}",
                method, path, status, duration
            );
            logger.info(logEntry);
        }
    }
}
```

FILE: src/main/resources/logback-spring.xml
```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <include resource="org/springframework/boot/logging/logback/defaults.xml"/>
    
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} [%thread] %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

FILE: src/main/resources/application.properties
```properties
server.port=${PORT:8080}
```

FILE: src/test/java/com/example/ordersservice/OrderControllerTest.java
```java
package com.example.ordersservice;

import com.example.ordersservice.controller.OrderController;
import com.example.ordersservice.controller.OrderController.CreateOrderRequest;
import com.example.ordersservice.controller.OrderController.CreateOrderItemRequest;
import com.example.ordersservice.model.Order;
import com.example.ordersservice.service.OrderService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.util.Collections;
import java.util.List;

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

    @Autowired
    private OrderService orderService;

    @BeforeEach
    void setUp() {
        // Clear any existing orders from previous tests if necessary, 
        // though Spring Boot context usually restarts per test class or method depending on config.
        // For simplicity in this demo, we rely on fresh context or clear manually if needed.
        // Note: In a real app, we might use @DirtiesContext or clear the map in a @BeforeEach.
        // Here, we'll just assume clean state for the test methods.
    }

    @Test
    void createOrderSuccess() throws Exception {
        CreateOrderRequest request = new CreateOrderRequest();
        request.setCustomerId("c-1");
        
        CreateOrderItemRequest item = new CreateOrderItemRequest();
        item.setSku("A-1");
        item.setQuantity(2);
        item.setUnitPriceCents(1250);
        
        request.setItems(Collections.singletonList(item));

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
                .andExpect(jsonPath("$.items[0].sku").value("A-1"))
                .andExpect(jsonPath("$.items[0].quantity").value(2))
                .andExpect(jsonPath("$.items[0].unitPriceCents").value(1250))
                .andExpect(jsonPath("$.totalCents").value(2500))
                .andExpect(jsonPath("$.id").isNotEmpty())
                .andExpect(jsonPath("$.createdAt").isNotEmpty());
    }

    @Test
    void createOrderMissingCustomerId() throws Exception {
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
    void createOrderEmptyItems() throws Exception {
        String json = """
            {
                "customerId": "c-1",
                "items": []
            }
            """;

        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").exists());
    }

    @Test
    void createOrderInvalidQuantity() throws Exception {
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
    void createOrderInvalidUnitPriceCents() throws Exception {
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
    void createOrderInvalidJson() throws Exception {
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{ invalid json }"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").exists());
    }

    @Test
    void getOrderSuccess() throws Exception {
        // Create an order first
        String createJson = """
            {
                "customerId": "c-2",
                "items": [
                    {
                        "sku": "B-2",
                        "quantity": 1,
                        "unitPriceCents": 500
                    }
                ]
            }
            """;

        MvcResult mvcResult = mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(createJson))
                .andExpect(status().isCreated())
                .andReturn();

        String orderId = mvcResult.getResponse().getHeader("Location").split("/")[2];

        mockMvc.perform(get("/orders/" + orderId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.customerId").value("c-2"))
                .andExpect(jsonPath("$.id").value(orderId));
    }

    @Test
    void getOrderNotFound() throws Exception {
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