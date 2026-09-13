package com.roommateledger;

import java.security.Principal;
import java.util.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/receipts")
public class ReceiptController {
  private final ReceiptService service;

  public ReceiptController(ReceiptService service) {
    this.service = service;
  }

  @GetMapping("/capabilities")
  Object capabilities() {
    return Map.of(
        "automatedExtraction", service.extractionAvailable(), "maxBytes", 8 * 1024 * 1024);
  }

  @GetMapping
  Object list(Principal p) {
    return service.list(AuthController.user(p));
  }

  @PostMapping
  Object manual(Principal p) {
    return Map.of("id", service.manual(AuthController.user(p)));
  }

  @PostMapping("/extract")
  Object extract(Principal p, @RequestParam MultipartFile file) {
    return service.upload(AuthController.user(p), file);
  }

  @GetMapping("/{id}")
  Object get(Principal p, @PathVariable UUID id) {
    return service.get(AuthController.user(p), id);
  }

  @PutMapping("/{id}")
  Object save(Principal p, @PathVariable UUID id, @RequestBody ReceiptService.Draft draft) {
    return service.save(AuthController.user(p), id, draft);
  }

  @PostMapping("/{id}/confirm")
  Object confirm(Principal p, @PathVariable UUID id) {
    return service.confirm(AuthController.user(p), id);
  }
}
