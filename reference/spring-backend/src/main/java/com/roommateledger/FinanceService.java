package com.roommateledger;

import java.math.*;
import java.time.*;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class FinanceService {
  private final Store db;
  private final HouseholdService households;

  public FinanceService(Store db, HouseholdService households) {
    this.db = db;
    this.households = households;
  }

  public List<Map<String, Object>> balances(UUID user, UUID household) {
    households.member(user, household);
    return db.list(
        """
        SELECT u.id,u.name,
          COALESCE((SELECT SUM(e.amount) FROM expense e WHERE e.household_id=? AND e.payer_id=u.id AND e.deleted=false),0)
          - COALESCE((SELECT SUM(a.amount) FROM allocation a JOIN expense e ON e.id=a.expense_id WHERE e.household_id=? AND a.user_id=u.id AND e.deleted=false),0)
          + COALESCE((SELECT SUM(s.amount) FROM settlement s WHERE s.household_id=? AND s.from_user=u.id),0)
          - COALESCE((SELECT SUM(s.amount) FROM settlement s WHERE s.household_id=? AND s.to_user=u.id),0) AS balance
        FROM app_user u WHERE EXISTS(SELECT 1 FROM membership m WHERE m.user_id=u.id AND m.household_id=?) ORDER BY u.name
        """,
        household,
        household,
        household,
        household,
        household);
  }

  public record Settlement(
      UUID fromUser, UUID toUser, long amount, String method, LocalDate date) {}

  @Transactional
  public void settle(UUID user, UUID household, Settlement s) {
    households.member(user, household);
    Money.positive(s.amount());
    if (!user.equals(s.fromUser())
        || user.equals(s.toUser())
        || s.toUser() == null
        || s.date() == null
        || s.date().isAfter(LocalDate.now())
        || s.method() == null
        || s.method().isBlank()
        || s.method().length() > 40)
      throw ApiException.invalid(
          "Record a payment you made, with a valid recipient, date and method.");
    if (!db.exists(
        "SELECT id FROM membership WHERE household_id=? AND user_id=?", household, s.toUser()))
      throw ApiException.invalid("Recipient must belong to household history.");
    UUID id = UUID.randomUUID();
    db.run(
        "INSERT INTO"
            + " settlement(id,household_id,from_user,to_user,amount,method,payment_date,created_by)"
            + " VALUES(?,?,?,?,?,?,?,?)",
        id,
        household,
        user,
        s.toUser(),
        s.amount(),
        s.method(),
        s.date(),
        user);
    db.audit(user, household, "SETTLEMENT_RECORDED", id);
  }

  public Object settlements(UUID user, UUID household) {
    households.member(user, household);
    return db.list(
        "SELECT s.*,f.name AS from_name,t.name AS to_name FROM settlement s JOIN app_user f ON"
            + " f.id=s.from_user JOIN app_user t ON t.id=s.to_user WHERE household_id=? ORDER BY"
            + " s.payment_date DESC LIMIT 100",
        household);
  }

  public Map<String, Object> analytics(UUID user, UUID household, YearMonth month) {
    if (household != null) households.member(user, household);
    String from =
        household == null
            ? " FROM expense e JOIN allocation a ON a.expense_id=e.id WHERE e.deleted=false AND"
                + " a.user_id=?"
            : " FROM expense e WHERE e.deleted=false AND e.household_id=? AND e.scope<>'PERSONAL'";
    Object subject = household == null ? user : household;
    String amount = household == null ? "a.amount" : "e.amount";
    var current = aggregate(amount, from, subject, month);
    var previous = aggregate(amount, from, subject, month.minusMonths(1));
    long total = Store.number(current.get("total")), prior = Store.number(previous.get("total"));
    List<Map<String, Object>> trend = new ArrayList<>();
    for (int i = 5; i >= 0; i--) {
      YearMonth m = month.minusMonths(i);
      var entry = new LinkedHashMap<>(aggregate(amount, from, subject, m));
      entry.put("month", m.toString());
      trend.add(entry);
    }
    var categories =
        db.list(
            "SELECT e.category,SUM("
                + amount
                + ") AS total"
                + from
                + " AND e.expense_date>=? AND e.expense_date<? GROUP BY e.category ORDER BY total"
                + " DESC",
            subject,
            month.atDay(1),
            month.plusMonths(1).atDay(1));
    var previousCategories =
        db.list(
            "SELECT e.category,SUM("
                + amount
                + ") AS total"
                + from
                + " AND e.expense_date>=? AND e.expense_date<? GROUP BY e.category",
            subject,
            month.minusMonths(1).atDay(1),
            month.atDay(1));
    var result = new LinkedHashMap<String, Object>();
    result.putAll(current);
    result.put("month", month.toString());
    result.put("previousTotal", prior);
    result.put("difference", total - prior);
    result.put(
        "percentChange",
        prior == 0
            ? null
            : BigDecimal.valueOf(total - prior)
                .multiply(BigDecimal.valueOf(100))
                .divide(BigDecimal.valueOf(prior), 1, RoundingMode.HALF_UP));
    result.put("categories", categories);
    result.put("previousCategories", previousCategories);
    result.put("trend", trend);
    return result;
  }

  private Map<String, Object> aggregate(
      String amount, String from, Object subject, YearMonth month) {
    return db.one(
        "SELECT COALESCE(SUM("
            + amount
            + "),0) AS total,COALESCE(SUM(CASE WHEN e.scope='PERSONAL' THEN "
            + amount
            + " ELSE 0 END),0) AS personal,COALESCE(SUM(CASE WHEN e.scope<>'PERSONAL' THEN "
            + amount
            + " ELSE 0 END),0) AS shared"
            + from
            + " AND e.expense_date>=? AND e.expense_date<?",
        subject,
        month.atDay(1),
        month.plusMonths(1).atDay(1));
  }
}
