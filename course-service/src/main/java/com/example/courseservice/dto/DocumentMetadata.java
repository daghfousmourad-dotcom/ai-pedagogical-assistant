package com.example.courseservice.dto;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import java.time.LocalDateTime;

@Document(collection = "documents")
public class DocumentMetadata {
    @Id
    private String id;
    @Field("course_id")
    private String courseId; // Lien vers la collection courses
    private String nom;
    @Field("gridfs_id")
    private String gridfsId; // ID du fichier physique dans GridFS
    private String status; // INDEXING, READY, ERROR
    @Field("date_ajout")
    private LocalDateTime dateAjout;

    @Field("course_context")
    private String courseContext;

    @Field("system_role")
    private String systemRole;

    @Field("custom_sources")
    private java.util.List<String> customSources;

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

    public String getCourseContext() {
        return courseContext;
    }

    public void setCourseContext(String courseContext) {
        this.courseContext = courseContext;
    }

    public String getSystemRole() {
        return systemRole;
    }

    public void setSystemRole(String systemRole) {
        this.systemRole = systemRole;
    }

    public java.util.List<String> getCustomSources() {
        return customSources;
    }

    public void setCustomSources(java.util.List<String> customSources) {
        this.customSources = customSources;
    }
}
