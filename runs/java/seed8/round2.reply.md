FILE: src/main/java/com/example/orderservice/controller/OrderController.java
```java
package com.example.orderservice.controller;

import com.example.orderservice.model.Order;
import com.example.orderservice.model.OrderItem;
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
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.support.WebExchangeBindException;

import java.util.ArrayList;
import java.util.List;

@RestController
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping("/orders")
    public ResponseEntity<Order> createOrder(@RequestBody @Valid CreateOrderRequest request,
                                             org.springframework.validation.Errors errors) {
        if (errors.hasErrors()) {
            String message = errors.getFieldErrors().stream()
                    .map(fe -> fe.getField() + ": " + fe.getDefaultMessage())
                    .reduce((a, b) -> a + "; " + b)
                    .orElse("Validation failed");
            return ResponseEntity.badRequest().body(null);
        }

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
        @Min(1)
        @Max(100)
        private Integer quantity;

        @NotNull
        @Min(1)
        @Max(1000000)
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
        // Return standard Spring Boot error structure for general errors
        return super.getErrorAttributes(webRequest, options);
    }
}
```

FILE: src/main/java/com/example/orderservice/config/ValidationExceptionHandler.java
```java
package com.example.orderservice.config;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.Map;
import java.util.stream.Collectors;

@RestControllerAdvice
public class ValidationExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, String>> handleValidationExceptions(MethodArgumentNotValidException ex) {
        String message = ex.getBindingResult().getFieldErrors().stream()
                .map(fe -> fe.getField() + ": " + fe.getDefaultMessage())
                .collect(Collectors.joining(", "));
        
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .body(Map.of("error", message));
    }
}
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