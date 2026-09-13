package com.roommateledger;

import jakarta.validation.Valid;
import java.security.Principal;
import java.time.LocalDate;
import java.util.UUID;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/expenses")
public class ExpenseController {
  private final ExpenseService service;

  public ExpenseController(ExpenseService service) {
    this.service = service;
  }

  @PostMapping
  Object create(Principal p, @Valid @RequestBody ExpenseService.Input in) {
    return service.create(AuthController.user(p), in, null, null);
  }

  @GetMapping("/{id}")
  Object get(Principal p, @PathVariable UUID id) {
    return service.get(AuthController.user(p), id);
  }

  @PatchMapping("/{id}")
  Object edit(Principal p, @PathVariable UUID id, @Valid @RequestBody ExpenseService.Input in) {
    return service.edit(AuthController.user(p), id, in);
  }

  @DeleteMapping("/{id}")
  void delete(Principal p, @PathVariable UUID id) {
    service.delete(AuthController.user(p), id);
  }

  @GetMapping
  Object list(
      Principal p,
      @RequestParam(required = false) UUID householdId,
      @RequestParam(required = false) String scope,
      @RequestParam(required = false) String search,
      @RequestParam(required = false) String category,
      @RequestParam(required = false) LocalDate from,
      @RequestParam(required = false) LocalDate to,
      @RequestParam(required = false) UUID payer,
      @RequestParam(required = false) UUID participant,
      @RequestParam(required = false) Long min,
      @RequestParam(required = false) Long max,
      @RequestParam(defaultValue = "0") int page) {
    if (page < 0 || page > 100000) throw ApiException.invalid("Invalid page.");
    return service.list(
        AuthController.user(p),
        householdId,
        scope,
        search,
        category,
        from,
        to,
        payer,
        participant,
        min,
        max,
        page);
  }
}
