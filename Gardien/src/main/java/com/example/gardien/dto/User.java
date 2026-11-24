package com.example.gardien.dto;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "users")
public class User {
    @Id
    private String id;
    private String email;
    private String password;
    private String fullName;
    private String role;
    private String parentAdminId; // ID de l'établissement (Admin créateur)
    private java.util.Date createdAt;

    public User() {
        this.createdAt = new java.util.Date();
    }

    public User(String id, String email, String password, String fullName, String role, String parentAdminId) {
        this.id = id;
        this.email = email;
        this.password = password;
        this.fullName = fullName;
        this.role = role;
        this.parentAdminId = parentAdminId;
        this.createdAt = new java.util.Date();
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public String getPassword() {
        return password;
    }

    public void setPassword(String password) {
        this.password = password;
    }

    public String getRole() {
        return role;
    }

    public void setRole(String role) {
        this.role = role;
    }

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }

    public String getParentAdminId() {
        return parentAdminId;
    }

    public void setParentAdminId(String parentAdminId) {
        this.parentAdminId = parentAdminId;
    }

    public java.util.Date getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(java.util.Date createdAt) {
        this.createdAt = createdAt;
    }
}
