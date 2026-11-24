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

    private int status = HttpServletResponse.SC_OK;

    public HttpServletResponseWrapper(HttpServletResponse response) {
        super(response);
    }

    @Override
    public void setStatus(int sc) {
        super.setStatus(sc);
        this.status = sc;
    }

    @Override
    public int getStatus() {
        return this.status;
    }
}
```