package com.example.courseservice.repository;

import com.example.courseservice.dto.Course;
import org.springframework.data.mongodb.repository.MongoRepository;
import java.util.List;

public interface CourseRepository extends MongoRepository<Course, String> {
    List<Course> findByProfesseurId(String professeurId);

    boolean existsByProfesseurIdAndTitre(String professeurId, String titre);

    Course findByProfesseurIdAndTitre(String professeurId, String titre);

    List<Course> findByProfesseurIdIn(List<String> professeurIds);
}
