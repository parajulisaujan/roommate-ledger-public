package com.roommateledger;

import java.nio.charset.StandardCharsets;
import java.security.*;
import java.time.*;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AccountService {
  private final Store db;
  private final EmailProvider email;
  private final PasswordEncoder encoder;
  private final String frontend;
  private final boolean verificationRequired;

  public AccountService(
      Store db,
      EmailProvider email,
      PasswordEncoder encoder,
      @Value("${app.frontend-url:http://localhost:3000}") String frontend,
      @Value("${app.email.verification-required:false}") boolean verificationRequired) {
    this.db = db;
    this.email = email;
    this.encoder = encoder;
    this.frontend = frontend;
    this.verificationRequired = verificationRequired;
  }

  public Map<String, Object> capabilities() {
    return Map.of(
        "emailDeliveryAvailable", email.available(), "verificationRequired", verificationRequired);
  }

  static String hash(String token) {
    try {
      return HexFormat.of()
          .formatHex(
              MessageDigest.getInstance("SHA-256").digest(token.getBytes(StandardCharsets.UTF_8)));
    } catch (NoSuchAlgorithmException e) {
      throw new IllegalStateException(e);
    }
  }

  static void validatePassword(String password) {
    if (password == null
        || password.length() < 12
        || password.getBytes(StandardCharsets.UTF_8).length > 72)
      throw ApiException.invalid(
          "Use at least 12 characters and no more than 72 UTF-8 bytes for your password.");
  }

  @Transactional
  public void requestReset(String address) {
    var users =
        db.list(
            "SELECT id FROM app_user WHERE email=? AND deactivated=false",
            address.trim().toLowerCase(Locale.ROOT));
    if (!users.isEmpty()) issue(Store.uuid(users.getFirst().get("id")), "RESET");
  }

  @Transactional
  public void requestVerification(UUID user) {
    issue(user, "VERIFY");
  }

  private void issue(UUID user, String purpose) {
    var account =
        db.one("SELECT email,email_verified,deactivated FROM app_user WHERE id=? FOR UPDATE", user);
    if (!email.available()
        || Boolean.TRUE.equals(account.get("deactivated"))
        || (purpose.equals("VERIFY") && Boolean.TRUE.equals(account.get("email_verified")))) return;
    db.run("DELETE FROM account_token WHERE expires_at<CURRENT_TIMESTAMP");
    db.run("UPDATE account_token SET used=true WHERE user_id=? AND purpose=?", user, purpose);
    byte[] bytes = new byte[32];
    new SecureRandom().nextBytes(bytes);
    String token = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    UUID id = UUID.randomUUID();
    db.run(
        "INSERT INTO account_token(id,user_id,token_hash,purpose,expires_at) VALUES(?,?,?,?,?)",
        id,
        user,
        hash(token),
        purpose,
        OffsetDateTime.now(ZoneOffset.UTC).plusMinutes(purpose.equals("RESET") ? 30 : 1440));
    String action = purpose.equals("RESET") ? "reset" : "verify";
    try {
      email.send(
          account.get("email").toString(),
          purpose.equals("RESET")
              ? "Reset your RoommateLedger password"
              : "Verify your RoommateLedger email",
          "Open this link to continue: "
              + frontend
              + "/#"
              + action
              + "="
              + token
              + "\n"
              + "This link expires and can be used once. If you did not request it, ignore this"
              + " email.");
    } catch (RuntimeException e) {
      db.run("UPDATE account_token SET used=true WHERE id=?", id);
      org.slf4j.LoggerFactory.getLogger(AccountService.class)
          .warn("account_email_delivery_failed purpose={}", purpose);
    }
  }

  private UUID consume(String token, String purpose) {
    if (token == null || !token.matches("[A-Za-z0-9_-]{43}"))
      throw ApiException.invalid("This link is invalid or expired. Request a new email.");
    var rows =
        db.list(
            "SELECT id,user_id FROM account_token WHERE token_hash=? AND purpose=? AND used=false"
                + " AND expires_at>CURRENT_TIMESTAMP FOR UPDATE",
            hash(token),
            purpose);
    if (rows.isEmpty())
      throw ApiException.invalid("This link is invalid or expired. Request a new email.");
    var row = rows.getFirst();
    db.run("UPDATE account_token SET used=true WHERE id=?", row.get("id"));
    return Store.uuid(row.get("user_id"));
  }

  @Transactional
  public void reset(String token, String password) {
    validatePassword(password);
    UUID id = consume(token, "RESET");
    db.run(
        "UPDATE app_user SET password_hash=?,session_version=session_version+1 WHERE id=? AND"
            + " deactivated=false",
        encoder.encode(password),
        id);
    db.run("UPDATE account_token SET used=true WHERE user_id=? AND purpose='RESET'", id);
  }

  @Transactional
  public void verify(String token) {
    UUID id = consume(token, "VERIFY");
    db.run("UPDATE app_user SET email_verified=true WHERE id=? AND deactivated=false", id);
  }

  private void checkPassword(UUID id, String password) {
    var account =
        db.one("SELECT password_hash,deactivated FROM app_user WHERE id=? FOR UPDATE", id);
    if (password == null
        || Boolean.TRUE.equals(account.get("deactivated"))
        || !encoder.matches(password, account.get("password_hash").toString()))
      throw ApiException.invalid("Current password is incorrect.");
  }

  @Transactional
  public void changePassword(UUID id, String current, String replacement) {
    validatePassword(replacement);
    checkPassword(id, current);
    db.run(
        "UPDATE app_user SET password_hash=?,session_version=session_version+1 WHERE id=?",
        encoder.encode(replacement),
        id);
    db.run("UPDATE account_token SET used=true WHERE user_id=?", id);
  }

  @Transactional
  public void deactivate(UUID id, String password) {
    checkPassword(id, password);
    if (db.exists(
        "SELECT m.id FROM membership m WHERE m.user_id=? AND m.role='OWNER' AND m.left_at IS NULL"
            + " AND EXISTS(SELECT 1 FROM membership other WHERE other.household_id=m.household_id"
            + " AND other.user_id<>? AND other.left_at IS NULL)",
        id,
        id))
      throw ApiException.invalid(
          "Remove active roommates from households you own before deactivating. Historical records"
              + " and balances will remain.");
    db.run("UPDATE app_user SET deactivated=true,session_version=session_version+1 WHERE id=?", id);
    db.run("UPDATE membership SET left_at=CURRENT_DATE WHERE user_id=? AND left_at IS NULL", id);
    db.run("UPDATE account_token SET used=true WHERE user_id=?", id);
    db.run("UPDATE recurring_template SET active=false WHERE owner_id=?", id);
    db.run(
        "UPDATE invitation SET expires_at=CURRENT_TIMESTAMP WHERE household_id IN (SELECT"
            + " household_id FROM membership WHERE user_id=? AND role='OWNER')",
        id);
  }
}
