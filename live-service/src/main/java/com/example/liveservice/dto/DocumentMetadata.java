package com.example.liveservice.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import java.time.LocalDateTime;

/**
 * DTO représentant les métadonnées d'un document.
 * Désérialisé depuis les réponses REST du course-service.
 * N'est PAS lié à MongoDB directement dans live-service.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public class DocumentMetadata {
    private String id;
    private String courseId;
    private String nom;
    private String gridfsId;
    private String status;
    private LocalDateTime dateAjout;

    public DocumentMetadata() {
    }

    public DocumentMetadata(String courseId, String nom, String gridfsId) {
        this.courseId = courseId;
        this.nom = nom;
        this.gridfsId = gridfsId;
        this.status = "READY"; // par défaut, ou INDEXING si on déclenche Python direct
        this.dateAjout = LocalDateTime.now();
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getCourseId() {
        return courseId;
    }

    public void setCourseId(String courseId) {
        this.courseId = courseId;
    }

    public String getNom() {
        return nom;
    }

    public void setNom(String nom) {
        this.nom = nom;
    }

    public String getGridfsId() {
        return gridfsId;
    }

    public void setGridfsId(String gridfsId) {
        this.gridfsId = gridfsId;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public LocalDateTime getDateAjout() {
        return dateAjout;
    }

    public void setDateAjout(LocalDateTime dateAjout) {
        this.dateAjout = dateAjout;
    }
}
