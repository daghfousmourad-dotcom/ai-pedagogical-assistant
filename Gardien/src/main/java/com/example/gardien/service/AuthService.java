/*
 * ==============================================================================
 * PROPRIÉTÉ DE AI ASSISTANT - (c) 2024-2026 Mourad Daghfous
 * Système d'Interaction Vocale Intelligent pour l'Éducation
 * ------------------------------------------------------------------------------
 * Ce fichier est confidentiel et protégé par les lois sur la propriété
 * intellectuelle. Toute diffusion non autorisée est passible de poursuites.
 * ==============================================================================
 */
package com.example.gardien.service;

import com.example.gardien.dto.JwtUtils;
import com.example.gardien.dto.User;
import com.example.gardien.repository.UserRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;

@Service
public class AuthService {

    private final UserRepository userRepository;
    private final JwtUtils jwtUtils;
    private final BCryptPasswordEncoder passwordEncoder = new BCryptPasswordEncoder();

    public AuthService(UserRepository userRepository, JwtUtils jwtUtils) {
        this.userRepository = userRepository;
        this.jwtUtils = jwtUtils;
    }

    // Inscription : Hachage du mot de passe + Enregistrement
    public User register(User user) {
        user.setPassword(passwordEncoder.encode(user.getPassword()));
        return userRepository.save(user);
    }

    // Connexion : Vérification + Signature du Badge JWT
    public String login(String email, String password) {
        System.out.println("DEBUG: Login attempt for: [" + email + "]");
        System.out.println("DEBUG: Provided password: [" + password + "]");
        User user = userRepository.findByEmail(email)
                .orElseThrow(() -> new RuntimeException("Utilisateur non trouvé"));

        System.out.println("DEBUG: Stored hash: [" + user.getPassword() + "]");

        if (passwordEncoder.matches(password, user.getPassword())) {
            return jwtUtils.generateToken(user.getEmail(), user.getRole(), user.getId(), user.getParentAdminId());
        } else {
            throw new RuntimeException("Mot de passe incorrect");
        }
    }

    public java.util.List<User> getAllUsersByRole(String role) {
        return userRepository.findAllByRole(role);
    }

    public java.util.List<User> getAllUsersByRoleAndAdmin(String role, String adminId) {
        return userRepository.findAllByRoleAndParentAdminId(role, adminId);
    }

    public User updateUser(String id, User updatedUser) {
        User existingUser = userRepository.findById(id)
                .orElseThrow(() -> new RuntimeException("Utilisateur non trouvé"));

        if (updatedUser.getFullName() != null) {
            existingUser.setFullName(updatedUser.getFullName());
        }
        if (updatedUser.getEmail() != null) {
            existingUser.setEmail(updatedUser.getEmail());
        }
        if (updatedUser.getPassword() != null && !updatedUser.getPassword().isEmpty()) {
            existingUser.setPassword(passwordEncoder.encode(updatedUser.getPassword()));
        }

        return userRepository.save(existingUser);
    }

    private final java.net.http.HttpClient httpClient = java.net.http.HttpClient.newHttpClient();

    @org.springframework.beans.factory.annotation.Value("${course.service.url:http://localhost:8082}")
    private String courseServiceUrl;

    private String getCourseServiceCleanupUrl() {
        return courseServiceUrl + "/api/admin/dashboard/cleanup/professor/";
    }

    public void deleteUser(String id) {
        User user = userRepository.findById(id)
                .orElseThrow(() -> new RuntimeException("Utilisateur non trouvé"));

        if ("ADMIN".equals(user.getRole())) {
            // Suppression en cascade de tous les professeurs rattachés
            java.util.List<User> subordinates = userRepository.findAllByParentAdminId(id);
            System.out.println("⚠️ Suppression CASCADE de l'admin: " + id + " (" + subordinates.size() + " subordonnés)");
            for (User sub : subordinates) {
                deleteUser(sub.getId()); // Appel récursif pour chaque sous-utilisateur (professeur)
            }
        } else if ("PROFESSOR".equals(user.getRole())) {
            // Déclencher le nettoyage en cascade (Cours + GridFS + Qdrant) dans le service métier
            try {
                java.net.http.HttpRequest request = java.net.http.HttpRequest.newBuilder()
                        .uri(java.net.URI.create(getCourseServiceCleanupUrl() + id))
                        .DELETE()
                        .build();
                httpClient.send(request, java.net.http.HttpResponse.BodyHandlers.ofString());
                System.out.println("🔄 Cleanup cascade envoyé pour le prof: " + id);
            } catch (Exception e) {
                System.err.println("⚠️ Échec du nettoyage cascade (procéder quand même): " + e.getMessage());
            }
        }

        // 2. Supprimer l'utilisateur lui-même de la base d'identité
        userRepository.deleteById(id);
    }

    @Bean
    public BCryptPasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }
}
