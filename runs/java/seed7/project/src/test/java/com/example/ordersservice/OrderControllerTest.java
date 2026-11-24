package com.example.ordersservice;

import com.example.ordersservice.controller.OrderController;
import com.example.ordersservice.controller.OrderController.CreateOrderRequest;
import com.example.ordersservice.controller.OrderController.CreateOrderItemRequest;
import com.example.ordersservice.model.Order;
import com.example.ordersservice.service.OrderService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.util.Collections;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private OrderService orderService;

    @BeforeEach
    void setUp() {
        // Clear any existing orders from previous tests if necessary, 
        // though Spring Boot context usually restarts per test class or method depending on config.
        // For simplicity in this demo, we rely on fresh context or clear manually if needed.
        // Note: In a real app, we might use @DirtiesContext or clear the map in a @BeforeEach.
        // Here, we'll just assume clean state for the test methods.
    }

    @Test
    void createOrderSuccess() throws Exception {
        CreateOrderRequest request = new CreateOrderRequest();
        request.setCustomerId("c-1");
        
        CreateOrderItemRequest item = new CreateOrderItemRequest();
        item.setSku("A-1");
        item.setQuantity(2);
        item.setUnitPriceCents(1250);
        
        request.setItems(Collections.singletonList(item));

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
                .andExpect(jsonPath("$.items[0].sku").value("A-1"))
                .andExpect(jsonPath("$.items[0].quantity").value(2))
                .andExpect(jsonPath("$.items[0].unitPriceCents").value(1250))
                .andExpect(jsonPath("$.totalCents").value(2500))
                .andExpect(jsonPath("$.id").isNotEmpty())
                .andExpect(jsonPath("$.createdAt").isNotEmpty());
    }

    @Test
    void createOrderMissingCustomerId() throws Exception {
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
                .andExpect(jsonPath("$.error").exists());
    }

    @Test
    void createOrderEmptyItems() throws Exception {
        String json = """
            {
                "customerId": "c-1",
                "items": []
            }
            """;

        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").exists());
    }

    @Test
    void createOrderInvalidQuantity() throws Exception {
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
                .andExpect(jsonPath("$.error").exists());
    }

    @Test
    void createOrderInvalidUnitPriceCents() throws Exception {
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
                .andExpect(jsonPath("$.error").exists());
    }

    @Test
    void createOrderInvalidJson() throws Exception {
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{ invalid json }"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").exists());
    }

    @Test
    void getOrderSuccess() throws Exception {
        // Create an order first
        String createJson = """
            {
                "customerId": "c-2",
                "items": [
                    {
                        "sku": "B-2",
                        "quantity": 1,
                        "unitPriceCents": 500
                    }
                ]
            }
            """;

        MvcResult mvcResult = mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(createJson))
                .andExpect(status().isCreated())
                .andReturn();

        String orderId = mvcResult.getResponse().getHeader("Location").split("/")[2];

        mockMvc.perform(get("/orders/" + orderId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.customerId").value("c-2"))
                .andExpect(jsonPath("$.id").value(orderId));
    }

    @Test
    void getOrderNotFound() throws Exception {
        mockMvc.perform(get("/orders/non-existent-id"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error").exists());
    }

    @Test
    void healthCheck() throws Exception {
        mockMvc.perform(get("/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("ok"));
    }
}
