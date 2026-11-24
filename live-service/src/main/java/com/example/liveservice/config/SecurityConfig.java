package com.example.liveservice.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;

/**
 * Le Course Service fait confiance à la Gateway pour la sécurité.
 * Toutes les requêtes qui passent par la Gateway sont déjà validées.
 * Ce service n'a pas besoin de valider le JWT à nouveau.
 */
@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
                .csrf(csrf -> csrf.disable())
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().permitAll()); // La Gateway gère la sécurité

        return http.build();
    }
}