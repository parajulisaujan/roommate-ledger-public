package com.roommateledger;

import java.security.Principal;
import java.util.*;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/recurring")
public class RecurringController {
  private final RecurringService service;

  public RecurringController(RecurringService service) {
    this.service = service;
  }

  @GetMapping
  Object list(Principal p, @RequestParam(required = false) UUID householdId) {
    return service.list(AuthController.user(p), householdId);
  }

  @PostMapping
  Object create(Principal p, @RequestBody RecurringService.Input in) {
    return Map.of("id", service.save(AuthController.user(p), null, in));
  }

  @PatchMapping("/{id}")
  Object edit(Principal p, @PathVariable UUID id, @RequestBody RecurringService.Input in) {
    return Map.of("id", service.save(AuthController.user(p), id, in));
  }

  @PostMapping("/{id}/record")
  Object record(Principal p, @PathVariable UUID id) {
    return service.record(AuthController.user(p), id);
  }
}
