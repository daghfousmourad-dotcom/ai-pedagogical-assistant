package com.example.courseservice.repository;

import com.example.courseservice.dto.User;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.Query;
import java.util.List;

public interface UserRepository extends MongoRepository<User, String> {
    // Cette annotation n'aide pas à changer de base, on devra utiliser le template manuellement
    List<User> findByRole(String role);
}
