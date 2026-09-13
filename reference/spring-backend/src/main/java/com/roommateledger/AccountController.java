package com.roommateledger;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.security.Principal;
import java.util.Map;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api")
class AccountController {
  private final AccountService accounts;

  AccountController(AccountService accounts) {
    this.accounts = accounts;
  }

  record Address(@NotBlank @Email @Size(max = 254) String email) {}

  record Token(@NotBlank @Size(max = 100) String token) {}

  record Reset(
      @NotBlank @Size(max = 100) String token, @NotBlank @Size(max = 72) String password) {}

  record Passwords(
      @NotBlank @Size(max = 72) String currentPassword,
      @NotBlank @Size(max = 72) String password) {}

  record Password(@NotBlank @Size(max = 72) String password) {}

  @GetMapping("/auth/capabilities")
  Object capabilities() {
    return accounts.capabilities();
  }

  @PostMapping("/auth/forgot-password")
  Object forgot(@Valid @RequestBody Address address) {
    accounts.requestReset(address.email());
    return Map.of(
        "message",
        "If this address has an active account and email delivery is available, a reset link will"
            + " be sent.");
  }

  @PostMapping("/auth/reset-password")
  Object reset(@Valid @RequestBody Reset input) {
    accounts.reset(input.token(), input.password());
    return Map.of("message", "Password reset. Sign in with your new password.");
  }

  @PostMapping("/auth/verify-email")
  Object verify(@Valid @RequestBody Token input) {
    accounts.verify(input.token());
    return Map.of("message", "Email verified. You can continue to your ledger.");
  }

  @PostMapping("/account/resend-verification")
  Object resend(Principal p) {
    accounts.requestVerification(AuthController.user(p));
    return Map.of(
        "message",
        "If verification is needed and email delivery is available, a new link will be sent.");
  }

  @PostMapping("/account/password")
  void password(Principal p, @Valid @RequestBody Passwords input, HttpServletRequest req) {
    accounts.changePassword(AuthController.user(p), input.currentPassword(), input.password());
    signOut(req);
  }

  @PostMapping("/account/deactivate")
  void deactivate(Principal p, @Valid @RequestBody Password input, HttpServletRequest req) {
    accounts.deactivate(AuthController.user(p), input.password());
    signOut(req);
  }

  private void signOut(HttpServletRequest req) {
    if (req.getSession(false) != null) req.getSession(false).invalidate();
    SecurityContextHolder.clearContext();
  }
}
