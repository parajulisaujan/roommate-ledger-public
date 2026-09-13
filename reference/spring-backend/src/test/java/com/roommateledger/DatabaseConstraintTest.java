package com.roommateledger;

import static org.assertj.core.api.Assertions.*;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
@ActiveProfiles("test")
@Transactional
class DatabaseConstraintTest {
  @Autowired Store db;

  @Test
  void allocationRequiresExistingExpenseAndUser() {
    assertThatThrownBy(
            () ->
                db.run(
                    "INSERT INTO allocation(expense_id,user_id,amount) VALUES(?,?,?)",
                    UUID.randomUUID(),
                    UUID.randomUUID(),
                    100))
        .isInstanceOf(DataIntegrityViolationException.class);
  }

  @Test
  void membershipDatesCannotRunBackwards() {
    UUID person = UUID.randomUUID(), house = UUID.randomUUID();
    db.run(
        "INSERT INTO app_user(id,name,email,password_hash) VALUES(?,?,?,?)",
        person,
        "Fictional constraint test",
        person + "@example.test",
        "unused");
    db.run(
        "INSERT INTO household(id,name,created_by) VALUES(?,?,?)",
        house,
        "Fictional constraint test",
        person);
    assertThatThrownBy(
            () ->
                db.run(
                    "INSERT INTO membership(id,household_id,user_id,role,joined_at,left_at)"
                        + " VALUES(?,?,?,'MEMBER',DATE '2026-02-01',DATE '2026-01-01')",
                    UUID.randomUUID(),
                    house,
                    person))
        .isInstanceOf(DataIntegrityViolationException.class);
  }
}
