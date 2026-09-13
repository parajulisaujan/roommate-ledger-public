package com.roommateledger;

import java.nio.charset.StandardCharsets;
import java.security.*;
import java.time.*;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class HouseholdService {
  private final Store db;

  public HouseholdService(Store db) {
    this.db = db;
  }

  @Transactional
  public void rename(UUID user, UUID household, String name) {
    owner(user, household);
    if (name == null || name.isBlank() || name.length() > 80)
      throw ApiException.invalid("Enter a name up to 80 characters.");
    db.run("UPDATE household SET name=? WHERE id=?", name.trim(), household);
    db.audit(user, household, "HOUSEHOLD_RENAMED", household);
  }

  public Object activity(UUID user, UUID household) {
    member(user, household);
    return db.list(
        "SELECT a.action,a.entity_id,a.created_at,u.name FROM audit_event a JOIN app_user u ON"
            + " a.actor_id=u.id WHERE a.household_id=? ORDER BY a.created_at DESC LIMIT 50",
        household);
  }

  public void member(UUID user, UUID household) {
    if (household == null
        || !db.exists(
            "SELECT id FROM membership WHERE user_id=? AND household_id=? AND left_at IS NULL",
            user,
            household)) throw ApiException.forbidden();
  }

  public void owner(UUID user, UUID household) {
    if (!db.exists(
        "SELECT id FROM membership WHERE user_id=? AND household_id=? AND left_at IS NULL AND"
            + " role='OWNER'",
        user,
        household)) throw ApiException.forbidden();
  }

  public List<UUID> applicable(UUID household, LocalDate date) {
    return db
        .list(
            "SELECT DISTINCT user_id FROM membership WHERE household_id=? AND joined_at<=? AND"
                + " (left_at IS NULL OR left_at>=?)",
            household,
            date,
            date)
        .stream()
        .map(r -> Store.uuid(r.get("user_id")))
        .toList();
  }

  public List<Map<String, Object>> list(UUID user) {
    return db.list(
        "SELECT DISTINCT h.* FROM household h JOIN membership m ON m.household_id=h.id WHERE"
            + " m.user_id=? AND m.left_at IS NULL",
        user);
  }

  @Transactional
  public Map<String, Object> create(UUID user, String name) {
    if (name == null || name.isBlank() || name.length() > 80)
      throw ApiException.invalid("Enter a household name up to 80 characters.");
    UUID id = UUID.randomUUID();
    db.run("INSERT INTO household(id,name,created_by) VALUES(?,?,?)", id, name.trim(), user);
    db.run(
        "INSERT INTO membership(id,household_id,user_id,role,joined_at) VALUES(?,?,?,'OWNER',?)",
        UUID.randomUUID(),
        id,
        user,
        LocalDate.now());
    db.audit(user, id, "HOUSEHOLD_CREATED", id);
    return db.one("SELECT * FROM household WHERE id=?", id);
  }

  public List<Map<String, Object>> members(UUID user, UUID household) {
    member(user, household);
    return db.list(
        "SELECT m.*,u.name,u.diet FROM membership m JOIN app_user u ON u.id=m.user_id WHERE"
            + " m.household_id=? ORDER BY m.joined_at,u.name",
        household);
  }

  public static String hash(String token) {
    try {
      return HexFormat.of()
          .formatHex(
              MessageDigest.getInstance("SHA-256").digest(token.getBytes(StandardCharsets.UTF_8)));
    } catch (NoSuchAlgorithmException e) {
      throw new IllegalStateException(e);
    }
  }

  public Map<String, String> invite(UUID user, UUID household) {
    owner(user, household);
    byte[] bytes = new byte[32];
    new SecureRandom().nextBytes(bytes);
    String token = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    db.run(
        "INSERT INTO invitation(id,household_id,token_hash,expires_at) VALUES(?,?,?,?)",
        UUID.randomUUID(),
        household,
        hash(token),
        OffsetDateTime.now().plusDays(7));
    return Map.of("token", token, "expiresIn", "7 days");
  }

  @Transactional
  public Map<String, Object> accept(UUID user, String token) {
    var invite =
        db.one(
            "SELECT * FROM invitation WHERE token_hash=? AND accepted_by IS NULL AND"
                + " expires_at>CURRENT_TIMESTAMP FOR UPDATE",
            hash(token));
    UUID household = Store.uuid(invite.get("household_id"));
    db.one("SELECT id FROM household WHERE id=? FOR UPDATE", household);
    if (db.exists(
        "SELECT id FROM membership WHERE user_id=? AND household_id=? AND left_at IS NULL",
        user,
        household)) throw ApiException.invalid("You already belong to this household.");
    db.run(
        "INSERT INTO membership(id,household_id,user_id,role,joined_at) VALUES(?,?,?,'MEMBER',?)",
        UUID.randomUUID(),
        household,
        user,
        LocalDate.now());
    db.run("UPDATE invitation SET accepted_by=? WHERE id=?", user, invite.get("id"));
    db.audit(user, household, "MEMBER_JOINED", user);
    return db.one("SELECT * FROM household WHERE id=?", household);
  }

  @Transactional
  public void leave(UUID actor, UUID household, UUID membership) {
    owner(actor, household);
    var m =
        db.one(
            "SELECT * FROM membership WHERE id=? AND household_id=? FOR UPDATE",
            membership,
            household);
    if ("OWNER".equals(m.get("role")))
      throw ApiException.invalid(
          "The owner cannot be removed. Transfer ownership in a future release.");
    if (m.get("left_at") != null) throw ApiException.invalid("This membership has already ended.");
    db.run("UPDATE membership SET left_at=? WHERE id=?", LocalDate.now(), membership);
    db.audit(actor, household, "MEMBER_LEFT", Store.uuid(m.get("user_id")));
  }
}
