/*
 * ==============================================================================
 * PROPRIÉTÉ DE AI ASSISTANT - (c) 2024-2026 Mourad Daghfous
 * Système d'Interaction Vocale Intelligent pour l'Éducation
 * ------------------------------------------------------------------------------
 * Ce fichier est confidentiel et protégé par les lois sur la propriété
 * intellectuelle. Toute diffusion non autorisée est passible de poursuites.
 * ==============================================================================
 */
package com.example.courseservice.client;

import com.example.courseservice.dto.User;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.Collections;
import java.util.List;

/**
 * Client REST pour communiquer avec le service d'identité (Gardien).
 * Remplace l'accès direct à identityMongoTemplate pour garantir
 * l'isolation complète des bases de données.
 */
@Component
public class GardienClient {

    @Value("${gardien.service.url:http://localhost:8081}")
    private String gardienBaseUrl;

    private final HttpClient httpClient = HttpClient.newHttpClient();
    private final ObjectMapper objectMapper = new ObjectMapper();

    /**
     * Récupère tous les professeurs d'un admin donné.
     */
    public List<User> getProfessors(String adminId) {
        String url = gardienBaseUrl + "/auth/professors";
        if (adminId != null && !adminId.isEmpty()) {
            url += "?adminId=" + adminId;
        }
        return fetchUsers(url);
    }

    /**
     * Récupère tous les administrateurs du système.
     */
    public List<User> getAdmins() {
        return fetchUsers(gardienBaseUrl + "/auth/admins");
    }

    /**
     * Récupère tous les IDs de professeurs appartenant à un admin.
     */
    public List<String> getProfessorIds(String adminId) {
        return getProfessors(adminId).stream()
                .map(User::getId)
                .filter(id -> id != null && !id.isEmpty())
                .collect(java.util.stream.Collectors.toList());
    }

    private List<User> fetchUsers(String url) {
        try {
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .header("Content-Type", "application/json")
                    .GET()
                    .build();

            HttpResponse<String> response = httpClient.send(request,
                    HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() == 200) {
                return objectMapper.readValue(response.body(),
                        new TypeReference<List<User>>() {});
            } else {
                System.err.println("⚠️ [GardienClient] Erreur HTTP " +
                        response.statusCode() + " sur " + url);
            }
        } catch (Exception e) {
            System.err.println("❌ [GardienClient] Impossible de joindre Gardien sur " +
                    url + " : " + e.getMessage());
        }
        // Retourne une liste vide en cas d'erreur (fail-safe)
        return Collections.emptyList();
    }
}
