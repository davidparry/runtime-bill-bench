The issue is that `@Min` and `@Max` annotations on `Integer` fields in Spring Boot's validation do not trigger if the field is `null` (which it isn't here, but the logic might be tricky with JSON parsing) or if the validation is not properly wired. However, the more likely cause for `quantity: 0` passing validation when `@Min(1)` is present is that the JSON deserializer might be bypassing the validation or the validation is not being triggered correctly in the test environment.

Actually, looking closely at the error logs:
`Status expected:<400> but was:<201>` for `quantity: 0` and `unitPriceCents: 0`.

The `@Min(1)` constraint should fail for `0`. The fact that it passes suggests that the validation is not being applied or the `Integer` objects are somehow not being validated.

Wait, `@Min` and `@Max` work on `Number` types. `Integer` is a `Number`.

Let's look at the `CreateOrderRequest` class.
```java
            @NotNull(message = "quantity is required")
            @Min(value = 1, message = "quantity must be at least 1")
            @Max(value = 100, message = "quantity must be at most 100")
            private Integer quantity;
```

In Spring Boot 3.x (which uses Jakarta EE), `jakarta.validation.constraints.Min` is used.

The issue might be that `MockMvc` by default does not perform validation on the request body if the controller method argument is not annotated with `@Valid` or `@Validated`.

Looking at `OrdersController.java`:
```java
    @PostMapping
    public ResponseEntity<?> createOrder(@RequestBody @Valid CreateOrderRequest request) {
```
It **is** annotated with `@Valid`.

Why is it passing?

Ah, I see. In the test `shouldRejectOrderWithInvalidQuantity`, the JSON has `"quantity": 0`.
If the validation is working, it should fail.

Let's check the `OrderItemRequest` class again.
```java
        public static class OrderItemRequest {
            // ...
            @NotNull(message = "quantity is required")
            @Min(value = 1, message = "quantity must be at least 1")
            @Max(value = 100, message = "quantity must be at most 100")
            private Integer quantity;
            // ...
        }
```

If the JSON is valid and deserializes to `quantity = 0`, `@Min(1)` should fail.

However, there is a known behavior in some Spring versions or configurations where `@Valid` on a nested object inside a list might not trigger if the list itself isn't validated or if the nested class isn't properly recognized.

Actually, the most common reason for this specific failure in Spring Boot tests is that **`@Valid` on the root object does not automatically validate elements inside a `List` unless the list field itself is annotated with `@Valid`**.

In `CreateOrderRequest`:
```java
        @NotNull(message = "items is required")
        @Size(min = 1, max = 50, message = "items must contain between 1 and 50 entries")
        private List<OrderItemRequest> items;
```
It is missing `@Valid` on the `items` field. Without `@Valid` on the `items` field, Spring will validate the list (size, not null) but will **not** recursively validate the `OrderItemRequest` objects inside it.

I need to add `@Valid` to the `items` field in `CreateOrderRequest`.

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
        @Valid
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