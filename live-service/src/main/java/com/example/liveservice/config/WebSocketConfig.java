package com.example.liveservice.config;

import com.example.liveservice.websocket.LiveSessionHandler;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration
@EnableWebSocket
public class WebSocketConfig implements WebSocketConfigurer {

    private final LiveSessionHandler liveSessionHandler;

    public WebSocketConfig(LiveSessionHandler liveSessionHandler) {
        this.liveSessionHandler = liveSessionHandler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(liveSessionHandler, "/ws/navigation")
                .setAllowedOrigins("*");
    }
}
