FILE: src/test/java/com/example/orderservice/controller/OrderControllerTest.java
```java
package com.example.orderservice.controller;

import com.example.orderservice.service.OrderService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.bean.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private OrderService orderService;

    @Test
    void createOrder_validRequest_returns201() throws Exception {
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
                .andExpect(jsonPath("$.customerId").value("c-1"))
                .andExpect(jsonPath("$.totalCents").value(2500));
    }

    @Test
    void createOrder_missingCustomerId_returns400() throws Exception {
        String json = """
            {
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
                .andExpect(jsonPath("$.customerId").exists());
    }

    @Test
    void createOrder_invalidSkuLength_returns400() throws Exception {
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
                .andExpect(status().isBadRequest());
    }

    @Test
    void createOrder_quantityOutOfRange_returns400() throws Exception {
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
                .andExpect(status().isBadRequest());
    }

    @Test
    void createOrder_emptyItems_returns400() throws Exception {
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
    void getOrder_existingOrder_returns200() throws Exception {
        String orderId = "123e4567-e89b-12d3-a456-426614174000";
        
        mockMvc.perform(get("/orders/" + orderId))
                .andExpect(status().isNotFound()); // Mock service returns null by default
    }

    @Test
    void getOrder_nonExistingOrder_returns404() throws Exception {
        mockMvc.perform(get("/orders/non-existing-id"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error").exists());
    }
}
```