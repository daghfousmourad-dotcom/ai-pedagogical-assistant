/*
 * ==============================================================================
 * PROPRIÉTÉ DE AI ASSISTANT - (c) 2024-2026 Mourad Daghfous
 * Système d'Interaction Vocale Intelligent pour l'Éducation
 * ------------------------------------------------------------------------------
 * Ce fichier est confidentiel et protégé par les lois sur la propriété 
 * intellectuelle. Toute diffusion non autorisée est passible de poursuites.
 * ==============================================================================
 */
package com.example.courseservice.service;

import com.example.courseservice.client.GardienClient;
import com.example.courseservice.dto.ApiResponse;
import com.example.courseservice.dto.Course;
import com.example.courseservice.dto.DocumentMetadata;
import com.example.courseservice.dto.User;
import com.example.courseservice.repository.CourseRepository;
import com.example.courseservice.repository.DocumentRepository;
import org.bson.types.ObjectId;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.mongodb.core.aggregation.*;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.gridfs.GridFsTemplate;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.http.ResponseEntity;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.URI;
import java.util.*;
import java.util.stream.Collectors;

@Service
public class CourseService {

    @Autowired
    private CourseRepository courseRepository;

    @Autowired
    private org.springframework.data.mongodb.core.MongoTemplate mongoTemplate;

    @Autowired
    private DocumentRepository documentRepository;

    @Autowired
    private GardienClient gardienClient;

    @Autowired
    private GridFsTemplate gridFsTemplate;

    @org.springframework.beans.factory.annotation.Value("${shared.uploads.path}")
    private String SHARED_UPLOADS_HOST;

    @org.springframework.beans.factory.annotation.Value("${fastapi.url:http://localhost:5005}")
    private String fastApiUrl;

    private String getArchivisteUrl() {
        return fastApiUrl + "/api/ai/upload-pdf";
    }

    private String getAiCleanupUrl() {
        return fastApiUrl + "/api/ai/documents/";
    }

    private final HttpClient httpClient = HttpClient.newHttpClient();

    public Course createCourse(String profId, String title) {
        Course course;
        if (!courseRepository.existsByProfesseurIdAndTitre(profId, title)) {
            course = new Course(title, profId);
            course = courseRepository.save(course);
        } else {
            course = courseRepository.findByProfesseurIdAndTitre(profId, title);
        }
        if (course != null) {
            course.setDocCount(documentRepository.countByCourseId(course.getId()));
        }
        return course;
    }

    public List<Course> getAllCourses(String profId) {
        List<Course> courses = courseRepository.findByProfesseurId(profId);
        courses.forEach(c -> {
            List<DocumentMetadata> docs = documentRepository.findByCourseId(c.getId());
            c.setDocuments(docs);
            c.setDocCount(docs.size());
        });
        return courses;
    }

    public void deleteCourse(String profId, String courseId) {
        // Supprimer d'abord les documents locaux (GridFS + Docs) = Logique extraite
        List<DocumentMetadata> docs = documentRepository.findByCourseId(courseId);
        for (DocumentMetadata doc : docs) {
            deleteDocument(doc.getId());
        }
        courseRepository.deleteById(courseId);
    }

    public Course updateCourseTitle(String profId, String courseId, String newTitle) {
        Course course = courseRepository.findById(courseId).orElse(null);
        if (course != null && course.getProfesseurId().equals(profId)) {
            course.setTitre(newTitle);
            course = courseRepository.save(course);
            course.setDocCount(documentRepository.countByCourseId(course.getId()));
            return course;
        }
        return null;
    }


    public Course getCourseById(String courseId) {
        Course course = courseRepository.findById(courseId).orElse(null);
        if (course != null) {
            course.setDocuments(getDocumentsByCourse(courseId));
            course.setDocCount(course.getDocuments().size());
        }
        return course;
    }

    public List<DocumentMetadata> getDocumentsByCourse(String courseId) {
        return documentRepository.findByCourseId(courseId);
    }

    public void deleteDocument(String docId) {
        DocumentMetadata meta = documentRepository.findById(docId).orElse(null);
        if (meta != null) {
            gridFsTemplate.delete(new Query(Criteria.where("_id").is(new ObjectId(meta.getGridfsId()))));
            documentRepository.deleteById(docId);
            notifyAiServiceDeletion(docId);
        }
    }

    private void notifyAiServiceDeletion(String docId) {
        try {
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(getAiCleanupUrl() + docId))
                    .DELETE()
                    .build();
            httpClient.sendAsync(request, HttpResponse.BodyHandlers.ofString())
                    .thenAccept(
                            res -> System.out.println("AI Deletion response (" + res.statusCode() + ") for: " + docId));
        } catch (Exception e) {
            System.err.println("Failed to notify AI Service for deletion: " + e.getMessage());
        }
    }

    public void deleteProfessorData(String profId) {
        System.out.println("🚀 Début du nettoyage global pour le professeur: " + profId);
        List<Course> courses = courseRepository.findByProfesseurId(profId);
        for (Course course : courses) {
            deleteCourse(profId, course.getId());
        }
        System.out.println("✅ Nettoyage terminé pour le professeur: " + profId);
    }

    public boolean renameDocument(String profId, String docId, String newName) {
        DocumentMetadata doc = documentRepository.findById(docId).orElse(null);
        if (doc != null) {
            doc.setNom(newName);
            documentRepository.save(doc);
            return true;
        }
        return false;
    }

    public DocumentMetadata updateDocumentMetadata(String docId, String context, String role, List<String> sources) {
        DocumentMetadata doc = documentRepository.findById(docId).orElse(null);
        if (doc != null) {
            if (context != null)
                doc.setCourseContext(context);
            if (role != null)
                doc.setSystemRole(role);
            if (sources != null)
                doc.setCustomSources(sources);
            return documentRepository.save(doc);
        }
        return null;
    }

    /**
     * Expose les métadonnées d'un document pour les services consommateurs (ex: live-service).
     * Remplace l'accès direct à DocumentRepository depuis les autres services.
     */
    public DocumentMetadata getDocumentMetadataById(String docId) {
        return documentRepository.findById(docId).orElse(null);
    }

    /**
     * Expose le flux binaire PDF d'un document via GridFS pour les services consommateurs.
     * Remplace le GridFsTemplate injecté directement dans live-service.
     */
    public ResponseEntity<org.springframework.core.io.InputStreamResource> streamDocument(String docId) {
        try {
            DocumentMetadata meta = documentRepository.findById(docId).orElse(null);
            if (meta == null || meta.getGridfsId() == null) {
                return ResponseEntity.notFound().build();
            }
            org.springframework.data.mongodb.gridfs.GridFsResource resource =
                    gridFsTemplate.getResource(
                            gridFsTemplate.findOne(new Query(Criteria.where("_id").is(new ObjectId(meta.getGridfsId())))));
            if (resource == null || !resource.exists()) {
                return ResponseEntity.notFound().build();
            }
            org.springframework.http.HttpHeaders headers = new org.springframework.http.HttpHeaders();
            headers.add("Content-Disposition", "inline; filename=\"" + meta.getNom() + "\"");
            return ResponseEntity.ok()
                    .headers(headers)
                    .contentLength(resource.contentLength())
                    .contentType(org.springframework.http.MediaType.APPLICATION_PDF)
                    .body(new org.springframework.core.io.InputStreamResource(resource.getInputStream()));
        } catch (Exception e) {
            System.err.println("❌ [CourseService] Erreur streaming document " + docId + ": " + e.getMessage());
            return ResponseEntity.internalServerError().build();
        }
    }


    public ResponseEntity<ApiResponse> uploadDocument(String profId, String courseTitle, int method,
            MultipartFile file) {
        try {
            Course course = courseRepository.findByProfesseurIdAndTitre(profId, courseTitle);
            if (course == null) {
                course = createCourse(profId, courseTitle);
            }
            return processFileUpload(course, method, file);
        } catch (Exception e) {
            return ResponseEntity.status(500)
                    .body(new ApiResponse(false, "Erreur lors de l'upload: " + e.getMessage(), null));
        }
    }

    public ResponseEntity<ApiResponse> uploadDocumentById(String courseId, int method, MultipartFile file) {
        try {
            Course course = courseRepository.findById(courseId).orElse(null);
            if (course == null) {
                return ResponseEntity.status(404)
                        .body(new ApiResponse(false, "Cours introuvable", null));
            }
            return processFileUpload(course, method, file);
        } catch (Exception e) {
            return ResponseEntity.status(500)
                    .body(new ApiResponse(false, "Erreur lors de l'upload: " + e.getMessage(), null));
        }
    }

    private ResponseEntity<ApiResponse> processFileUpload(Course course, int method, MultipartFile file)
            throws Exception {
        // Sauvegarde dans GridFS
        ObjectId gridFsId = gridFsTemplate.store(file.getInputStream(), file.getOriginalFilename());

        // Sauvegarde metadata
        DocumentMetadata metadata = new DocumentMetadata(course.getId(), file.getOriginalFilename(),
                gridFsId.toString());
        documentRepository.save(metadata);

        // Appel IA : Sauvegarde locale temporaire pour le volume partagé
        try {
            Path sharedPath = Paths.get(SHARED_UPLOADS_HOST, file.getOriginalFilename());
            Files.copy(file.getInputStream(), sharedPath, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
            // On envoie le chemin ABSOLU du fichier sur l'hôte, car FastAPI tourne en local
            notifyAiService(sharedPath.toAbsolutePath().toString(), metadata.getId(), method);
        } catch (Exception aiEx) {
            System.err.println("AI Notification failed: " + aiEx.getMessage());
        }

        return ResponseEntity.ok(new ApiResponse(true, "Document uploadé et envoyé à l'IA", metadata));
    }

    private void notifyAiService(String dockerPath, String mongoId, int method) {
        try {
            String escapedPath = dockerPath.replace("\\", "\\\\");
            String json = String.format("{\"pdf_path\": \"%s\", \"mongo_id\": \"%s\"}", escapedPath, mongoId);

            String targetUrl = getArchivisteUrl(); // default -> /api/ai/upload-pdf
            if (method == 2) {
                // Change url to advanced endpoint
                targetUrl = targetUrl.replace("/upload-pdf", "/upload-pdf-advanced");
            }

            System.out.println("🚀 [CourseService] Sending POST to: " + targetUrl);
            System.out.println("📦 [CourseService] JSON Body: " + json);

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(targetUrl))
                    .version(HttpClient.Version.HTTP_1_1)
                    .header("Content-Type", "application/json; charset=UTF-8")
                    .POST(HttpRequest.BodyPublishers.ofString(json, java.nio.charset.StandardCharsets.UTF_8))
                    .build();

            httpClient.sendAsync(request, HttpResponse.BodyHandlers.ofString())
                    .thenAccept(
                            res -> {
                                System.out.println("✅ AI Service response (" + res.statusCode() + "): " + res.body());
                                if (res.statusCode() == 400) {
                                    System.err.println("❌ Error 400 detected! Check if JSON matches FastAPI models.");
                                }
                            });
        } catch (Exception e) {
            System.err.println("Error notifying AI Service: " + e.getMessage());
        }
    }

    public long getTotalFilesCount(String adminId) {
        if (adminId == null || adminId.isEmpty()) {
            return mongoTemplate.count(new Query(), "fs.files");
        }
        List<String> profIds = getProfessorIdsForAdmin(adminId);
        List<String> courseIds = courseRepository.findByProfesseurIdIn(profIds).stream().map(Course::getId).collect(Collectors.toList());
        return documentRepository.countByCourseIdIn(courseIds);
    }

    public long getTotalStorageBytes(String adminId) {
        List<String> gridFsIds;
        if (adminId == null || adminId.isEmpty()) {
            gridFsIds = null; // null means all
        } else {
            List<String> profIds = getProfessorIdsForAdmin(adminId);
            List<String> courseIds = courseRepository.findByProfesseurIdIn(profIds).stream().map(Course::getId).collect(Collectors.toList());
            gridFsIds = documentRepository.findByCourseIdIn(courseIds).stream().map(DocumentMetadata::getGridfsId).collect(Collectors.toList());
        }

        Query query = new Query();
        if (gridFsIds != null) {
            List<ObjectId> objectIds = gridFsIds.stream().map(ObjectId::new).collect(Collectors.toList());
            query.addCriteria(Criteria.where("_id").in(objectIds));
        }

        List<org.bson.Document> results = mongoTemplate.getCollection("fs.files")
                .find(query.getQueryObject())
                .projection(new org.bson.Document("length", 1))
                .into(new java.util.ArrayList<>());

        long total = 0;
        for (org.bson.Document doc : results) {
            total += doc.getLong("length");
        }
        return total;
    }

    private List<String> getProfessorIdsForAdmin(String adminId) {
        return gardienClient.getProfessorIds(adminId);
    }

    public List<Map<String, Object>> validateAllDocuments(String adminId) {
        Criteria criteria = new Criteria();
        if (adminId != null && !adminId.isEmpty()) {
            List<String> profIds = getProfessorIdsForAdmin(adminId);
            List<String> courseIds = courseRepository.findByProfesseurIdIn(profIds).stream().map(Course::getId).collect(Collectors.toList());
            criteria = Criteria.where("course_id").in(courseIds);
        }

        AggregationOperation convertId = context -> new org.bson.Document("$addFields",
                new org.bson.Document("gridfsId_obj",
                        new org.bson.Document("$toObjectId", "$gridfs_id")));

        LookupOperation lookupFs = Aggregation.lookup("fs.files", "gridfsId_obj", "_id", "fileInfo");
        MatchOperation matchDocs = Aggregation.match(criteria);
        MatchOperation matchMissing = Aggregation.match(Criteria.where("fileInfo").size(0));

        LookupOperation lookupCourse = Aggregation.lookup("courses", "course_id", "_id", "courseInfo");
        UnwindOperation unwindCourse = Aggregation.unwind("courseInfo", true);

        ProjectionOperation project = Aggregation.project()
                .and("courseInfo.professeur_id").as("professeur")
                .and("courseInfo.titre").as("cours")
                .and("id").as("docId")
                .and("nom").as("fileName")
                .and("gridfs_id").as("gridFsId");

        Aggregation agg = Aggregation.newAggregation(convertId, lookupFs, matchDocs, matchMissing, lookupCourse, unwindCourse,
                project);
        List<Map> results = mongoTemplate.aggregate(agg, "documents", Map.class).getMappedResults();
        return results.stream()
                .map(m -> (Map<String, Object>) m)
                .collect(Collectors.toList());
    }

    public long cleanOrphanedFiles(String adminId) {
        // NOTE: Nettoyage global des orphelins GridFS (fichiers sans metadata)
        // Si adminId est fourni, on ne nettoie QUE si l'orphelin n'est PAS référencé par cet admin ?
        // En fait, un orphelin GridFS est par définition non référencé. 
        // Par sécurité, on limite le nettoyage aux orphelins si l'admin est "GLOBAL" ou on ignore adminId ici
        // car un fichier orphelin n'a plus de propriétaire.
        return cleanOrphanedFiles(); 
    }

    public long cleanOrphanedFiles() {
        // Get all GridFS IDs referenced in the documents collection
        List<String> referencedGridFsIds = documentRepository.findAll().stream()
                .map(DocumentMetadata::getGridfsId)
                .filter(Objects::nonNull)
                .collect(Collectors.toList());

        List<ObjectId> objectIds = referencedGridFsIds.stream()
                .map(id -> {
                    try {
                        return new ObjectId(id);
                    } catch (Exception e) {
                        return null;
                    }
                })
                .filter(Objects::nonNull)
                .collect(Collectors.toList());

        // Find files in GridFS not in the list
        Query query = new Query(Criteria.where("_id").nin(objectIds));
        List<org.bson.Document> orphanedFiles = mongoTemplate.find(query, org.bson.Document.class, "fs.files");

        long count = 0;
        for (org.bson.Document file : orphanedFiles) {
            gridFsTemplate.delete(new Query(Criteria.where("_id").is(file.get("_id"))));
            count++;
        }
        return count;
    }

    public long removeDeadReferences(String adminId) {
        List<Map<String, Object>> deadRefs = validateAllDocuments(adminId);
        long count = 0;
        for (Map<String, Object> ref : deadRefs) {
            String docId = (String) ref.get("docId");
            notifyAiServiceDeletion(docId);
            documentRepository.deleteById(docId);
            count++;
        }
        return count;
    }

    public Map<String, Map<String, Long>> getProfessorStats(String adminId) {
        Map<String, Map<String, Long>> stats = new HashMap<>();
        List<User> professors = gardienClient.getProfessors(adminId);

        for (User prof : professors) {
            String profId = prof.getId();
            Map<String, Long> profStats = new HashMap<>();
            long courseCount = courseRepository.findByProfesseurId(profId).size();
            profStats.put("courses", courseCount);
            List<Course> courses = courseRepository.findByProfesseurId(profId);
            long docCount = 0;
            for (Course c : courses) {
                docCount += documentRepository.countByCourseId(c.getId());
            }
            profStats.put("documents", docCount);
            stats.put(profId, profStats);
        }
        return stats;
    }

    public long syncQdrantOrphans(String adminId) {
        System.out.println("🧹 Synchronisation des orphelins Qdrant pour admin: " + adminId);
        List<String> validIds;
        if (adminId != null && !adminId.isEmpty()) {
            List<String> profIds = getProfessorIdsForAdmin(adminId);
            List<String> courseIds = courseRepository.findByProfesseurIdIn(profIds).stream().map(Course::getId).collect(Collectors.toList());
            validIds = documentRepository.findByCourseIdIn(courseIds).stream().map(DocumentMetadata::getId).collect(Collectors.toList());
        } else {
            validIds = documentRepository.findAll().stream().map(DocumentMetadata::getId).collect(Collectors.toList());
        }
        Set<String> mongoIdsSet = new HashSet<>(validIds);

        long cleanedCount = 0;
        try {
            HttpRequest request = HttpRequest.newBuilder().uri(URI.create(getAiCleanupUrl() + "ids")).GET().build();
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() == 200) {
                Set<String> qdrantIds = parseIds(response.body());
                if (qdrantIds.isEmpty() && !mongoIdsSet.isEmpty()) {
                    System.err.println("⚠️ Sync Qdrant: Qdrant semble vide alors que Mongo a des docs. Annulation par sécurité.");
                    return 0;
                }
                for (String id : qdrantIds) {
                    if (id.length() > 0 && !mongoIdsSet.contains(id)) {
                        if (adminId != null && !adminId.isEmpty() && documentRepository.existsById(id)) {
                            continue;
                        }
                        System.out.println("🗑️ Orphelin détecté dans Qdrant: " + id);
                        notifyAiServiceDeletion(id);
                        cleanedCount++;
                    }
                }
            } else {
                System.err.println("❌ Sync Qdrant: Échec API IA (Code: " + response.statusCode() + "). Annulation.");
                return 0; // ABORT cleanup if API fails
            }
        } catch (Exception e) {
            System.err.println("Erreur lors de la synchronisation Qdrant: " + e.getMessage());
        }
        return cleanedCount;
    }

    public Map<String, Object> getGlobalAdminStats() {
        Map<String, Object> globalStats = new HashMap<>();
        List<User> admins = gardienClient.getAdmins();
        for (User admin : admins) {
            String adminId = admin.getId();
            List<User> professors = gardienClient.getProfessors(adminId);
            long profCount = professors.size();
            long docCount = 0;
            if (profCount > 0) {
                List<String> profIds = professors.stream().map(User::getId).collect(Collectors.toList());
                List<String> courseIds = courseRepository.findByProfesseurIdIn(profIds).stream().map(Course::getId).collect(Collectors.toList());
                docCount = documentRepository.countByCourseIdIn(courseIds);
            }
            Map<String, Long> stats = new HashMap<>();
            stats.put("professorCount", profCount);
            stats.put("documentCount", docCount);
            globalStats.put(adminId, stats);
        }
        return globalStats;
    }

    public Map<String, Object> performSystemWideCleanup() {
        System.out.println("🚨 Démarrage d'un nettoyage SYSTÉMIQUE global...");
        Map<String, Object> results = new HashMap<>();

        // Phase 1 : GridFS (Orphelins physiques)
        long gridfsCleaned = cleanOrphanedFiles(null);
        results.put("gridfs_cleaned", gridfsCleaned);

        // Phase 2 : MongoDB (Références mortes vers des fichiers inexistants)
        long refsCleaned = removeDeadReferences(null);
        results.put("mongo_refs_cleaned", refsCleaned);

        // Phase 3 : Qdrant (Vecteurs fantômes sans doc Mongo)
        long qdrantCleaned = syncQdrantOrphans(null);
        results.put("qdrant_cleaned", qdrantCleaned);

        // Phase 4 : Reverse (Docs Mongo sans vecteurs Qdrant)
        long reverseCleaned = cleanDeadMongoReferences(null);
        results.put("mongo_hollow_docs_cleaned", reverseCleaned);

        System.out.println("✅ Nettoyage systémique terminé : " + results);
        return results;
    }

    public long cleanDeadMongoReferences(String adminId) {
        System.out.println("🧹 Reverse Cleanup: Recherche des docs Mongo sans vecteurs Qdrant...");
        
        // 1. Récupérer les IDs de Qdrant
        try {
            HttpRequest request = HttpRequest.newBuilder().uri(URI.create(getAiCleanupUrl() + "ids")).GET().build();
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
            
            if (response.statusCode() != 200) {
                System.err.println("❌ Reverse Sync: Échec API IA (Code: " + response.statusCode() + "). Nettoyage annulé.");
                return 0;
            }

            Set<String> qdrantIds = parseIds(response.body());
            
            // 2. Parcourir les documents Mongo
            List<DocumentMetadata> allDocs;
            if (adminId != null && !adminId.isEmpty()) {
                List<String> profIds = getProfessorIdsForAdmin(adminId);
                List<String> courseIds = courseRepository.findByProfesseurIdIn(profIds).stream().map(Course::getId).collect(Collectors.toList());
                allDocs = documentRepository.findByCourseIdIn(courseIds);
            } else {
                allDocs = documentRepository.findAll();
            }

            // SECURITY: If Qdrant returns nothing but we have docs in Mongo, SOMETHING IS WRONG.
            if (qdrantIds.isEmpty() && !allDocs.isEmpty()) {
                System.err.println("❌ [CRITIQUE] Reverse Sync: Qdrant est vide mais Mongo contient " + allDocs.size() + " docs. ABORT pour éviter la perte de données.");
                return 0;
            }

            long count = 0;
            for (DocumentMetadata doc : allDocs) {
                if (!qdrantIds.contains(doc.getId())) {
                    System.out.println("🗑️ Suppression doc Mongo 'creux' (pas de vecteurs): " + doc.getNom() + " (ID: " + doc.getId() + ")");
                    deleteDocument(doc.getId());
                    count++;
                }
            }
            return count;
        } catch (Exception e) {
            System.err.println("Erreur Reverse Sync: Impossible de joindre l'IA: " + e.getMessage());
            return 0;
        }
    }

    /**
     * Répare Qdrant en cas de corruption WAL en supprimant physiquement les collections 
     * et en redémarrant le conteneur.
     */
    public Map<String, Object> hardRepairQdrant() {
        System.out.println("🔨 [CourseService] Démarrage de la réparation HARD de Qdrant...");
        Map<String, Object> results = new HashMap<>();
        try {
            // Chemin absolu du projet pour trouver le docker-compose
            String projectDir = "/Volumes/MonSSD/pfe/test-microservices";
            
            // 1. Stop Qdrant
            executeCommand(projectDir, "docker-compose", "stop", "qdrant");
            results.put("step1", "Qdrant arrêté");

            // 2. Nettoyage physique du volume (Suppression du dossier collections corrompu)
            // On utilise une image alpine temporaire pour accéder au volume nommé
            executeCommand(projectDir, "docker", "run", "--rm", "-v", "test-microservices_qdrant_data:/qdrant_storage", "alpine", "rm", "-rf", "/qdrant_storage/collections");
            results.put("step2", "Dossier collections supprimé (Volume nettoyé)");

            // 3. Start Qdrant
            executeCommand(projectDir, "docker-compose", "start", "qdrant");
            results.put("step3", "Qdrant redémarré avec succès");

            System.out.println("✅ [CourseService] Réparation HARD terminée.");
            results.put("success", true);
        } catch (Exception e) {
            System.err.println("❌ [CourseService] Échec de la réparation HARD : " + e.getMessage());
            results.put("success", false);
            results.put("error", e.getMessage());
        }
        return results;
    }

    private Set<String> parseIds(String jsonBody) {
        Set<String> ids = new HashSet<>();
        try {
            int startIndex = jsonBody.indexOf("[");
            int endIndex = jsonBody.lastIndexOf("]");
            if (startIndex != -1 && endIndex != -1) {
                String content = jsonBody.substring(startIndex + 1, endIndex);
                if (!content.trim().isEmpty()) {
                    String[] parts = content.split(",");
                    for (String part : parts) {
                        String cleanId = part.replace("\"", "").replace("[", "").replace("]", "").trim();
                        if (!cleanId.isEmpty()) {
                            ids.add(cleanId);
                        }
                    }
                }
            }
        } catch (Exception e) {
            System.err.println("❌ Erreur parsing IDs: " + e.getMessage());
        }
        return ids;
    }

    private void executeCommand(String workingDir, String... command) throws Exception {
        ProcessBuilder pb = new ProcessBuilder(command);
        pb.directory(new java.io.File(workingDir));
        pb.redirectErrorStream(true);
        Process process = pb.start();
        
        // On attend la fin (blockant)
        int exitCode = process.waitFor();
        if (exitCode != 0) {
            throw new Exception("La commande a échoué avec le code " + exitCode + " : " + String.join(" ", command));
        }
    }
}
