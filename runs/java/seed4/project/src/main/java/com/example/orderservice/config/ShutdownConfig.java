package com.example.orderservice.config;

import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.stereotype.Component;

import java.util.Arrays;
import java.util.concurrent.TimeUnit;

@Component
public class ShutdownConfig {

    private static final Logger logger = LoggerFactory.getLogger(ShutdownConfig.class);

    @PreDestroy
    public void shutdown() {
        logger.info("Application is shutting down...");
        // Spring Boot handles the actual shutdown lifecycle, but we can log here.
    }
}
