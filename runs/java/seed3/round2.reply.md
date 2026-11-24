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
    public void doFilter(ServletRequest servletRequest, ServletResponse servletResponse, FilterChain filterChain) throws IOException, ServletException {
        HttpServletRequest request = (HttpServletRequest) servletRequest;
        HttpServletResponse response = (HttpServletResponse) servletResponse;
        
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
        String createdAt = Instant.now().atZone(ZoneOffset.UTC).format(FORMATTER);
        
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