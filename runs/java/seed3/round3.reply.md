FILE: src/test/java/com/example/orderservice/OrderControllerTest.java
```java
package com.example.orderservice;

import com.example.orderservice.model.OrderRequest;
import com.example.orderservice.model.OrderItem;
import com.example.orderservice.model.OrderResponse;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
class OrderControllerTest {

    @Autowired
    private WebApplicationContext context;

    private MockMvc mockMvc;

    @org.junit.jupiter.api.BeforeEach
    void setUp() {
        this.mockMvc = MockMvcBuilders.webAppContextSetup(context).build();
    }

    private String toJson(Object obj) throws Exception {
        return new ObjectMapper().writeValueAsString(obj);
    }

    @Test
    void createOrderSuccess() throws Exception {
        OrderItem item = new OrderItem();
        item.setSku("A-1");
        item.setQuantity(2);
        item.setUnitPriceCents(1250L);

        OrderRequest request = new OrderRequest();
        request.setCustomerId("c-1");
        request.setItems(List.of(item));

        mockMvc.perform(post("/orders")
                .contentType("application/json")
                .content(toJson(request)))
                .andExpect(status().isCreated())
                .andExpect(header().exists("Location"))
                .andExpect(jsonPath("$.customerId").value("c-1"))
                .andExpect(jsonPath("$.items[0].sku").value("A-1"))
                .andExpect(jsonPath("$.totalCents").value(2500));
    }

    @Test
    void createOrderInvalidCustomerId() throws Exception {
        OrderItem item = new OrderItem();
        item.setSku("A-1");
        item.setQuantity(2);
        item.setUnitPriceCents(1250L);

        OrderRequest request = new OrderRequest();
        request.setCustomerId("");
        request.setItems(List.of(item));

        mockMvc.perform(post("/orders")
                .contentType("application/json")
                .content(toJson(request)))
                .andExpect(status().isBadRequest());
    }

    @Test
    void createOrderInvalidQuantity() throws Exception {
        OrderItem item = new OrderItem();
        item.setSku("A-1");
        item.setQuantity(0);
        item.setUnitPriceCents(1250L);

        OrderRequest request = new OrderRequest();
        request.setCustomerId("c-1");
        request.setItems(List.of(item));

        mockMvc.perform(post("/orders")
                .contentType("application/json")
                .content(toJson(request)))
                .andExpect(status().isBadRequest());
    }

    @Test
    void createOrderInvalidUnitPrice() throws Exception {
        OrderItem item = new OrderItem();
        item.setSku("A-1");
        item.setQuantity(2);
        item.setUnitPriceCents(0L);

        OrderRequest request = new OrderRequest();
        request.setCustomerId("c-1");
        request.setItems(List.of(item));

        mockMvc.perform(post("/orders")
                .contentType("application/json")
                .content(toJson(request)))
                .andExpect(status().isBadRequest());
    }

    @Test
    void createOrderInvalidJson() throws Exception {
        mockMvc.perform(post("/orders")
                .contentType("application/json")
                .content("{ invalid json }"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void getOrderSuccess() throws Exception {
        OrderItem item = new OrderItem();
        item.setSku("A-1");
        item.setQuantity(2);
        item.setUnitPriceCents(1250L);

        OrderRequest request = new OrderRequest();
        request.setCustomerId("c-1");
        request.setItems(List.of(item));

        MvcResult result = mockMvc.perform(post("/orders")
                .contentType("application/json")
                .content(toJson(request)))
                .andExpect(status().isCreated())
                .andReturn();

        String location = result.getResponse().getHeader("Location");
        String orderId = location.substring(location.lastIndexOf('/') + 1);

        mockMvc.perform(get("/orders/" + orderId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(orderId));
    }

    @Test
    void getOrderNotFound() throws Exception {
        mockMvc.perform(get("/orders/non-existent-id"))
                .andExpect(status().isNotFound());
    }

    @Test
    void healthCheck() throws Exception {
        mockMvc.perform(get("/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("ok"));
    }
}
```