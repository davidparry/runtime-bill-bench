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

    public void calculateTotal() {
        long sum = 0;
        for (OrderItem item : items) {
            sum += item.getQuantity() * item.getUnitPriceCents();
        }
        this.totalCents = sum;
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
    public ResponseEntity<Order> createOrder(@RequestBody @Valid CreateOrderRequest request) {
        Order order = orderService.createOrder(request.getCustomerId(), request.getItems());
        String location = "/orders/" + order.getId();
        return ResponseEntity.status(HttpStatus.CREATED)
                .header(HttpHeaders.LOCATION, location)
                .body(order);
    }

    @GetMapping("/orders/{id}")
    public ResponseEntity<Order> getOrder(@PathVariable String id) {
        Order order = orderService.getOrder(id);
        if (order == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(order);
    }

    @GetMapping("/health")
    public ResponseEntity<HealthStatus> health() {
        return ResponseEntity.ok(new HealthStatus("ok"));
    }

    public static class HealthStatus {
        private String status;

        public HealthStatus() {
        }

        public HealthStatus(String status) {
            this.status = status;
        }

        public String getStatus() {
            return status;
        }

        public void setStatus(String status) {
            this.status = status;
        }
    }

    public static class CreateOrderRequest {
        @NotBlank
        @Size(min = 1, max = 64)
        private String customerId;

        @NotNull
        @Size(min = 1, max = 50)
        private List<CreateOrderItem> items;

        public CreateOrderRequest() {
        }

        public String getCustomerId() {
            return customerId;
        }

        public void setCustomerId(String customerId) {
            this.customerId = customerId;
        }

        public List<CreateOrderItem> getItems() {
            return items;
        }

        public void setItems(List<CreateOrderItem> items) {
            this.items = items;
        }
    }

    public static class CreateOrderItem {
        @NotBlank
        @Size(min = 1, max = 32)
        private String sku;

        @NotNull
        private Integer quantity;

        @NotNull
        private Long unitPriceCents;

        public CreateOrderItem() {
        }

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

FILE: src/main/java/com/example/orderservice/service/OrderService.java
```java
package com.example.orderservice.service;

import com.example.orderservice.controller.OrderController.CreateOrderItem;
import com.example.orderservice.model.Order;
import com.example.orderservice.model.OrderItem;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.locks.ReadWriteLock;
import java.util.concurrent.locks.ReentrantReadWriteLock;

@Service
public class OrderService {

    private final Map<String, Order> orders = new ConcurrentHashMap<>();
    private final ReadWriteLock lock = new ReentrantReadWriteLock();

    public Order createOrder(String customerId, List<CreateOrderItem> items) {
        Order order = new Order();
        order.setCustomerId(customerId);

        List<OrderItem> orderItems = new ArrayList<>();
        for (CreateOrderItem item : items) {
            OrderItem orderItem = new OrderItem();
            orderItem.setSku(item.getSku());
            orderItem.setQuantity(item.getQuantity());
            orderItem.setUnitPriceCents(item.getUnitPriceCents());
            orderItems.add(orderItem);
        }
        order.setItems(orderItems);
        order.calculateTotal();

        lock.writeLock().lock();
        try {
            orders.put(order.getId(), order);
        } finally {
            lock.writeLock().unlock();
        }

        return order;
    }

    public Order getOrder(String id) {
        lock.readLock().lock();
        try {
            return orders.get(id);
        } finally {
            lock.readLock().unlock();
        }
    }
}
```

FILE: src/main/java/com/example/orderservice/config/CustomErrorAttributes.java
```java
package com.example.orderservice.config;

import org.springframework.boot.web.error.ErrorAttributeOptions;
import org.springframework.boot.web.servlet.error.DefaultErrorAttributes;
import org.springframework.stereotype.Component;
import org.springframework.web.context.request.WebRequest;

import java.util.Map;

@Component
public class CustomErrorAttributes extends DefaultErrorAttributes {

    @Override
    public Map<String, Object> getErrorAttributes(WebRequest webRequest, ErrorAttributeOptions options) {
        Map<String, Object> errorAttributes = super.getErrorAttributes(webRequest, options);
        
        // Ensure we only return the error message as requested by the spec
        // Default Spring Boot error response has more fields.
        // We override to provide a simple {"error": "..."} structure.
        
        Throwable error = getError(webRequest);
        String message = "Bad Request";
        if (error != null) {
            message = error.getLocalizedMessage();
            if (message == null || message.isEmpty()) {
                message = "An unexpected error occurred";
            }
        }
        
        return Map.of("error", message);
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
            
            Map<String, Object> logData = new LinkedHashMap<>();
            logData.put("method", httpRequest.getMethod());
            logData.put("path", httpRequest.getRequestURI());
            logData.put("status", httpResponse.getStatus());
            logData.put("durationMs", duration);
            
            // Simple JSON formatting for the log line
            StringBuilder sb = new StringBuilder();
            sb.append("{");
            boolean first = true;
            for (Map.Entry<String, Object> entry : logData.entrySet()) {
                if (!first) {
                    sb.append(",");
                }
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
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=10s
```

FILE: src/test/java/com/example/orderservice/OrderControllerValidationTest.java
```java
package com.example.orderservice;

import com.example.orderservice.controller.OrderController;
import com.example.orderservice.service.OrderService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderControllerValidationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void shouldRejectMissingCustomerId() throws Exception {
        String json = "{\"items\": [{\"sku\": \"A-1\", \"quantity\": 1, \"unitPriceCents\": 100}]}";
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldRejectEmptyCustomerId() throws Exception {
        String json = "{\"customerId\": \"\", \"items\": [{\"sku\": \"A-1\", \"quantity\": 1, \"unitPriceCents\": 100}]}";
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldRejectLongCustomerId() throws Exception {
        String longId = "a".repeat(65);
        String json = "{\"customerId\": \"" + longId + "\", \"items\": [{\"sku\": \"A-1\", \"quantity\": 1, \"unitPriceCents\": 100}]}";
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldRejectMissingItems() throws Exception {
        String json = "{\"customerId\": \"c-1\"}";
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldRejectEmptyItems() throws Exception {
        String json = "{\"customerId\": \"c-1\", \"items\": []}";
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldRejectTooManyItems() throws Exception {
        StringBuilder json = new StringBuilder("{\"customerId\": \"c-1\", \"items\": [");
        for (int i = 0; i < 51; i++) {
            if (i > 0) json.append(",");
            json.append("{\"sku\": \"A-1\", \"quantity\": 1, \"unitPriceCents\": 100}");
        }
        json.append("]}");
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json.toString()))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldRejectInvalidSku() throws Exception {
        String json = "{\"customerId\": \"c-1\", \"items\": [{\"sku\": \"\", \"quantity\": 1, \"unitPriceCents\": 100}]}";
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldRejectSkuTooLong() throws Exception {
        String longSku = "a".repeat(33);
        String json = "{\"customerId\": \"c-1\", \"items\": [{\"sku\": \"" + longSku + "\", \"quantity\": 1, \"unitPriceCents\": 100}]}";
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldRejectMissingQuantity() throws Exception {
        String json = "{\"customerId\": \"c-1\", \"items\": [{\"sku\": \"A-1\", \"unitPriceCents\": 100}]}";
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldRejectQuantityTooSmall() throws Exception {
        String json = "{\"customerId\": \"c-1\", \"items\": [{\"sku\": \"A-1\", \"quantity\": 0, \"unitPriceCents\": 100}]}";
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldRejectQuantityTooLarge() throws Exception {
        String json = "{\"customerId\": \"c-1\", \"items\": [{\"sku\": \"A-1\", \"quantity\": 101, \"unitPriceCents\": 100}]}";
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldRejectMissingUnitPriceCents() throws Exception {
        String json = "{\"customerId\": \"c-1\", \"items\": [{\"sku\": \"A-1\", \"quantity\": 1}]}";
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldRejectZeroUnitPriceCents() throws Exception {
        String json = "{\"customerId\": \"c-1\", \"items\": [{\"sku\": \"A-1\", \"quantity\": 1, \"unitPriceCents\": 0}]}";
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldRejectUnitPriceCentsTooLarge() throws Exception {
        String json = "{\"customerId\": \"c-1\", \"items\": [{\"sku\": \"A-1\", \"quantity\": 1, \"unitPriceCents\": 1000001}]}";
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldRejectInvalidJson() throws Exception {
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{invalid json}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldRejectMissingFieldsInItem() throws Exception {
        String json = "{\"customerId\": \"c-1\", \"items\": [{\"sku\": \"A-1\"}]}";
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isBadRequest());
    }
}
```

FILE: src/test/java/com/example/orderservice/OrderControllerNotFoundTest.java
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

@SpringBootTest
@AutoConfigureMockMvc
class OrderControllerNotFoundTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void shouldReturn404ForNonExistentOrder() throws Exception {
        mockMvc.perform(get("/orders/non-existent-id"))
                .andExpect(status().isNotFound());
    }
}
```