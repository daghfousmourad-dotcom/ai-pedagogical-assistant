package com.example.courseservice.repository;

import com.example.courseservice.dto.DocumentMetadata;
import org.springframework.data.mongodb.repository.MongoRepository;
import java.util.List;

public interface DocumentRepository extends MongoRepository<DocumentMetadata, String> {
    List<DocumentMetadata> findByCourseId(String courseId);

    void deleteByCourseId(String courseId);

    long countByCourseId(String courseId);

    List<DocumentMetadata> findByCourseIdIn(List<String> courseIds);

    long countByCourseIdIn(List<String> courseIds);
}
