/*
 * ==============================================================================
 * PROPRIÉTÉ DE AI ASSISTANT - (c) 2024-2026 Mourad Daghfous
 * Système d'Interaction Vocale Intelligent pour l'Éducation
 * ------------------------------------------------------------------------------
 * Ce fichier est confidentiel et protégé par les lois sur la propriété 
 * intellectuelle. Toute diffusion non autorisée est passible de poursuites.
 * ==============================================================================
 */
package com.example.liveservice.service;

import com.example.liveservice.client.CourseServiceClient;
import com.example.liveservice.dto.DocumentMetadata;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.http.ResponseEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Service;
import org.springframework.http.ResponseEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.core.io.InputStreamResource;

import java.util.List;

/**
 * Service de session Live refactorisé pour une isolation complète des microservices.
 * N'accède plus jamais directement à la base MongoDB de course-service.
 * Toutes les données passent par l'API REST du CourseServiceClient.
 */
@Service
public class LiveSessionService {

    @Autowired
    private CourseServiceClient courseServiceClient;

    /**
     * Récupère les documents d'un cours via l'API REST du course-service.
     */
    public List<DocumentMetadata> getDocumentsByCourse(String courseId) {
        return courseServiceClient.getDocumentsByCourse(courseId);
    }

    /**
     * Stream le PDF d'un document via l'API REST du course-service.
     * Le live-service agit comme un proxy transparent.
     * Utilise HttpClient pour éviter la fermeture précoce du flux (problème avec RestTemplate.execute).
     */
    public ResponseEntity<InputStreamResource> getDocumentStream(String docId) {
        String streamUrl = courseServiceClient.getDocumentStreamUrl(docId);
        try {
            java.net.http.HttpClient client = java.net.http.HttpClient.newHttpClient();
            java.net.http.HttpRequest request = java.net.http.HttpRequest.newBuilder()
                    .uri(java.net.URI.create(streamUrl))
                    .GET()
                    .build();

            java.net.http.HttpResponse<java.io.InputStream> response = client.send(
                    request, java.net.http.HttpResponse.BodyHandlers.ofInputStream());

            if (response.statusCode() == 200) {
                HttpHeaders headers = new HttpHeaders();
                response.headers().firstValue("Content-Disposition")
                        .ifPresent(v -> headers.add("Content-Disposition", v));
                
                String contentType = response.headers().firstValue("Content-Type").orElse("application/pdf");

                return ResponseEntity.ok()
                        .headers(headers)
                        .contentType(org.springframework.http.MediaType.parseMediaType(contentType))
                        .body(new InputStreamResource(response.body()));
            } else {
                return ResponseEntity.status(response.statusCode()).build();
            }
        } catch (Exception e) {
            System.err.println("❌ [LiveSessionService] Erreur streaming document " + docId
                    + " depuis course-service : " + e.getMessage());
            return ResponseEntity.internalServerError().build();
        }
    }
}
