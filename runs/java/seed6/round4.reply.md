The previous implementation had two main issues:
1.  **Malformed JSON Handling**: The `LoggingFilter` was logging `status: 500` for malformed JSON because the `@Valid` annotation on `@RequestBody` triggers validation *after* deserialization. If deserialization fails (malformed JSON), Spring throws `HttpMessageNotReadableException` before the controller method is invoked. The `GlobalExceptionHandler` was catching this as a generic `Exception` and returning 500. It needs to specifically handle `HttpMessageNotReadableException` to return 400.
2.  **Logging Output**: The requirement states "Write one JSON log line to standard output per request". The previous implementation used `logger.info()` which goes to the application log file/stream but might be filtered or formatted in a way that doesn't match the strict "JSON object" expectation if the harness is parsing stdout directly. More importantly, the harness explicitly complained about "found 0" lines matching the criteria, implying the output format or location was wrong. While `logger.info` writes to stdout by default in Spring Boot, the harness might be expecting raw JSON without the timestamp/thread prefixes that `logging.pattern.console` adds. To be safe and strictly adhere to "one JSON log line... to standard output", I will write directly to `System.out` using a JSON builder or simple string concatenation to ensure the format is exactly what is expected, bypassing the logging framework's formatting.

I will update:
1.  `GlobalExceptionHandler` to handle `HttpMessageNotReadableException` and return 400.
2.  `LoggingFilter` to write directly to `System.out` in a raw JSON format to satisfy the strict log line requirement.

FILE: src/main/java/com/example/orderservice/config/GlobalExceptionHandler.java
```java
package com.example.orderservice.config;

import com.example.orderservice.controller.OrdersController;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.stream.Collectors;

@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<OrdersController.ErrorResponse> handleNotReadableException(HttpMessageNotReadableException ex) {
        return ResponseEntity.badRequest()
                .body(new OrdersController.ErrorResponse("Invalid JSON: " + ex.getMessage()));
    }

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

import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.Map;

public class LoggingFilter implements Filter {

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
            
            // Write raw JSON to System.out to ensure it matches the expected format
            System.out.println(toJson(logEntry));
        }
    }

    private String toJson(Map<String, Object> map) {
        StringBuilder sb = new StringBuilder();
        sb.append("{");
        boolean first = true;
        for (Map.Entry<String, Object> entry : map.entrySet()) {
            if (!first) {
                sb.append(",");
            }
            first = false;
            String key = escapeJson(entry.getKey());
            Object value = entry.getValue();
            if (value instanceof String) {
                sb.append("\"").append(key).append("\":\"").append(escapeJson((String) value)).append("\"");
            } else if (value instanceof Number) {
                sb.append("\"").append(key).append("\":").append(value);
            } else {
                sb.append("\"").append(key).append("\":\"").append(escapeJson(value.toString())).append("\"");
            }
        }
        sb.append("}");
        return sb.toString();
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