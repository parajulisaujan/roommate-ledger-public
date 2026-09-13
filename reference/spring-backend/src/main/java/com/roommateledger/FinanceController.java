package com.roommateledger;

import java.security.Principal;
import java.time.YearMonth;
import java.util.UUID;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api")
public class FinanceController {
  private final FinanceService service;

  public FinanceController(FinanceService service) {
    this.service = service;
  }

  @GetMapping("/households/{id}/balances")
  Object balances(Principal p, @PathVariable UUID id) {
    return service.balances(AuthController.user(p), id);
  }

  @GetMapping("/households/{id}/settlements")
  Object settlements(Principal p, @PathVariable UUID id) {
    return service.settlements(AuthController.user(p), id);
  }

  @PostMapping("/households/{id}/settlements")
  void settle(Principal p, @PathVariable UUID id, @RequestBody FinanceService.Settlement s) {
    service.settle(AuthController.user(p), id, s);
  }

  @GetMapping("/analytics/personal")
  Object personal(Principal p, @RequestParam(required = false) String month) {
    return service.analytics(
        AuthController.user(p), null, month == null ? YearMonth.now() : YearMonth.parse(month));
  }

  @GetMapping("/households/{id}/analytics")
  Object shared(Principal p, @PathVariable UUID id, @RequestParam(required = false) String month) {
    return service.analytics(
        AuthController.user(p), id, month == null ? YearMonth.now() : YearMonth.parse(month));
  }
}
