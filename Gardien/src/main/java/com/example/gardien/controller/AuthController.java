/*
 * ==============================================================================
 * PROPRIÉTÉ DE AI Assistant - (c) 2024-2026 Mourad Daghfous
 * Système d'Interaction Vocale Intelligent pour l'Éducation
 * ------------------------------------------------------------------------------
 * Ce fichier est confidentiel et protégé par les lois sur la propriété 
 * intellectuelle. Toute diffusion non autorisée est passible de poursuites.
 * ==============================================================================
 */
package com.example.gardien.controller;

import com.example.gardien.dto.User;
import com.example.gardien.service.AuthService;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/auth")
public class AuthController {

    private final AuthService authService;

    public AuthController(AuthService authService) {
        this.authService = authService;
    }

    @PostMapping("/register")
    public User register(@RequestBody User user) {
        return authService.register(user);
    }

    @PostMapping("/login")
    public String login(@RequestBody Map<String, String> credentials) {
        return authService.login(credentials.get("email"), credentials.get("password"));
    }

    @GetMapping("/professors")
    public java.util.List<User> getAllProfessors(@RequestParam(required = false) String adminId) {
        if (adminId != null && !adminId.isEmpty()) {
            return authService.getAllUsersByRoleAndAdmin("PROFESSOR", adminId);
        }
        return authService.getAllUsersByRole("PROFESSOR");
    }

    @GetMapping("/admins")
    public java.util.List<User> getAllAdmins() {
        return authService.getAllUsersByRole("ADMIN");
    }

    @DeleteMapping("/professors/{id}")
    public org.springframework.http.ResponseEntity<String> deleteProfessor(@PathVariable String id) {
        authService.deleteUser(id);
        return org.springframework.http.ResponseEntity.ok("{\"success\":true,\"message\":\"Professeur supprimé\"}");
    }

    @DeleteMapping("/admins/{id}")
    public org.springframework.http.ResponseEntity<String> deleteAdmin(@PathVariable String id) {
        authService.deleteUser(id);
        return org.springframework.http.ResponseEntity.ok("{\"success\":true,\"message\":\"Administrateur et ses professeurs rattachés supprimés\"}");
    }

    @PutMapping("/users/{id}")
    public User updateProfile(@PathVariable String id, @RequestBody User user) {
        return authService.updateUser(id, user);
    }
}