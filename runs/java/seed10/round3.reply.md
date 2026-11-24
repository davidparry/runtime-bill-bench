FILE: src/main/java/com/example/orderservice/config/CustomErrorController.java
```java
package com.example.orderservice.config;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.boot.autoconfigure.web.servlet.error.AbstractErrorController;
import org.springframework.boot.web.error.ErrorAttributeOptions;
import org.springframework.boot.web.servlet.error.ErrorAttributes;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.RequestMapping;

import java.util.Map;

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
                    .contentType(org.springframework.http.MediaType.APPLICATION_JSON)
                    .body(Map.of("error", "Order not found"));
        }

        return ResponseEntity.status(status)
                .contentType(org.springframework.http.MediaType.APPLICATION_JSON)
                .body(Map.of("error", "An error occurred"));
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
        try {
            chain.doFilter(request, response);
        } finally {
            long duration = System.currentTimeMillis() - startTime;

            Map<String, Object> logEntry = new LinkedHashMap<>();
            logEntry.put("method", httpRequest.getMethod());
            logEntry.put("path", httpRequest.getRequestURI());
            logEntry.put("status", httpResponse.getStatus());
            logEntry.put("durationMs", duration);

            log.info("{}", logEntry);
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
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;

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

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<?> createOrder(@RequestBody CreateOrderRequest request) {
        List<String> errors = validate(request);
        if (!errors.isEmpty()) {
            return ResponseEntity.badRequest()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(Map.of("error", errors.get(0)));
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
                .contentType(MediaType.APPLICATION_JSON)
                .body(order);
    }

    @GetMapping(value = "/{id}", produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Order> getOrder(@PathVariable String id) {
        Order order = orderService.findById(id);
        if (order == null) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(null);
        }
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(order);
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