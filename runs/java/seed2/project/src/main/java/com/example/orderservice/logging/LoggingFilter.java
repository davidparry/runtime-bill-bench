package com.example.orderservice.logging;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.HashMap;
import java.util.Map;

@Component
public class LoggingFilter extends OncePerRequestFilter {

    private static final Logger logger = LoggerFactory.getLogger(LoggingFilter.class);

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {
        
        long startTime = System.currentTimeMillis();
        
        try {
            filterChain.doFilter(request, response);
        } finally {
            long duration = System.currentTimeMillis() - startTime;
            Map<String, Object> logEntry = new HashMap<>();
            logEntry.put("method", request.getMethod());
            logEntry.put("path", request.getRequestURI());
            logEntry.put("status", response.getStatus());
            logEntry.put("durationMs", duration);
            
            // Simple JSON formatting for log line
            StringBuilder sb = new StringBuilder("{");
            sb.append("\"method\":\"").append(logEntry.get("method")).append("\",");
            sb.append("\"path\":\"").append(logEntry.get("path")).append("\",");
            sb.append("\"status\":").append(logEntry.get("status")).append(",");
            sb.append("\"durationMs\":").append(logEntry.get("durationMs"));
            sb.append("}");
            
            logger.info(sb.toString());
        }
    }
}
