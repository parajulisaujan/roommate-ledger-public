package com.roommateledger;

import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class Store {
  private final JdbcTemplate jdbc;

  public Store(JdbcTemplate jdbc) {
    this.jdbc = jdbc;
  }

  public List<Map<String, Object>> list(String sql, Object... args) {
    return jdbc.queryForList(sql, args);
  }

  public Map<String, Object> one(String sql, Object... args) {
    var rows = list(sql, args);
    if (rows.isEmpty()) throw ApiException.missing();
    return rows.getFirst();
  }

  public boolean exists(String sql, Object... args) {
    return !list(sql, args).isEmpty();
  }

  public int run(String sql, Object... args) {
    return jdbc.update(sql, args);
  }

  public void audit(UUID actor, UUID household, String action, UUID entity) {
    run(
        "INSERT INTO audit_event(id,household_id,actor_id,action,entity_id) VALUES(?,?,?,?,?)",
        UUID.randomUUID(),
        household,
        actor,
        action,
        entity);
  }

  public static UUID uuid(Object value) {
    return value == null ? null : UUID.fromString(value.toString());
  }

  public static long number(Object value) {
    return ((Number) value).longValue();
  }
}
