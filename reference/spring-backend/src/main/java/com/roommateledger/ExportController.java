package com.roommateledger;

import java.security.Principal;
import java.time.LocalDate;
import java.util.*;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/export")
class ExportController {
  private final Store db;
  private final HouseholdService households;

  ExportController(Store db, HouseholdService households) {
    this.db = db;
    this.households = households;
  }

  @GetMapping("/expenses")
  ResponseEntity<String> expenses(
      Principal p,
      @RequestParam(required = false) UUID householdId,
      @RequestParam(required = false) LocalDate from,
      @RequestParam(required = false) LocalDate to) {
    UUID user = AuthController.user(p);
    if (householdId != null) households.member(user, householdId);
    var args = new ArrayList<Object>();
    args.add(householdId == null ? user : householdId);
    String where =
        householdId == null
            ? "owner_id=? AND scope='PERSONAL'"
            : "household_id=? AND scope<>'PERSONAL'";
    if (from != null) {
      where += " AND expense_date>=?";
      args.add(from);
    }
    if (to != null) {
      where += " AND expense_date<=?";
      args.add(to);
    }
    var rows =
        db.list(
            "SELECT id,title,merchant,expense_date,category,scope,amount,currency,payer_id FROM"
                + " expense WHERE deleted=false AND "
                + where
                + " ORDER BY expense_date,id LIMIT 10001",
            args.toArray());
    return csv(
        "expenses.csv",
        List.of(
            "id",
            "title",
            "merchant",
            "expense_date",
            "category",
            "scope",
            "amount",
            "currency",
            "payer_id"),
        rows);
  }

  @GetMapping("/settlements")
  ResponseEntity<String> settlements(Principal p, @RequestParam UUID householdId) {
    households.member(AuthController.user(p), householdId);
    return csv(
        "settlements.csv",
        List.of("id", "from_user", "to_user", "amount", "method", "payment_date"),
        db.list(
            "SELECT id,from_user,to_user,amount,method,payment_date FROM settlement WHERE"
                + " household_id=? ORDER BY payment_date,id LIMIT 10001",
            householdId));
  }

  static String cell(Object value) {
    String s = Objects.toString(value, "");
    if (s.matches("(?s)^[\\s]*[=+@-].*") || s.startsWith("\t") || s.startsWith("\r")) s = "'" + s;
    return "\"" + s.replace("\"", "\"\"") + "\"";
  }

  private ResponseEntity<String> csv(
      String filename, List<String> fields, List<Map<String, Object>> rows) {
    if (rows.size() > 10000)
      throw ApiException.invalid(
          "Export exceeds 10,000 records. Use a smaller expense date range or contact your"
              + " administrator for a full data export.");
    var out =
        new StringBuilder(
                String.join(
                    ",",
                    fields.stream().map(f -> f.equals("amount") ? "amount_cents" : f).toList()))
            .append("\r\n");
    for (var row : rows)
      out.append(String.join(",", fields.stream().map(f -> cell(row.get(f))).toList()))
          .append("\r\n");
    return ResponseEntity.ok()
        .header("Content-Disposition", "attachment; filename=\"" + filename + "\"")
        .header("Cache-Control", "no-store")
        .contentType(new MediaType("text", "csv", java.nio.charset.StandardCharsets.UTF_8))
        .body(out.toString());
  }
}
