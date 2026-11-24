package com.example.gardien.dto;

import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.SignatureAlgorithm;
import io.jsonwebtoken.security.Keys;
import org.springframework.stereotype.Component;

import java.util.Date;

@Component
public class JwtUtils {
    private String secretKey = "MaCleSecreteSuperDifficilePourLaRadiologie2026!";

    public String generateToken(String email, String role, String id, String parentAdminId) {
        return Jwts.builder()
                .setSubject(email)
                .claim("role", role)
                .claim("id", id)
                .claim("parentAdminId", parentAdminId)
                .setIssuedAt(new Date())
                .setExpiration(new Date(System.currentTimeMillis() + 86400000)) // 24 heures
                .signWith(Keys.hmacShaKeyFor(secretKey.getBytes()), SignatureAlgorithm.HS256)
                .compact();
    }
}
