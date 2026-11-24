package com.example.liveservice.controller;

import com.example.liveservice.service.LiveSessionService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.core.io.InputStreamResource;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/livesession")
public class LiveSessionController {

    @Autowired
    private LiveSessionService courseService;

    @GetMapping("/documents/{docId}/stream")
    public ResponseEntity<InputStreamResource> streamDocument(@PathVariable String docId) {
        return courseService.getDocumentStream(docId);
    }
}
