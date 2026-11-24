FILE: src/main/java/com/example/orderservice/controller/OrdersController.java
```java
package com.example.orderservice.controller;

import com.example.orderservice.model.Order;
import com.example.orderservice.model.OrderItem;
import com.example.orderservice.service.OrderStore;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;
import java.util.HashMap;

@RestController
@RequestMapping("/orders")
public class OrdersController {

    private final OrderStore orderStore;

    public OrdersController(OrderStore orderStore) {
        this.orderStore = orderStore;
    }

    @PostMapping
    public ResponseEntity<?> createOrder(@Valid @RequestBody CreateOrderRequest request) {
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
    public void doFilter(jakarta.servlet.ServletRequest servletRequest, 
                         jakarta.servlet.ServletResponse servletResponse, 
                         FilterChain filterChain) 
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