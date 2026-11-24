package com.example.liveservice.dto;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

import java.time.LocalDateTime;

@Document(collection = "courses")
public class Course {
    @Id
    private String id;
    private String titre;
    @Field("professeur_id")
    private String professeurId; // ID venant du service Gardien
    @Field("created_at")
    private java.time.LocalDateTime createdAt;

    @org.springframework.data.annotation.Transient
    private long docCount;

    public Course() {
    }

    public Course(String titre, String professeurId) {
        this.titre = titre;
        this.professeurId = professeurId;
        this.createdAt = java.time.LocalDateTime.now();
    }

    public long getDocCount() {
        return docCount;
    }

    public void setDocCount(long docCount) {
        this.docCount = docCount;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getTitre() {
        return titre;
    }

    public void setTitre(String titre) {
        this.titre = titre;
    }

    public String getProfesseurId() {
        return professeurId;
    }

    public void setProfesseurId(String professeurId) {
        this.professeurId = professeurId;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(LocalDateTime createdAt) {
        this.createdAt = createdAt;
    }
}
