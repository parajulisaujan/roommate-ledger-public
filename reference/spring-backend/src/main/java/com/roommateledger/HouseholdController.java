package com.roommateledger;

import java.security.Principal;
import java.util.*;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api")
public class HouseholdController {
  private final HouseholdService service;

  public HouseholdController(HouseholdService service) {
    this.service = service;
  }

  record Name(String name) {}

  @GetMapping("/households")
  Object list(Principal p) {
    return service.list(AuthController.user(p));
  }

  @PostMapping("/households")
  Object create(Principal p, @RequestBody Name n) {
    return service.create(AuthController.user(p), n.name());
  }

  @GetMapping("/households/{id}/members")
  Object members(Principal p, @PathVariable UUID id) {
    return service.members(AuthController.user(p), id);
  }

  @PostMapping("/households/{id}/invitations")
  Object invite(Principal p, @PathVariable UUID id) {
    return service.invite(AuthController.user(p), id);
  }

  @PostMapping("/invitations/{token}/accept")
  Object accept(Principal p, @PathVariable String token) {
    return service.accept(AuthController.user(p), token);
  }

  @DeleteMapping("/households/{id}/members/{membership}")
  void leave(Principal p, @PathVariable UUID id, @PathVariable UUID membership) {
    service.leave(AuthController.user(p), id, membership);
  }

  @PatchMapping("/households/{id}")
  void rename(Principal p, @PathVariable UUID id, @RequestBody Name n) {
    service.rename(AuthController.user(p), id, n.name());
  }

  @GetMapping("/households/{id}/activity")
  Object activity(Principal p, @PathVariable UUID id) {
    return service.activity(AuthController.user(p), id);
  }
}
