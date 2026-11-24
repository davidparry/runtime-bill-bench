package com.example.orderservice.config;

import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpServletResponseWrapper;

public class HttpServletResponseWrapper extends HttpServletResponseWrapper {

    private int status = HttpServletResponse.SC_OK;

    public HttpServletResponseWrapper(HttpServletResponse response) {
        super(response);
    }

    @Override
    public void setStatus(int sc) {
        super.setStatus(sc);
        this.status = sc;
    }

    @Override
    public int getStatus() {
        return this.status;
    }
}
