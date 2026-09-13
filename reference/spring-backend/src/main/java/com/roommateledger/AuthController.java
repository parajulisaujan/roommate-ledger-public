package com.roommateledger;

import jakarta.servlet.http.*;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.security.Principal;
import java.time.*;
import java.util.*;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api")
public class AuthController {
  private final Store db;
  private final PasswordEncoder encoder;
  private final AccountService accounts;

  public record Credentials(
      @NotBlank @Email @Size(max = 254) String email,
      @NotBlank @Size(min = 12, max = 72) String password,
      @Size(max = 80) String name) {}

  public record Profile(
      @NotBlank @Size(max = 80) String name,
      @NotBlank @Size(max = 32) String diet,
      @NotBlank @Size(max = 60) String timezone,
      boolean notifications) {}

  public AuthController(Store db, PasswordEncoder encoder, AccountService accounts) {
    this.db = db;
    this.encoder = encoder;
    this.accounts = accounts;
  }

  public static UUID user(Principal principal) {
    return UUID.fromString(principal.getName());
  }

  @GetMapping("/health")
  Map<String, String> health() {
    return Map.of("status", "ok");
  }

  @GetMapping("/auth/csrf")
  Map<String, String> csrf(CsrfToken token) {
    return Map.of("token", token.getToken(), "headerName", token.getHeaderName());
  }

  @PostMapping("/auth/register")
  Map<String, Object> register(
      @Valid @RequestBody Credentials c, HttpServletRequest req, HttpServletResponse res) {
    AccountService.validatePassword(c.password());
    if (c.name() == null || c.name().isBlank()) throw ApiException.invalid("Enter your name.");
    UUID id = UUID.randomUUID();
    db.run(
        "INSERT INTO app_user(id,name,email,password_hash) VALUES(?,?,?,?)",
        id,
        c.name().trim(),
        c.email().toLowerCase(Locale.ROOT).trim(),
        encoder.encode(c.password()));
    loginSession(id, req, res);
    accounts.requestVerification(id);
    return profile(id);
  }

  @PostMapping("/auth/login")
  Map<String, Object> login(
      @Valid @RequestBody Credentials c, HttpServletRequest req, HttpServletResponse res) {
    var rows =
        db.list(
            "SELECT id,password_hash FROM app_user WHERE email=? AND deactivated=false",
            c.email().toLowerCase(Locale.ROOT).trim());
    String hash =
        rows.isEmpty()
            ? "$2a$12$abcdefghijklmnopqrstuuCqM0mb.YBBn8x00oAoTPNKaCZLH6bhS"
            : rows.getFirst().get("password_hash").toString();
    if (!encoder.matches(c.password(), hash) || rows.isEmpty())
      throw new ApiException(401, "INVALID_CREDENTIALS", "Email or password is incorrect.");
    UUID id = Store.uuid(rows.getFirst().get("id"));
    loginSession(id, req, res);
    return profile(id);
  }

  private void loginSession(UUID id, HttpServletRequest req, HttpServletResponse res) {
    if (req.getSession(false) != null) req.changeSessionId();
    var context = SecurityContextHolder.createEmptyContext();
    var authentication = new UsernamePasswordAuthenticationToken(id.toString(), null, List.of());
    authentication.setDetails(
        Store.number(
            db.one("SELECT session_version FROM app_user WHERE id=?", id).get("session_version")));
    context.setAuthentication(authentication);
    SecurityContextHolder.setContext(context);
    new HttpSessionSecurityContextRepository().saveContext(context, req, res);
  }

  private Map<String, Object> profile(UUID id) {
    var result =
        db.one(
            "SELECT id,name,email,diet,timezone,currency,notifications,email_verified FROM app_user"
                + " WHERE id=?",
            id);
    result.put("verification_required", accounts.capabilities().get("verificationRequired"));
    return result;
  }

  @GetMapping("/auth/me")
  Map<String, Object> me(Principal p) {
    return profile(user(p));
  }

  @PatchMapping("/profile")
  Map<String, Object> update(Principal p, @Valid @RequestBody Profile profile) {
    ZoneId.of(profile.timezone());
    db.run(
        "UPDATE app_user SET name=?,diet=?,timezone=?,notifications=? WHERE id=?",
        profile.name(),
        profile.diet(),
        profile.timezone(),
        profile.notifications(),
        user(p));
    return me(p);
  }
}
