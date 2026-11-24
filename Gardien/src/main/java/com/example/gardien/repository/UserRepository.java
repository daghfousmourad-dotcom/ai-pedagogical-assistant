package com.example.gardien.repository;

import com.example.gardien.dto.User;
import org.springframework.data.mongodb.repository.MongoRepository;
import java.util.Optional;

public interface UserRepository extends MongoRepository<User, String> {
    Optional<User> findByEmail(String email);

    java.util.List<User> findAllByRole(String role);

    java.util.List<User> findAllByRoleAndParentAdminId(String role, String parentAdminId);

    java.util.List<User> findAllByParentAdminId(String parentAdminId);
}