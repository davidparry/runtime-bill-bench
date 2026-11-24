package com.example.orderservice;

import com.example.orderservice.config.GlobalExceptionHandler;
import com.example.orderservice.model.OrderItem;
import com.example.orderservice.service.OrderStore;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.util.List;
import java.util.Map;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

@SpringBootTest
@AutoConfigureMockMvc
class OrderValidationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private OrderStore orderStore;

    @Test
    void shouldReturn400WhenCustomerIdIsEmpty() throws Exception {
        String json = """
            {
              "customerId": "",
              "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]
            }
            """;
        
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldReturn400WhenCustomerIdTooLong() throws Exception {
        String longId = "a".repeat(65);
        String json = """
            {
              "customerId": "%s",
              "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]
            }
            """.formatted(longId);
        
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldReturn400WhenItemsIsEmpty() throws Exception {
        String json = """
            {
              "customerId": "c-1",
              "items": []
            }
            """;
        
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldReturn400WhenSkuIsEmpty() throws Exception {
        String json = """
            {
              "customerId": "c-1",
              "items": [{"sku": "", "quantity": 1, "unitPriceCents": 100}]
            }
            """;
        
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldReturn400WhenQuantityIsZero() throws Exception {
        String json = """
            {
              "customerId": "c-1",
              "items": [{"sku": "A-1", "quantity": 0, "unitPriceCents": 100}]
            }
            """;
        
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldReturn400WhenQuantityIs101() throws Exception {
        String json = """
            {
              "customerId": "c-1",
              "items": [{"sku": "A-1", "quantity": 101, "unitPriceCents": 100}]
            }
            """;
        
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldReturn400WhenUnitPriceCentsIsZero() throws Exception {
        String json = """
            {
              "customerId": "c-1",
              "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 0}]
            }
            """;
        
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldReturn400WhenUnitPriceCentsIsTooLarge() throws Exception {
        String json = """
            {
              "customerId": "c-1",
              "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 1000001}]
            }
            """;
        
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldReturn400WhenInvalidJSON() throws Exception {
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{ invalid json }"))
                .andExpect(status().isBadRequest());
    }
}
