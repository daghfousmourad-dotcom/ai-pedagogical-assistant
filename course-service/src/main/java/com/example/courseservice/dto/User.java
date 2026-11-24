package com.example.courseservice.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/**
 * DTO représentant un utilisateur retourné par le service Gardien.
 * N'est PAS lié à MongoDB directement — utilisé uniquement pour désérialiser
 * les réponses REST du service d'identité.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public class User {
    private String id;
    private String email;
    private String fullName;
    private String role;
    private String parentAdminId;

    public User() {}

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
    public String getFullName() { return fullName; }
    public void setFullName(String fullName) { this.fullName = fullName; }
    public String getRole() { return role; }
    public void setRole(String role) { this.role = role; }
    public String getParentAdminId() { return parentAdminId; }
    public void setParentAdminId(String parentAdminId) { this.parentAdminId = parentAdminId; }
}
