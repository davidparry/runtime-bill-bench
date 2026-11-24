package com.example.orderservice;

import com.example.orderservice.controller.OrdersController;
import com.example.orderservice.controller.OrdersController.CreateOrderRequest;
import com.example.orderservice.controller.OrdersController.CreateOrderRequest.OrderItemRequest;
import com.example.orderservice.service.OrderService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrdersControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private OrderService orderService;

    @Test
    void shouldCreateOrderSuccessfully() throws Exception {
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

        MvcResult result = mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isCreated())
                .andExpect(header().exists("Location"))
                .andExpect(jsonPath("$.customerId").value("c-1"))
                .andExpect(jsonPath("$.items[0].sku").value("A-1"))
                .andExpect(jsonPath("$.items[0].quantity").value(2))
                .andExpect(jsonPath("$.items[0].unitPriceCents").value(1250))
                .andExpect(jsonPath("$.totalCents").value(2500))
                .andExpect(jsonPath("$.createdAt").exists())
                .andReturn();

        String location = result.getResponse().getHeader("Location");
        assertThat(location).startsWith("/orders/");
    }

    @Test
    void shouldRejectOrderWithMissingCustomerId() throws Exception {
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
    void shouldRejectOrderWithInvalidQuantity() throws Exception {
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
    void shouldRejectOrderWithInvalidUnitPriceCents() throws Exception {
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
    void shouldReturn404ForNonExistentOrder() throws Exception {
        String nonExistentId = UUID.randomUUID().toString();

        mockMvc.perform(get("/orders/" + nonExistentId))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error").exists());
    }

    @Test
    void shouldReturn404ForInvalidIdFormat() throws Exception {
        String invalidId = "not-a-uuid";

        mockMvc.perform(get("/orders/" + invalidId))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").exists());
    }
    
    @Test
    void shouldIgnoreUnknownFields() throws Exception {
        String json = """
            {
                "customerId": "c-1",
                "items": [
                    {
                        "sku": "A-1",
                        "quantity": 1,
                        "unitPriceCents": 100,
                        "unknownField": "ignored"
                    }
                ],
                "unknownRootField": "ignored"
            }
            """;

        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isCreated());
    }
}
