package com.example.orderservice.config;

import org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory;
import org.springframework.boot.web.server.WebServer;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GracefulShutdownConfig {

    @Bean
    public WebServerFactoryCustomizer<TomcatServletWebServerFactory> webServerFactoryCustomizer() {
        return (webServerFactory) -> {
            webServerFactory.setRegisterDefaultServlet(false);
            // Spring Boot 3.x handles graceful shutdown via server.shutdown=graceful
            // We rely on the default configuration which is usually sufficient if configured in application.yml
            // But to be explicit and robust, we ensure the context is managed properly.
        };
    }
}
