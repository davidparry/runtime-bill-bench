The issue is that the `LoggingFilter` is not being registered as a Spring Bean. In the previous iteration, it was just a class implementing `Filter`. While Spring Boot can auto-configure filters if they are beans or registered via `FilterRegistrationBean`, simply having the class isn't enough if it's not picked up by the component scan or explicitly registered. The `@Component` annotation was present in the first version but might have been lost or the bean registration order might be tricky.

However, the most robust way to ensure the filter is applied and logs to `System.out` (which is what the harness is checking) is to register it explicitly or ensure it's a bean. The previous code had `@Component` on `LoggingFilter`. Why did it fail?

Looking at the output:
`found 0` JSON lines.
The logs shown are standard Spring Boot logs.

If the filter is not running, no JSON lines will be printed to stdout.

Let's ensure the filter is properly registered. I will use `@Component` and also ensure it's added to the `FilterRegistrationBean` if necessary, but `@Component` on a `Filter` usually works in Spring Boot 3.x.

Wait, looking at the previous `LoggingFilter` code I provided:
```java
public class LoggingFilter implements Filter {
```
It does **not** have `@Component`. I removed it in the last step thinking I was just fixing the logic, but I need to keep it or register it.

Actually, the best practice for a custom filter that needs to be a bean is to annotate it with `@Component`.

I will add `@Component` back to `LoggingFilter`.

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
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.Map;

@Component
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