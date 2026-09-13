package com.roommateledger;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.*;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RecurringService {
  private final Store db;
  private final ExpenseService expenses;
  private final ObjectMapper mapper;

  public record Input(
      ExpenseService.Input expense, LocalDate nextDue, String frequency, boolean active) {}

  public RecurringService(Store db, ExpenseService expenses, ObjectMapper mapper) {
    this.db = db;
    this.expenses = expenses;
    this.mapper = mapper;
  }

  public String encode(Object value) {
    try {
      return mapper.writeValueAsString(value);
    } catch (Exception e) {
      throw ApiException.invalid("Invalid draft.");
    }
  }

  public ExpenseService.Input decode(String value) {
    try {
      return mapper.readValue(value, ExpenseService.Input.class);
    } catch (Exception e) {
      throw ApiException.invalid("Invalid stored draft.");
    }
  }

  public List<Map<String, Object>> list(UUID user, UUID household) {
    List<Map<String, Object>> rows;
    if (household == null)
      rows =
          db.list(
              "SELECT * FROM recurring_template WHERE owner_id=? AND household_id IS NULL ORDER BY"
                  + " next_due",
              user);
    else {
      expenses.requireMember(user, household);
      rows =
          db.list(
              "SELECT * FROM recurring_template WHERE household_id=? ORDER BY next_due", household);
    }
    rows.forEach(r -> r.put("expense", decode(r.remove("draft").toString())));
    return rows;
  }

  @Transactional
  public UUID save(UUID user, UUID id, Input in) {
    if (in.expense() == null
        || in.nextDue() == null
        || in.frequency() == null
        || !Set.of("MONTHLY", "WEEKLY", "YEARLY").contains(in.frequency()))
      throw ApiException.invalid("Provide expense defaults, due date and frequency.");
    var e = in.expense();
    expenses.validate(
        user,
        new ExpenseService.Input(
            e.title(),
            e.merchant(),
            e.amount(),
            e.category(),
            e.scope(),
            e.householdId(),
            e.payerId(),
            LocalDate.now(),
            e.splitMethod(),
            e.participants(),
            e.values(),
            e.notes(),
            null));
    if (id == null) {
      id = UUID.randomUUID();
      db.run(
          "INSERT INTO recurring_template(id,owner_id,household_id,draft,next_due,frequency,active)"
              + " VALUES(?,?,?,?,?,?,?)",
          id,
          user,
          e.householdId(),
          encode(e),
          in.nextDue(),
          in.frequency(),
          in.active());
    } else {
      var old = db.one("SELECT * FROM recurring_template WHERE id=? FOR UPDATE", id);
      if (!user.equals(Store.uuid(old.get("owner_id")))) throw ApiException.forbidden();
      db.run(
          "UPDATE recurring_template SET household_id=?,draft=?,next_due=?,frequency=?,active=?"
              + " WHERE id=?",
          e.householdId(),
          encode(e),
          in.nextDue(),
          in.frequency(),
          in.active(),
          id);
    }
    return id;
  }

  @Transactional
  public Object record(UUID user, UUID id) {
    var t = db.one("SELECT * FROM recurring_template WHERE id=? FOR UPDATE", id);
    if (!user.equals(Store.uuid(t.get("owner_id")))) throw ApiException.forbidden();
    if (!Boolean.TRUE.equals(t.get("active")))
      throw ApiException.invalid("This recurring bill is paused.");
    LocalDate due = LocalDate.parse(t.get("next_due").toString());
    if (due.isAfter(LocalDate.now())) throw ApiException.invalid("This bill is not due yet.");
    var e = decode(t.get("draft").toString());
    var result =
        expenses.create(
            user,
            new ExpenseService.Input(
                e.title(),
                e.merchant(),
                e.amount(),
                e.category(),
                e.scope(),
                e.householdId(),
                e.payerId(),
                due,
                e.splitMethod(),
                e.participants(),
                e.values(),
                e.notes(),
                null),
            null,
            id);
    LocalDate next =
        switch (t.get("frequency").toString()) {
          case "WEEKLY" -> due.plusWeeks(1);
          case "YEARLY" -> due.plusYears(1);
          default -> due.plusMonths(1);
        };
    db.run("UPDATE recurring_template SET next_due=? WHERE id=?", next, id);
    return result;
  }
}
