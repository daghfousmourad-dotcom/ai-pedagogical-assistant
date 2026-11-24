package com.example.liveservice.websocket;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

@Component
public class LiveSessionHandler extends TextWebSocketHandler {

    private final ObjectMapper objectMapper = new ObjectMapper();
    private final HttpClient httpClient = HttpClient.newHttpClient();

    @Value("${fastapi.url:http://localhost:5005}")
    private String fastApiUrl;

    private String getPythonOrchestratorUrl() {
        return fastApiUrl + "/api/ai/orchestrate";
    }

    // Ensemble global de sessions (pour monitoring et fallback)
    private static final Map<String, WebSocketSession> allSessions = new ConcurrentHashMap<>();

    // Cloisonnement des sessions par salle de cours (ex: document ID / course ID)
    private static final Map<String, Set<WebSocketSession>> roomSessions = new ConcurrentHashMap<>();

    // Traçabilité session -> salle de cours
    private static final Map<String, String> sessionToRoomMap = new ConcurrentHashMap<>();

    @Override
    public void afterConnectionEstablished(WebSocketSession session) throws Exception {
        allSessions.put(session.getId(), session);
        System.out.println("🔌 WebSocket Java: Nouveau client connecté (" + session.getId() + ")");
    }

    /**
     * Enregistre un client dans une salle de cours spécifique.
     */
    private void joinRoom(WebSocketSession session, String roomId) {
        if (roomId == null || roomId.trim().isEmpty()) {
            return;
        }
        String oldRoom = sessionToRoomMap.get(session.getId());
        if (oldRoom != null && !oldRoom.equals(roomId)) {
            Set<WebSocketSession> oldSet = roomSessions.get(oldRoom);
            if (oldSet != null) {
                oldSet.remove(session);
                if (oldSet.isEmpty()) {
                    roomSessions.remove(oldRoom);
                }
            }
        }
        sessionToRoomMap.put(session.getId(), roomId);
        roomSessions.computeIfAbsent(roomId, k -> ConcurrentHashMap.newKeySet()).add(session);
        System.out.println("🏫 [WS Room] Client " + session.getId() + " a rejoint la salle : " + roomId);
    }

    @Override
    protected void handleTextMessage(WebSocketSession session, TextMessage message) throws Exception {
        String payload = message.getPayload();

        if (payload == null || payload.trim().isEmpty()) {
            return;
        }

        // On transforme le payload en Map pour s'assurer qu'il est valide
        Map<String, Object> msgData = objectMapper.readValue(payload, Map.class);
        String command = (String) msgData.get("command");

        // Identification de la salle de cours à partir du document ou de la commande
        String roomId = null;
        if (msgData.containsKey("mongo_file_id") && msgData.get("mongo_file_id") != null) {
            roomId = String.valueOf(msgData.get("mongo_file_id"));
        } else if (msgData.containsKey("room_id") && msgData.get("room_id") != null) {
            roomId = String.valueOf(msgData.get("room_id"));
        } else if (msgData.containsKey("course_id") && msgData.get("course_id") != null) {
            roomId = String.valueOf(msgData.get("course_id"));
        }

        if (roomId != null) {
            joinRoom(session, roomId);
        } else {
            // Récupérer la dernière salle connue pour cette session
            roomId = sessionToRoomMap.get(session.getId());
        }

        final String targetRoom = roomId;

        if ("CLARIFICATION_VALIDATED".equals(command) || "CLARIFICATION_CLOSED".equals(command)) {
            System.out.println("🎨 [LiveSession WS] Signal de clarification ('" + command + "') diffusé à la salle : " + targetRoom);
            broadcast(targetRoom, payload);
            return;
        }

        if ("SYNC".equals(command) || "NAVIGATE".equals(command)) {
            // Envoi asynchrone vers l'orchestrateur IA sans bloquer le thread WebSocket
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(getPythonOrchestratorUrl()))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(payload))
                    .build();

            httpClient.sendAsync(request, HttpResponse.BodyHandlers.ofString())
                    .thenAccept(response -> {
                        try {
                            if (response.statusCode() == 200) {
                                String aiBody = response.body();
                                if (aiBody != null && !aiBody.contains("IGNORE")) {
                                    broadcast(targetRoom, aiBody);
                                }
                            } else {
                                System.err.println("❌ Python Error " + response.statusCode() + ": " + response.body());
                            }
                        } catch (Exception e) {
                            System.err.println("❌ Erreur callback Java: " + e.getMessage());
                        }
                    });
        } else {
            // Autres commandes (NEXT, PREV manuel, JOIN) -> Diffusion ciblée dans la salle
            broadcast(targetRoom, payload);
        }
    }

    /**
     * Diffuse un message aux participants de la salle concernée (ou global en fallback).
     */
    private void broadcast(String roomId, String message) {
        TextMessage textMessage = new TextMessage(message);

        if (roomId != null && roomSessions.containsKey(roomId)) {
            Set<WebSocketSession> sessionsInRoom = roomSessions.get(roomId);
            sessionsInRoom.removeIf(s -> !s.isOpen());
            sessionsInRoom.forEach(s -> sendToSession(s, textMessage));
            System.out.println("📢 [Broadcast Room: " + roomId + "] Message diffusé à " + sessionsInRoom.size() + " participant(s)");
        } else {
            allSessions.values().removeIf(s -> !s.isOpen());
            allSessions.values().forEach(s -> sendToSession(s, textMessage));
            System.out.println("📢 [Broadcast Global] Message diffusé à " + allSessions.size() + " participant(s)");
        }
    }

    private void sendToSession(WebSocketSession session, TextMessage message) {
        try {
            if (session.isOpen()) {
                synchronized (session) {
                    session.sendMessage(message);
                }
            }
        } catch (Exception e) {
            System.err.println("❌ Erreur de transmission vers session " + session.getId() + ": " + e.getMessage());
        }
    }

    @Override
    public void handleTransportError(WebSocketSession session, Throwable exception) throws Exception {
        System.err.println("❌ [WS] Erreur de transport (" + session.getId() + "): " + exception.getMessage());
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) throws Exception {
        String sid = session.getId();
        allSessions.remove(sid);
        String roomId = sessionToRoomMap.remove(sid);
        if (roomId != null) {
            Set<WebSocketSession> set = roomSessions.get(roomId);
            if (set != null) {
                set.remove(session);
                if (set.isEmpty()) {
                    roomSessions.remove(roomId);
                }
            }
        }
        System.out.println("🔌 WebSocket Java: Client déconnecté (" + sid + ", salle: " + roomId + ")");
    }

    private void sendErrorMessage(WebSocketSession session, String text) throws Exception {
        Map<String, Object> error = Map.of(
                "type", "NAVIGATE_RESULT",
                "data", Map.of("action", "STAY", "text", text, "intent", "TEXT_QUERY"));
        session.sendMessage(new TextMessage(objectMapper.writeValueAsString(error)));
    }
}
