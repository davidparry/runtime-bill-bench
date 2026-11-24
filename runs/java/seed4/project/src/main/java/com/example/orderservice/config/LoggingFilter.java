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
        
        // Use a custom wrapper class located in the same package but with a different name to avoid conflict
        // However, since HttpServletResponseWrapper is in jakarta.servlet.http, we can just use a different class name
        // But wait, the error says HttpServletResponseWrapper is already defined. 
        // This implies that there might be another class with that name in the package or a naming conflict.
        // Actually, the error "com.example.orderservice.config.HttpServletResponseWrapper is already defined in this compilation unit"
        // suggests that the class definition itself is duplicated in the source file or there's a weird compile state.
        // But looking at the file content, it's a single class.
        // Let's rename the wrapper to avoid any potential confusion with the Jakarta class, although the package is different.
        // The error message is strange. Let's try renaming the class to CustomResponseWrapper.
        
        CustomResponseWrapper responseWrapper = new CustomResponseWrapper(response);
        
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
