package com.example.orderservice.controller;

import com.example.orderservice.model.CreateOrderRequest;
import com.example.orderservice.model.CreateOrderRequest.OrderItemRequest;
import com.example.orderservice.model.Order;
import com.example.orderservice.service.OrderService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.util.List;
import java.util.Map;

import static org.hamcrest.Matchers.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private OrderService orderService;

    @Test
    void createOrder_validRequest_returns201AndOrder() throws Exception {
        CreateOrderRequest request = new CreateOrderRequest();
        request.setCustomerId("c-1");
        OrderItemRequest item = new OrderItemRequest();
        item.setSku("A-1");
        item.setQuantity(2);
        item.setUnitPriceCents(1250);
        request.setItems(List.of(item));

        String json = """
                {
                  "customerId": "c-1",
                  "items": [
                    {
                      "sku": "A-1",
                      "quantity": 2,
                      "unitPriceCents": 1250
                    }
                  ]
                }
                """;

        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isCreated())
                .andExpect(header().exists("Location"))
                .andExpect(jsonPath("$.customerId", is("c-1")))
                .andExpect(jsonPath("$.items[0].sku", is("A-1")))
                .andExpect(jsonPath("$.items[0].quantity", is(2)))
                .andExpect(jsonPath("$.items[0].unitPriceCents", is(1250)))
                .andExpect(jsonPath("$.totalCents", is(2500)))
                .andExpect(jsonPath("$.createdAt").isNotEmpty());
    }

    @Test
    void createOrder_invalidCustomerId_returns400() throws Exception {
        String json = """
                {
                  "customerId": "",
                  "items": [
                    {
                      "sku": "A-1",
                      "quantity": 1,
                      "unitPriceCents": 100
                    }
                  ]
                }
                """;

        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").isNotEmpty());
    }

    @Test
    void createOrder_invalidQuantity_returns400() throws Exception {
        String json = """
                {
                  "customerId": "c-1",
                  "items": [
                    {
                      "sku": "A-1",
                      "quantity": 0,
                      "unitPriceCents": 100
                    }
                  ]
                }
                """;

        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").isNotEmpty());
    }

    @Test
    void createOrder_invalidSku_returns400() throws Exception {
        String json = """
                {
                  "customerId": "c-1",
                  "items": [
                    {
                      "sku": "",
                      "quantity": 1,
                      "unitPriceCents": 100
                    }
                  ]
                }
                """;

        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").isNotEmpty());
    }

    @Test
    void createOrder_invalidUnitPriceCents_returns400() throws Exception {
        String json = """
                {
                  "customerId": "c-1",
                  "items": [
                    {
                      "sku": "A-1",
                      "quantity": 1,
                      "unitPriceCents": 0
                    }
                  ]
                }
                """;

        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").isNotEmpty());
    }

    @Test
    void createOrder_tooManyItems_returns400() throws Exception {
        StringBuilder sb = new StringBuilder();
        sb.append("{\"customerId\":\"c-1\",\"items\":[");
        for (int i = 0; i < 51; i++) {
            if (i > 0) sb.append(",");
            sb.append("{\"sku\":\"A-\",\"quantity\":1,\"unitPriceCents\":1}");
        }
        sb.append("]}");

        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(sb.toString()))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").isNotEmpty());
    }

    @Test
    void createOrder_invalidJson_returns400() throws Exception {
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{ invalid json }"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").isNotEmpty());
    }

    @Test
    void getOrder_existingOrder_returns200() throws Exception {
        // First create an order
        String json = """
                {
                  "customerId": "c-1",
                  "items": [
                    {
                      "sku": "A-1",
                      "quantity": 1,
                      "unitPriceCents": 100
                    }
                  ]
                }
                """;

        MvcResult result = mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").isNotEmpty())
                .andReturn();

        String orderId = result.getResponse().getContentAsString();
        // Extract ID from JSON body
        String id = com.jayway.jsonpath.JsonPath.read(result.getResponse().getContentAsString(), "$.id");

        mockMvc.perform(get("/orders/" + id))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id", is(id)))
                .andExpect(jsonPath("$.customerId", is("c-1")));
    }

    @Test
    void getOrder_nonExistentOrder_returns404() throws Exception {
        mockMvc.perform(get("/orders/non-existent-id"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error").isNotEmpty());
    }

    @Test
    void health_check_returns200() throws Exception {
        mockMvc.perform(get("/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status", is("ok")));
    }
}
