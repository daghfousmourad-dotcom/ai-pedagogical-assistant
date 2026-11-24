package com.example.courseservice.controller;

import com.example.courseservice.service.CourseService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import java.util.Map;

@RestController
@RequestMapping("/api/admin/dashboard")
public class AdminController {

    @Autowired
    private CourseService courseService;

    @GetMapping("/stats")
    public ResponseEntity<Map<String, Object>> getStats(@RequestParam(required = false) String adminId) {
        return ResponseEntity.ok(Map.of(
                "totalFiles", courseService.getTotalFilesCount(adminId),
                "totalStorage", courseService.getTotalStorageBytes(adminId),
                "professorStats", courseService.getProfessorStats(adminId)));
    }

    @GetMapping("/storage")
    public ResponseEntity<Map<String, Object>> getStorage(@RequestParam(required = false) String adminId) {
        return ResponseEntity.ok(Map.of("success", true, "data", courseService.getTotalStorageBytes(adminId)));
    }

    @GetMapping("/files-count")
    public ResponseEntity<Map<String, Object>> getFilesCount(@RequestParam(required = false) String adminId) {
        return ResponseEntity.ok(Map.of("success", true, "data", courseService.getTotalFilesCount(adminId)));
    }

    @GetMapping("/professors-stats")
    public ResponseEntity<Map<String, Object>> getProfessorsStats(@RequestParam(required = false) String adminId) {
        return ResponseEntity.ok(Map.of("success", true, "data", courseService.getProfessorStats(adminId)));
    }

    @PostMapping("/maintenance/clean-orphans")
    public ResponseEntity<Map<String, Object>> cleanOrphans(@RequestParam(required = false) String adminId) {
        long count = courseService.cleanOrphanedFiles(adminId);
        return ResponseEntity.ok(Map.of("success", true, "message", "Nettoyage terminé", "count", count));
    }

    @PostMapping("/maintenance/clean-refs")
    public ResponseEntity<Map<String, Object>> cleanRefs(@RequestParam(required = false) String adminId) {
        long count = courseService.removeDeadReferences(adminId);
        return ResponseEntity.ok(Map.of("success", true, "message", "Références mortes supprimées", "count", count));
    }

    @PostMapping("/maintenance/sync-qdrant")
    public ResponseEntity<Map<String, Object>> syncQdrant(@RequestParam(required = false) String adminId) {
        long count = courseService.syncQdrantOrphans(adminId);
        return ResponseEntity.ok(Map.of("success", true, "message", "Synchronisation Qdrant terminée", "count", count));
    }

    @GetMapping("/maintenance/validate")
    public ResponseEntity<Map<String, Object>> validateDocs(@RequestParam(required = false) String adminId) {
        return ResponseEntity.ok(Map.of("success", true, "data", courseService.validateAllDocuments(adminId)));
    }

    @GetMapping("/global-stats")
    public ResponseEntity<Map<String, Object>> getGlobalStats() {
        return ResponseEntity.ok(Map.of("success", true, "data", courseService.getGlobalAdminStats()));
    }

    @PostMapping("/maintenance/total-system-cleanup")
    public ResponseEntity<Map<String, Object>> systemCleanup() {
        return ResponseEntity.ok(Map.of("success", true, "message", "Nettoyage global effectué", "data", courseService.performSystemWideCleanup()));
    }

    @PostMapping("/maintenance/repair-qdrant")
    public ResponseEntity<Map<String, Object>> repairQdrant() {
        return ResponseEntity.ok(courseService.hardRepairQdrant());
    }

    @DeleteMapping("/cleanup/professor/{id}")
    public ResponseEntity<Map<String, Object>> cleanupProfessor(@PathVariable String id) {
        courseService.deleteProfessorData(id);
        return ResponseEntity.ok(Map.of("success", true, "message", "Données du professeur supprimées"));
    }
}
