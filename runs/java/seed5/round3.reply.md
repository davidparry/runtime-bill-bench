The issue is that the harness expects the request logs to be valid JSON objects on standard output, but the current implementation logs them as Spring's default logger output (which includes timestamps, thread names, etc., before the JSON string). The harness is parsing the raw stdout lines and expecting them to be JSON.

To fix this, I need to ensure the JSON log line is written directly to `System.out` as a valid JSON string, without any surrounding log framework formatting.

FILE: src/main/java/com/example/orderservice/config/RequestLoggingFilter.java
```java
package com.example.orderservice.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

@Component
public class RequestLoggingFilter extends OncePerRequestFilter {

    private static final ObjectMapper objectMapper = new ObjectMapper();

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {
        
        long startTime = Instant.now().toEpochMilli();
        
        try {
            filterChain.doFilter(request, response);
        } finally {
            long endTime = Instant.now().toEpochMilli();
            long durationMs = endTime - startTime;
            
            Map<String, Object> logEntry = new LinkedHashMap<>();
            logEntry.put("method", request.getMethod());
            logEntry.put("path", request.getRequestURI());
            logEntry.put("status", response.getStatus());
            logEntry.put("durationMs", durationMs);
            
            // Write directly to System.out as a JSON string to satisfy harness requirements
            System.out.println(objectMapper.writeValueAsString(logEntry));
        }
    }
}
```