package com.example.courseservice.controller;

import com.example.courseservice.dto.ApiResponse;
import com.example.courseservice.dto.Course;
import com.example.courseservice.dto.DocumentMetadata;
import com.example.courseservice.service.CourseService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/courses")
public class CourseController {

    @Autowired
    private CourseService courseService;

    @PostMapping("/{profId}/create")
    public ResponseEntity<ApiResponse> createCourse(Authentication authentication, @PathVariable String profId,
            @RequestParam String title) {
        String authenticatedProfId = (String) authentication.getPrincipal();
        // On utilise l'ID du JWT pour la création, ignorant celui de l'URL si différent
        return ResponseEntity
                .ok(new ApiResponse(true, "Cours créé", courseService.createCourse(authenticatedProfId, title)));
    }

    @GetMapping("/{profId}")
    public ResponseEntity<ApiResponse> getCourses(Authentication authentication, @PathVariable String profId) {
        String authenticatedProfId = (String) authentication.getPrincipal();
        // On récupère les cours de l'utilisateur authentifié
        return ResponseEntity
                .ok(new ApiResponse(true, "Cours récupérés", courseService.getAllCourses(authenticatedProfId)));
    }

    @GetMapping("/{profId}/{courseId}")
    public ResponseEntity<ApiResponse> getCourseById(Authentication authentication, @PathVariable String profId,
            @PathVariable String courseId) {
        String authenticatedProfId = (String) authentication.getPrincipal();
        Course course = courseService.getCourseById(courseId);
        if (course != null && course.getProfesseurId().equals(authenticatedProfId)) {
            return ResponseEntity.ok(new ApiResponse(true, "Cours trouvé", course));
        }
        return ResponseEntity.status(403).body(new ApiResponse(false, "Accès refusé ou non trouvé", null));
    }

    @DeleteMapping("/{profId}/{courseId}")
    public ResponseEntity<ApiResponse> deleteCourse(Authentication authentication, @PathVariable String profId,
            @PathVariable String courseId) {
        String authenticatedProfId = (String) authentication.getPrincipal();
        // On vérifie la suppression via l'ID authentifié
        courseService.deleteCourse(authenticatedProfId, courseId);
        return ResponseEntity.ok(new ApiResponse(true, "Cours supprimé", null));
    }

    @PostMapping(value = "/{profId}/upload", params = "courseTitle")
    public ResponseEntity<ApiResponse> uploadDocument(
            Authentication authentication,
            @PathVariable String profId,
            @RequestParam String courseTitle,
            @RequestParam(value = "method", defaultValue = "1") int method,
            @RequestParam("file") MultipartFile file) {
        String authenticatedProfId = (String) authentication.getPrincipal();
        return courseService.uploadDocument(authenticatedProfId, courseTitle, method, file);
    }

    @PostMapping(value = "/{courseId}/upload", params = "!courseTitle")
    public ResponseEntity<ApiResponse> uploadDocumentById(
            @PathVariable String courseId,
            @RequestParam(value = "method", defaultValue = "1") int method,
            @RequestParam("file") MultipartFile file) {
        return courseService.uploadDocumentById(courseId, method, file);
    }

    @PutMapping("/{profId}/{courseId}")
    public ResponseEntity<ApiResponse> updateCourseTitle(
            Authentication authentication,
            @PathVariable String profId,
            @PathVariable String courseId,
            @RequestBody Map<String, String> request) {
        String authenticatedProfId = (String) authentication.getPrincipal();
        Course course = courseService.updateCourseTitle(authenticatedProfId, courseId, request.get("title"));
        if (course != null) {
            return ResponseEntity.ok(new ApiResponse(true, "Cours mis à jour", course));
        }
        return ResponseEntity.status(404).body(new ApiResponse(false, "Cours non trouvé", null));
    }


    @GetMapping("/{profId}/{courseId}/documents")
    public ResponseEntity<ApiResponse> getCourseDocuments(
            Authentication authentication,
            @PathVariable String profId,
            @PathVariable String courseId) {
        // Liste les documents du cours (la vérification d'accès au cours peut être
        // faite si nécessaire)
        return ResponseEntity.ok(new ApiResponse(true, "Documents", courseService.getDocumentsByCourse(courseId)));
    }

    @DeleteMapping("/{profId}/documents/{docId}")
    public ResponseEntity<ApiResponse> deleteDocument(
            Authentication authentication,
            @PathVariable String profId,
            @PathVariable String docId) {
        // Suppression via service
        courseService.deleteDocument(docId);
        return ResponseEntity.ok(new ApiResponse(true, "Document supprimé", null));
    }

    @PutMapping("/{profId}/documents/{docId}/rename")
    public ResponseEntity<ApiResponse> renameDocument(
            Authentication authentication,
            @PathVariable String profId,
            @PathVariable String docId,
            @RequestBody Map<String, String> request) {
        String authenticatedProfId = (String) authentication.getPrincipal();
        boolean success = courseService.renameDocument(authenticatedProfId, docId, request.get("newName"));
        if (success) {
            return ResponseEntity.ok(new ApiResponse(true, "Document renommé", null));
        }
        return ResponseEntity.status(404).body(new ApiResponse(false, "Document non trouvé", null));
    }

    @PatchMapping("/{courseId}/documents/{docId}/metadata")
    public ResponseEntity<ApiResponse> updateDocumentMetadata(
            Authentication authentication,
            @PathVariable String courseId,
            @PathVariable String docId,
            @RequestBody Map<String, Object> request) {
        String context = (String) request.get("courseContext");
        String role = (String) request.get("systemRole");
        @SuppressWarnings("unchecked")
        List<String> sources = (List<String>) request.get("customSources");

        DocumentMetadata doc = courseService.updateDocumentMetadata(docId, context, role, sources);
        if (doc != null) {
            return ResponseEntity.ok(new ApiResponse(true, "Métadonnées du document mises à jour", doc));
        }
        return ResponseEntity.status(404).body(new ApiResponse(false, "Document non trouvé", null));
    }

    /**
     * Endpoint interne : Retourne les métadonnées d'un document par son ID.
     * Utilisé par le live-service pour éviter tout accès direct à la base de données.
     */
    @GetMapping("/documents/{docId}/metadata")
    public ResponseEntity<ApiResponse> getDocumentMetadata(@PathVariable String docId) {
        DocumentMetadata doc = courseService.getDocumentMetadataById(docId);
        if (doc != null) {
            return ResponseEntity.ok(new ApiResponse(true, "Métadonnées trouvées", doc));
        }
        return ResponseEntity.status(404).body(new ApiResponse(false, "Document non trouvé", null));
    }

    /**
     * Endpoint interne : Stream le PDF d'un document directement depuis GridFS.
     * Utilisé par le live-service pour afficher les PDFs sans accès direct à MongoDB.
     */
    @GetMapping("/documents/{docId}/stream")
    public ResponseEntity<org.springframework.core.io.InputStreamResource> streamDocument(@PathVariable String docId) {
        return courseService.streamDocument(docId);
    }
}
