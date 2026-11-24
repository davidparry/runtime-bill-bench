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

    public Order(String id, String customerId, List<OrderItem> items, long totalCents, Instant createdAt) {
        this.id = Objects.requireNonNull(id);
        this.customerId = Objects.requireNonNull(customerId);
        this.items = List.copyOf(Objects.requireNonNull(items));
        this.totalCents = totalCents;
        this.createdAt = Objects.requireNonNull(createdAt);
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

    public static class OrderItem {
        private final String sku;
        private final int quantity;
        private final long unitPriceCents;

        public OrderItem(String sku, int quantity, long unitPriceCents) {
            this.sku = Objects.requireNonNull(sku);
            this.quantity = quantity;
            this.unitPriceCents = unitPriceCents;
        }

        public String getSku() {
            return sku;
        }

        public int getQuantity() {
            return quantity;
        }

        public long getUnitPriceCents() {
            return unitPriceCents;
        }
    }
}
```

FILE: src/main/java/com/example/orderservice/model/CreateOrderRequest.java
```java
package com.example.orderservice.model;

import java.util.List;

public class CreateOrderRequest {

    private String customerId;
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
        private String sku;
        private int quantity;
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

FILE: src/main/java/com/example/orderservice/controller/OrderController.java
```java
package com.example.orderservice.controller;

import com.example.orderservice.model.CreateOrderRequest;
import com.example.orderservice.model.CreateOrderRequest.OrderItemRequest;
import com.example.orderservice.model.Order;
import com.example.orderservice.model.Order.OrderItem;
import com.example.orderservice.service.OrderService;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.ConstraintViolationException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.net.URI;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/orders")
public class OrderController {

    private static final Logger log = LoggerFactory.getLogger(OrderController.class);

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    public ResponseEntity<Order> createOrder(@RequestBody CreateOrderRequest request) {
        List<String> errors = validate(request);
        if (!errors.isEmpty()) {
            return ResponseEntity.badRequest()
                    .body(createErrorResponse(errors.get(0)));
        }

        List<OrderItem> items = new ArrayList<>();
        long totalCents = 0;
        for (OrderItemRequest itemReq : request.getItems()) {
            OrderItem item = new OrderItem(itemReq.getSku(), itemReq.getQuantity(), itemReq.getUnitPriceCents());
            items.add(item);
            totalCents += (long) itemReq.getQuantity() * itemReq.getUnitPriceCents();
        }

        String orderId = UUID.randomUUID().toString();
        Order order = new Order(orderId, request.getCustomerId(), items, totalCents, Instant.now());
        orderService.save(order);

        URI location = URI.create("/orders/" + orderId);
        return ResponseEntity.created(location).body(order);
    }

    @GetMapping("/{id}")
    public ResponseEntity<Order> getOrder(@PathVariable String id) {
        Order order = orderService.findById(id);
        if (order == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(order);
    }

    private Order createErrorResponse(String message) {
        // We need to return a JSON body, but ResponseEntity.body expects an Order object.
        // Since Order doesn't have an 'error' field, we need a custom approach or a generic type.
        // However, standard Spring Boot handles Map<String, String> as JSON automatically.
        // To strictly follow the return type ResponseEntity<Order>, we might need a wrapper or just return ResponseEntity.ok with a Map if the contract allows dynamic types.
        // The prompt says: respond 400 with {"error": "<message>"}.
        // ResponseEntity.ok(Map.of("error", message)) works because Spring serializes the map.
        // But the return type is ResponseEntity<Order>. This is a type mismatch for the error case if we strictly type it.
        // Let's change the return type to ResponseEntity<?> to handle both cases properly.
        return null; // Placeholder, logic below handles it.
    }
    
    // Refactored createOrder to handle the error response correctly without type mismatch warnings
    public ResponseEntity<?> createOrderRefactored(CreateOrderRequest request) {
        List<String> errors = validate(request);
        if (!errors.isEmpty()) {
            return ResponseEntity.badRequest().body(java.util.Map.of("error", errors.get(0)));
        }

        List<OrderItem> items = new ArrayList<>();
        long totalCents = 0;
        for (OrderItemRequest itemReq : request.getItems()) {
            OrderItem item = new OrderItem(itemReq.getSku(), itemReq.getQuantity(), itemReq.getUnitPriceCents());
            items.add(item);
            totalCents += (long) itemReq.getQuantity() * itemReq.getUnitPriceCents();
        }

        String orderId = UUID.randomUUID().toString();
        Order order = new Order(orderId, request.getCustomerId(), items, totalCents, Instant.now());
        orderService.save(order);

        URI location = URI.create("/orders/" + orderId);
        return ResponseEntity.created(location).body(order);
    }

    // Note: I will replace the method above with this one in the actual file content to ensure compilation.
    
    private List<String> validate(CreateOrderRequest request) {
        List<String> errors = new ArrayList<>();
        if (request == null) {
            errors.add("Request body is required");
            return errors;
        }
        if (request.getCustomerId() == null || request.getCustomerId().isEmpty()) {
            errors.add("customerId is required");
        } else if (request.getCustomerId().length() < 1 || request.getCustomerId().length() > 64) {
            errors.add("customerId must be between 1 and 64 characters");
        }
        
        if (request.getItems() == null || request.getItems().isEmpty()) {
            errors.add("items is required and must have at least 1 entry");
        } else if (request.getItems().size() > 50) {
            errors.add("items must have at most 50 entries");
        } else {
            int idx = 0;
            for (OrderItemRequest item : request.getItems()) {
                if (item == null) {
                    errors.add("items[" + idx + "] is required");
                    idx++;
                    continue;
                }
                if (item.getSku() == null || item.getSku().isEmpty()) {
                    errors.add("items[" + idx + "].sku is required");
                } else if (item.getSku().length() < 1 || item.getSku().length() > 32) {
                    errors.add("items[" + idx + "].sku must be between 1 and 32 characters");
                }
                
                if (item.getQuantity() < 1 || item.getQuantity() > 100) {
                    errors.add("items[" + idx + "].quantity must be between 1 and 100");
                }
                
                if (item.getUnitPriceCents() < 1 || item.getUnitPriceCents() > 1000000) {
                    errors.add("items[" + idx + "].unitPriceCents must be between 1 and 1000000");
                }
                idx++;
            }
        }
        return errors;
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

FILE: src/main/java/com/example/orderservice/exception/CustomErrorController.java
```java
package com.example.orderservice.exception;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.boot.autoconfigure.web.servlet.error.AbstractErrorController;
import org.springframework.boot.web.error.ErrorAttributeOptions;
import org.springframework.boot.web.servlet.error.ErrorAttributes;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;

import java.util.Map;
import java.util.LinkedHashMap;

@Controller
public class CustomErrorController extends AbstractErrorController {

    public CustomErrorController(ErrorAttributes errorAttributes) {
        super(errorAttributes);
    }

    @RequestMapping("/error")
    public ResponseEntity<Map<String, String>> handleError(HttpServletRequest request) {
        HttpStatus status = getStatus(request);
        
        if (status == HttpStatus.NOT_FOUND) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                    .body(Map.of("error", "Order not found"));
        }

        return ResponseEntity.status(status)
                .body(Map.of("error", "An error occurred"));
    }
}
```

FILE: src/main/java/com/example/orderservice/config/OrderController.java
```java
// This file is intentionally left blank or removed. 
// The logic in src/main/java/com/example/orderservice/controller/OrderController.java 
// had a small issue with method signature return type. 
// Let's fix OrderController.java properly below.
```

FILE: src/main/java/com/example/orderservice/controller/OrderController.java
```java
package com.example.orderservice.controller;

import com.example.orderservice.model.CreateOrderRequest;
import com.example.orderservice.model.CreateOrderRequest.OrderItemRequest;
import com.example.orderservice.model.Order;
import com.example.orderservice.model.Order.OrderItem;
import com.example.orderservice.service.OrderService;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.http.HttpHeaders;

import java.net.URI;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    public ResponseEntity<?> createOrder(@RequestBody CreateOrderRequest request) {
        List<String> errors = validate(request);
        if (!errors.isEmpty()) {
            return ResponseEntity.badRequest().body(Map.of("error", errors.get(0)));
        }

        List<OrderItem> items = new ArrayList<>();
        long totalCents = 0;
        for (OrderItemRequest itemReq : request.getItems()) {
            OrderItem item = new OrderItem(itemReq.getSku(), itemReq.getQuantity(), itemReq.getUnitPriceCents());
            items.add(item);
            totalCents += (long) itemReq.getQuantity() * itemReq.getUnitPriceCents();
        }

        String orderId = UUID.randomUUID().toString();
        Order order = new Order(orderId, request.getCustomerId(), items, totalCents, Instant.now());
        orderService.save(order);

        URI location = URI.create("/orders/" + orderId);
        HttpHeaders headers = new HttpHeaders();
        headers.setLocation(location);
        
        return ResponseEntity.status(HttpStatus.CREATED)
                .headers(headers)
                .body(order);
    }

    @GetMapping("/{id}")
    public ResponseEntity<Order> getOrder(@PathVariable String id) {
        Order order = orderService.findById(id);
        if (order == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(order);
    }

    private List<String> validate(CreateOrderRequest request) {
        List<String> errors = new ArrayList<>();
        if (request == null) {
            errors.add("Request body is required");
            return errors;
        }
        if (request.getCustomerId() == null || request.getCustomerId().isEmpty()) {
            errors.add("customerId is required");
        } else if (request.getCustomerId().length() < 1 || request.getCustomerId().length() > 64) {
            errors.add("customerId must be between 1 and 64 characters");
        }
        
        if (request.getItems() == null || request.getItems().isEmpty()) {
            errors.add("items is required and must have at least 1 entry");
        } else if (request.getItems().size() > 50) {
            errors.add("items must have at most 50 entries");
        } else {
            int idx = 0;
            for (OrderItemRequest item : request.getItems()) {
                if (item == null) {
                    errors.add("items[" + idx + "] is required");
                    idx++;
                    continue;
                }
                if (item.getSku() == null || item.getSku().isEmpty()) {
                    errors.add("items[" + idx + "].sku is required");
                } else if (item.getSku().length() < 1 || item.getSku().length() > 32) {
                    errors.add("items[" + idx + "].sku must be between 1 and 32 characters");
                }
                
                if (item.getQuantity() < 1 || item.getQuantity() > 100) {
                    errors.add("items[" + idx + "].quantity must be between 1 and 100");
                }
                
                if (item.getUnitPriceCents() < 1 || item.getUnitPriceCents() > 1000000) {
                    errors.add("items[" + idx + "].unitPriceCents must be between 1 and 1000000");
                }
                idx++;
            }
        }
        return errors;
    }
}
```

FILE: src/main/java/com/example/orderservice/config/GlobalExceptionHandler.java
```java
package com.example.orderservice.config;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.Map;

@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<Map<String, String>> handleBadRequest(HttpMessageNotReadableException ex) {
        return ResponseEntity.badRequest().body(Map.of("error", "Invalid JSON format"));
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

    private static final Logger log = LoggerFactory.getLogger(LoggingFilter.class);

    @Override
    public void doFilter(ServletRequest request, ServletResponse response, FilterChain chain)
            throws IOException, ServletException {
        HttpServletRequest httpRequest = (HttpServletRequest) request;
        HttpServletResponse httpResponse = (HttpServletResponse) response;

        long startTime = System.currentTimeMillis();
        chain.doFilter(request, response);
        long duration = System.currentTimeMillis() - startTime;

        Map<String, Object> logEntry = new LinkedHashMap<>();
        logEntry.put("method", httpRequest.getMethod());
        logEntry.put("path", httpRequest.getRequestURI());
        logEntry.put("status", httpResponse.getStatus());
        logEntry.put("durationMs", duration);

        log.info("{}", logEntry);
    }
}
```

FILE: src/main/java/com/example/orderservice/config/GracefulShutdownConfig.java
```java
package com.example.orderservice.config;

import org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory;
import org.springframework.boot.web.server.WebServer;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GracefulShutdownConfig {

    @Bean
    public WebServerFactoryCustomizer<TomcatServletWebServerFactory> webServerFactoryCustomizer() {
        return (webServerFactory) -> {
            webServerFactory.setRegisterDefaultServlet(false);
            // Spring Boot 3.x handles graceful shutdown via server.shutdown=graceful
            // We rely on the default configuration which is usually sufficient if configured in application.yml
            // But to be explicit and robust, we ensure the context is managed properly.
        };
    }
}
```

FILE: src/main/resources/application.yml
```yaml
server:
  port: ${PORT:8080}
  shutdown: graceful

logging:
  pattern:
    console: "%clr(%d{yyyy-MM-dd HH:mm:ss.SSS}){faint} %clr(%5p) %clr(${PID:- }){magenta} %clr(---){faint} %clr([%15.15t]){faint} %clr(%-40.40logger{39}){cyan} %clr(:){faint} %m%n%wEx"
```

FILE: src/test/java/com/example/orderservice/controller/OrderControllerTest.java
```java
package com.example.orderservice.controller;

import com.example.orderservice.model.CreateOrderRequest;
import com.example.orderservice.model.CreateOrderRequest.OrderItemRequest;
import com.example.orderservice.model.Order;
import com.example.orderservice.service.OrderService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.util.List;
import java.util.Map;

import static org.hamcrest.Matchers.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private OrderService orderService;

    @Test
    void createOrder_validRequest_returns201AndOrder() throws Exception {
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

        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isCreated())
                .andExpect(header().exists("Location"))
                .andExpect(jsonPath("$.customerId", is("c-1")))
                .andExpect(jsonPath("$.items[0].sku", is("A-1")))
                .andExpect(jsonPath("$.items[0].quantity", is(2)))
                .andExpect(jsonPath("$.items[0].unitPriceCents", is(1250)))
                .andExpect(jsonPath("$.totalCents", is(2500)))
                .andExpect(jsonPath("$.createdAt").isNotEmpty());
    }

    @Test
    void createOrder_invalidCustomerId_returns400() throws Exception {
        String json = """
                {
                  "customerId": "",
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
                .andExpect(jsonPath("$.error").isNotEmpty());
    }

    @Test
    void createOrder_invalidQuantity_returns400() throws Exception {
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
                .andExpect(jsonPath("$.error").isNotEmpty());
    }

    @Test
    void createOrder_invalidSku_returns400() throws Exception {
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
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").isNotEmpty());
    }

    @Test
    void createOrder_invalidUnitPriceCents_returns400() throws Exception {
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
                .andExpect(jsonPath("$.error").isNotEmpty());
    }

    @Test
    void createOrder_tooManyItems_returns400() throws Exception {
        StringBuilder sb = new StringBuilder();
        sb.append("{\"customerId\":\"c-1\",\"items\":[");
        for (int i = 0; i < 51; i++) {
            if (i > 0) sb.append(",");
            sb.append("{\"sku\":\"A-\",\"quantity\":1,\"unitPriceCents\":1}");
        }
        sb.append("]}");

        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(sb.toString()))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").isNotEmpty());
    }

    @Test
    void createOrder_invalidJson_returns400() throws Exception {
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{ invalid json }"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").isNotEmpty());
    }

    @Test
    void getOrder_existingOrder_returns200() throws Exception {
        // First create an order
        String json = """
                {
                  "customerId": "c-1",
                  "items": [
                    {
                      "sku": "A-1",
                      "quantity": 1,
                      "unitPriceCents": 100
                    }
                  ]
                }
                """;

        MvcResult result = mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").isNotEmpty())
                .andReturn();

        String orderId = result.getResponse().getContentAsString();
        // Extract ID from JSON body
        String id = result.getResolvedJsonPath("$.id");

        mockMvc.perform(get("/orders/" + id))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id", is(id)))
                .andExpect(jsonPath("$.customerId", is("c-1")));
    }

    @Test
    void getOrder_nonExistentOrder_returns404() throws Exception {
        mockMvc.perform(get("/orders/non-existent-id"))
                .andExpect(status().isNotFound());
    }

    @Test
    void health_check_returns200() throws Exception {
        mockMvc.perform(get("/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status", is("ok")));
    }
}
```

FILE: src/test/java/com/example/orderservice/service/OrderServiceTest.java
```java
package com.example.orderservice.service;

import com.example.orderservice.model.Order;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

class OrderServiceTest {

    @Test
    void saveAndFindById() {
        OrderService orderService = new OrderService();
        String id = UUID.randomUUID().toString();
        Order order = new Order(id, "c-1", List.of(), 0, Instant.now());
        
        orderService.save(order);
        
        Order found = orderService.findById(id);
        assertNotNull(found);
        assertEquals(id, found.getId());
    }

    @Test
    void findNonExistentById() {
        OrderService orderService = new OrderService();
        Order found = orderService.findById("non-existent");
        assertNull(found);
    }
}
```