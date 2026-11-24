package com.example.liveservice.repository;

import com.example.liveservice.dto.DocumentMetadata;
import org.springframework.data.mongodb.repository.MongoRepository;
import java.util.List;

public interface DocumentRepository extends MongoRepository<DocumentMetadata, String> {
    List<DocumentMetadata> findByCourseId(String courseId);

    void deleteByCourseId(String courseId);

    long countByCourseId(String courseId);
}
