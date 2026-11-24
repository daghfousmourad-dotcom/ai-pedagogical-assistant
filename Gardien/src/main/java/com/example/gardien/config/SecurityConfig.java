/*
 * ==============================================================================
 * PROPRIÉTÉ DE AI ASSISTANT - (c) 2024-2026 Mourad Daghfous
 * Système d'Interaction Vocale Intelligent pour l'Éducation
 * ------------------------------------------------------------------------------
 * Ce fichier est confidentiel et protégé par les lois sur la propriété
 * intellectuelle. Toute diffusion non autorisée est passible de poursuites.
 * ==============================================================================
 */
package com.example.gardien.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;
@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
                .csrf(csrf -> csrf.disable()) // Nouvelle syntaxe Lambda
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/auth/**").permitAll() // On laisse passer le login/register
                        .requestMatchers(org.springframework.http.HttpMethod.PATCH, "/api/courses/*/documents/*/metadata").permitAll()
                        .anyRequest().authenticated()
                );

        return http.build();
    }
}