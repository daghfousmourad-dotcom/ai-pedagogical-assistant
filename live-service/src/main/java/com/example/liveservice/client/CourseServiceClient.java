package com.example.liveservice.client;

import com.example.liveservice.dto.DocumentMetadata;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.ArrayList;
import java.util.List;

/**
 * Client REST pour communiquer avec le service de cours (CourseService).
 * Remplace l'accès direct à DocumentRepository et GridFsTemplate,
 * garantissant l'isolation complète de live-service.
 */
@Component
public class CourseServiceClient {

    @Value("${course.service.url:http://localhost:8082}")
    private String courseBaseUrl;

    private final HttpClient httpClient = HttpClient.newHttpClient();
    private final ObjectMapper objectMapper = new ObjectMapper();

    /**
     * Récupère les métadonnées d'un document par son ID.
     */
    public DocumentMetadata getDocumentMetadata(String docId) {
        String url = courseBaseUrl + "/api/courses/documents/" + docId + "/metadata";
        try {
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .GET()
                    .build();
            HttpResponse<String> response = httpClient.send(request,
                    HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() == 200) {
                JsonNode node = objectMapper.readTree(response.body());
                JsonNode data = node.get("data");
                if (data != null && !data.isNull()) {
                    return objectMapper.treeToValue(data, DocumentMetadata.class);
                }
            }
        } catch (Exception e) {
            System.err.println("❌ [CourseServiceClient] Erreur metadata pour " + docId + ": " + e.getMessage());
        }
        return null;
    }

    /**
     * Récupère tous les documents d'un cours.
     */
    public List<DocumentMetadata> getDocumentsByCourse(String courseId) {
        // Le course-service retourne les documents via GET /api/courses/{profId}/{courseId}/documents
        // Ici on utilise directement le courseId en GET paramètre
        String url = courseBaseUrl + "/api/courses/documents?courseId=" + courseId;
        try {
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .GET()
                    .build();
            HttpResponse<String> response = httpClient.send(request,
                    HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() == 200) {
                JsonNode node = objectMapper.readTree(response.body());
                JsonNode data = node.get("data");
                if (data != null && data.isArray()) {
                    List<DocumentMetadata> docs = new ArrayList<>();
                    for (JsonNode item : data) {
                        docs.add(objectMapper.treeToValue(item, DocumentMetadata.class));
                    }
                    return docs;
                }
            }
        } catch (Exception e) {
            System.err.println("❌ [CourseServiceClient] Erreur documents pour cours " + courseId + ": " + e.getMessage());
        }
        return List.of();
    }

    /**
     * Retourne l'URL de streaming du PDF (utilisé directement par le frontend ou via proxy).
     */
    public String getDocumentStreamUrl(String docId) {
        return courseBaseUrl + "/api/courses/documents/" + docId + "/stream";
    }
}
