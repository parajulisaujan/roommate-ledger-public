package com.roommateledger;

import jakarta.validation.constraints.*;
import java.time.LocalDate;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ExpenseService {
  public void requireMember(UUID user, UUID household) {
    households.member(user, household);
  }

  public record Input(
      @NotBlank @Size(max = 120) String title,
      @Size(max = 120) String merchant,
      long amount,
      @NotBlank @Size(max = 40) String category,
      @NotBlank String scope,
      UUID householdId,
      UUID payerId,
      @NotNull LocalDate date,
      @NotBlank String splitMethod,
      List<UUID> participants,
      Map<UUID, Long> values,
      @Size(max = 2000) String notes,
      Integer version) {}

  private final Store db;
  private final HouseholdService households;

  public ExpenseService(Store db, HouseholdService households) {
    this.db = db;
    this.households = households;
  }

  public Map<UUID, Long> validate(UUID user, Input in) {
    if (in.title() == null
        || in.title().isBlank()
        || in.title().length() > 120
        || in.category() == null
        || in.category().isBlank()
        || in.category().length() > 40
        || in.date() == null
        || in.date().isAfter(LocalDate.now())
        || in.date().isBefore(LocalDate.of(1900, 1, 1))
        || (in.notes() != null && in.notes().length() > 2000)
        || (in.merchant() != null && in.merchant().length() > 120))
      throw ApiException.invalid(
          "Check title, category and date. Future expenses belong in recurring bills.");
    if ("PERSONAL".equals(in.scope())) {
      if (in.householdId() != null || (in.payerId() != null && !user.equals(in.payerId())))
        throw ApiException.invalid("Personal expenses must belong to and be paid by you.");
      return Money.split(in.amount(), "EQUAL", List.of(user), null);
    }
    if (in.scope() == null || !Set.of("HOUSEHOLD", "SELECTED_MEMBERS").contains(in.scope()))
      throw ApiException.invalid("Invalid expense scope.");
    households.member(user, in.householdId());
    var applicable = households.applicable(in.householdId(), in.date());
    if (!applicable.contains(user) || !applicable.contains(in.payerId()))
      throw ApiException.invalid(
          "Creator and payer must have belonged to the household on the expense date.");
    var participants = "HOUSEHOLD".equals(in.scope()) ? applicable : in.participants();
    if (participants == null || !applicable.containsAll(participants))
      throw ApiException.invalid("Participants must have belonged to the household on this date.");
    return Money.split(in.amount(), in.splitMethod(), participants, in.values());
  }

  @Transactional
  public Map<String, Object> create(UUID user, Input in, UUID receipt, UUID template) {
    var allocations = validate(user, in);
    UUID id = UUID.randomUUID();
    boolean personal = "PERSONAL".equals(in.scope());
    db.run(
        "INSERT INTO"
            + " expense(id,owner_id,household_id,payer_id,title,merchant,amount,category,scope,split_method,expense_date,notes,receipt_id,template_id)"
            + " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        id,
        user,
        in.householdId(),
        personal ? user : in.payerId(),
        in.title(),
        in.merchant(),
        in.amount(),
        in.category(),
        in.scope(),
        personal ? "EQUAL" : in.splitMethod(),
        in.date(),
        in.notes(),
        receipt,
        template);
    allocations.forEach(
        (participant, amount) ->
            db.run(
                "INSERT INTO allocation(expense_id,user_id,amount) VALUES(?,?,?)",
                id,
                participant,
                amount));
    db.audit(user, in.householdId(), "EXPENSE_CREATED", id);
    return get(user, id);
  }

  public Map<String, Object> get(UUID user, UUID id) {
    var e =
        db.one(
            "SELECT e.*,u.name AS payer_name FROM expense e JOIN app_user u ON u.id=e.payer_id"
                + " WHERE e.id=? AND e.deleted=false",
            id);
    authorize(user, e);
    e.put(
        "allocations",
        db.list(
            "SELECT a.user_id,a.amount,u.name FROM allocation a JOIN app_user u ON u.id=a.user_id"
                + " WHERE a.expense_id=? ORDER BY u.name",
            id));
    return e;
  }

  void authorize(UUID user, Map<String, Object> e) {
    if ("PERSONAL".equals(e.get("scope"))) {
      if (!user.equals(Store.uuid(e.get("owner_id")))) throw ApiException.forbidden();
    } else households.member(user, Store.uuid(e.get("household_id")));
  }

  @Transactional
  public void delete(UUID user, UUID id) {
    var e = get(user, id);
    if (!user.equals(Store.uuid(e.get("owner_id")))) throw ApiException.forbidden();
    if (e.get("receipt_id") != null)
      throw ApiException.invalid(
          "Confirmed receipt items are immutable. Record a correction separately.");
    db.run("UPDATE expense SET deleted=true,version=version+1 WHERE id=?", id);
    db.audit(user, Store.uuid(e.get("household_id")), "EXPENSE_DELETED", id);
  }

  @Transactional
  public Map<String, Object> edit(UUID user, UUID id, Input in) {
    db.one("SELECT id FROM expense WHERE id=? FOR UPDATE", id);
    var e = get(user, id);
    if (!user.equals(Store.uuid(e.get("owner_id")))) throw ApiException.forbidden();
    if (e.get("receipt_id") != null)
      throw ApiException.invalid(
          "Confirmed receipt items are immutable. Record a correction separately.");
    if (in.version() == null || in.version() != ((Number) e.get("version")).intValue())
      throw new ApiException(409, "CONFLICT", "Expense changed. Refresh before editing.");
    if (!Objects.equals(in.householdId(), Store.uuid(e.get("household_id")))
        || !in.scope().equals(e.get("scope")))
      throw ApiException.invalid("Keep the original expense scope and household.");
    var allocations = validate(user, in);
    db.run(
        "UPDATE expense SET"
            + " title=?,merchant=?,amount=?,category=?,payer_id=?,split_method=?,expense_date=?,notes=?,version=version+1"
            + " WHERE id=?",
        in.title(),
        in.merchant(),
        in.amount(),
        in.category(),
        "PERSONAL".equals(in.scope()) ? user : in.payerId(),
        "PERSONAL".equals(in.scope()) ? "EQUAL" : in.splitMethod(),
        in.date(),
        in.notes(),
        id);
    db.run("DELETE FROM allocation WHERE expense_id=?", id);
    allocations.forEach(
        (participant, amount) ->
            db.run(
                "INSERT INTO allocation(expense_id,user_id,amount) VALUES(?,?,?)",
                id,
                participant,
                amount));
    db.audit(user, in.householdId(), "EXPENSE_EDITED", id);
    return get(user, id);
  }

  public Map<String, Object> list(
      UUID user,
      UUID household,
      String scope,
      String search,
      String category,
      LocalDate from,
      LocalDate to,
      UUID payer,
      UUID participant,
      Long min,
      Long max,
      int page) {
    List<Object> args = new ArrayList<>();
    StringBuilder where = new StringBuilder(" WHERE e.deleted=false");
    if (household != null) {
      households.member(user, household);
      where.append(" AND e.household_id=? AND e.scope<>'PERSONAL'");
      args.add(household);
    } else {
      where.append(" AND e.owner_id=? AND e.scope='PERSONAL'");
      args.add(user);
    }
    if (scope != null && !scope.isBlank()) {
      where.append(" AND e.scope=?");
      args.add(scope);
    }
    if (search != null && !search.isBlank()) {
      where.append(" AND (LOWER(e.title) LIKE ? OR LOWER(COALESCE(e.merchant,'')) LIKE ?)");
      args.add("%" + search.toLowerCase(Locale.ROOT) + "%");
      args.add(args.getLast());
    }
    if (category != null && !category.isBlank()) {
      where.append(" AND e.category=?");
      args.add(category);
    }
    if (from != null) {
      where.append(" AND e.expense_date>=?");
      args.add(from);
    }
    if (to != null) {
      where.append(" AND e.expense_date<=?");
      args.add(to);
    }
    if (payer != null) {
      where.append(" AND e.payer_id=?");
      args.add(payer);
    }
    if (participant != null) {
      where.append(
          " AND EXISTS(SELECT 1 FROM allocation a WHERE a.expense_id=e.id AND a.user_id=?)");
      args.add(participant);
    }
    if (min != null) {
      where.append(" AND e.amount>=?");
      args.add(min);
    }
    if (max != null) {
      where.append(" AND e.amount<=?");
      args.add(max);
    }
    long total =
        Store.number(
            db.one("SELECT COUNT(*) AS n FROM expense e" + where, args.toArray()).get("n"));
    args.add(Math.max(0, page) * 25);
    return Map.of(
        "items",
        db.list(
            "SELECT e.*,u.name AS payer_name FROM expense e JOIN app_user u ON u.id=e.payer_id"
                + where
                + " ORDER BY e.expense_date DESC,e.created_at DESC LIMIT 25 OFFSET ?",
            args.toArray()),
        "total",
        total,
        "page",
        Math.max(0, page),
        "pageSize",
        25);
  }
}
