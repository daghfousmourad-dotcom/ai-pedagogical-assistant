package com.example.courseservice.config;

import com.example.courseservice.security.JwtRequestFilter;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

/**
 * Le Course Service fait confiance à la Gateway pour la sécurité.
 * Toutes les requêtes qui passent par la Gateway sont déjà validées.
 * Ce service n'a pas besoin de valider le JWT à nouveau.
 */
@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Autowired
    private JwtRequestFilter jwtRequestFilter;

    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
                .csrf(csrf -> csrf.disable())
                .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        // Endpoints internes pour les documents (accès inter-services sans JWT)
                        .requestMatchers(org.springframework.http.HttpMethod.GET, "/api/courses/documents/**").permitAll()
                        // Endpoint interne appelé par le worker Celery (sans JWT)
                        .requestMatchers(org.springframework.http.HttpMethod.PATCH,
                                "/api/courses/*/documents/*/metadata")
                        .permitAll()
                        .requestMatchers("/api/courses/**").authenticated()
                        .anyRequest().permitAll());

        http.addFilterBefore(jwtRequestFilter, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }
}