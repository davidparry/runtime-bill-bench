package com.example.orderservice;

import com.example.orderservice.controller.OrderController;
import com.example.orderservice.service.OrderService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderControllerValidationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void shouldRejectMissingCustomerId() throws Exception {
        String json = "{\"items\": [{\"sku\": \"A-1\", \"quantity\": 1, \"unitPriceCents\": 100}]}";
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldRejectEmptyCustomerId() throws Exception {
        String json = "{\"customerId\": \"\", \"items\": [{\"sku\": \"A-1\", \"quantity\": 1, \"unitPriceCents\": 100}]}";
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldRejectLongCustomerId() throws Exception {
        String longId = "a".repeat(65);
        String json = "{\"customerId\": \"" + longId + "\", \"items\": [{\"sku\": \"A-1\", \"quantity\": 1, \"unitPriceCents\": 100}]}";
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldRejectMissingItems() throws Exception {
        String json = "{\"customerId\": \"c-1\"}";
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldRejectEmptyItems() throws Exception {
        String json = "{\"customerId\": \"c-1\", \"items\": []}";
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldRejectTooManyItems() throws Exception {
        StringBuilder json = new StringBuilder("{\"customerId\": \"c-1\", \"items\": [");
        for (int i = 0; i < 51; i++) {
            if (i > 0) json.append(",");
            json.append("{\"sku\": \"A-1\", \"quantity\": 1, \"unitPriceCents\": 100}");
        }
        json.append("]}");
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json.toString()))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldRejectInvalidSku() throws Exception {
        String json = "{\"customerId\": \"c-1\", \"items\": [{\"sku\": \"\", \"quantity\": 1, \"unitPriceCents\": 100}]}";
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldRejectSkuTooLong() throws Exception {
        String longSku = "a".repeat(33);
        String json = "{\"customerId\": \"c-1\", \"items\": [{\"sku\": \"" + longSku + "\", \"quantity\": 1, \"unitPriceCents\": 100}]}";
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldRejectMissingQuantity() throws Exception {
        String json = "{\"customerId\": \"c-1\", \"items\": [{\"sku\": \"A-1\", \"unitPriceCents\": 100}]}";
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldRejectQuantityTooSmall() throws Exception {
        String json = "{\"customerId\": \"c-1\", \"items\": [{\"sku\": \"A-1\", \"quantity\": 0, \"unitPriceCents\": 100}]}";
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldRejectQuantityTooLarge() throws Exception {
        String json = "{\"customerId\": \"c-1\", \"items\": [{\"sku\": \"A-1\", \"quantity\": 101, \"unitPriceCents\": 100}]}";
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldRejectMissingUnitPriceCents() throws Exception {
        String json = "{\"customerId\": \"c-1\", \"items\": [{\"sku\": \"A-1\", \"quantity\": 1}]}";
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldRejectZeroUnitPriceCents() throws Exception {
        String json = "{\"customerId\": \"c-1\", \"items\": [{\"sku\": \"A-1\", \"quantity\": 1, \"unitPriceCents\": 0}]}";
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldRejectUnitPriceCentsTooLarge() throws Exception {
        String json = "{\"customerId\": \"c-1\", \"items\": [{\"sku\": \"A-1\", \"quantity\": 1, \"unitPriceCents\": 1000001}]}";
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldRejectInvalidJson() throws Exception {
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{invalid json}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void shouldRejectMissingFieldsInItem() throws Exception {
        String json = "{\"customerId\": \"c-1\", \"items\": [{\"sku\": \"A-1\"}]}";
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isBadRequest());
    }
}
