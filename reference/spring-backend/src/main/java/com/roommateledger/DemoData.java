package com.roommateledger;

import java.time.*;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/** Explicit opt-in fictional data for a local demonstration database only. */
@Component
@Profile("demo")
public class DemoData implements CommandLineRunner {
  private final Store db;
  private final HouseholdService households;
  private final ExpenseService expenses;
  private final FinanceService finance;
  private final RecurringService recurring;
  private final PasswordEncoder encoder;
  final String password;

  public DemoData(
      Store db,
      HouseholdService households,
      ExpenseService expenses,
      FinanceService finance,
      RecurringService recurring,
      PasswordEncoder encoder,
      @Value("${DEMO_PASSWORD}") String password) {
    this.db = db;
    this.households = households;
    this.expenses = expenses;
    this.finance = finance;
    this.recurring = recurring;
    this.encoder = encoder;
    this.password = password;
  }

  @Override
  @Transactional
  public void run(String... args) {
    if (password.length() < 12 || password.length() > 72)
      throw new IllegalArgumentException("DEMO_PASSWORD must contain 12–72 characters.");
    if (db.exists("SELECT id FROM app_user WHERE email='demo@example.test'")) return;
    List<UUID> users = new ArrayList<>();
    String[] names = {"Demo User", "Alex", "David", "Sam"};
    for (int i = 0; i < 4; i++) {
      UUID id = UUID.randomUUID();
      users.add(id);
      db.run(
          "INSERT INTO app_user(id,name,email,password_hash,diet) VALUES(?,?,?,?,?)",
          id,
          names[i],
          i == 0 ? "demo@example.test" : names[i].toLowerCase(Locale.ROOT) + "@example.test",
          encoder.encode(password),
          i == 1 ? "Vegan" : "No restriction");
    }
    UUID owner = users.getFirst(),
        house = Store.uuid(households.create(owner, "Apartment 204 · Fictional demo").get("id"));
    for (UUID id : users.subList(1, 4))
      households.accept(id, households.invite(owner, house).get("token"));
    db.run(
        "UPDATE membership SET joined_at=? WHERE household_id=?",
        LocalDate.now().minusMonths(7).withDayOfMonth(1),
        house);
    for (int i = 5; i >= 0; i--) {
      LocalDate date = LocalDate.now().minusMonths(i).withDayOfMonth(1);
      add(owner, house, owner, "Rent", 240000, "Rent", "HOUSEHOLD", date, users);
      add(owner, house, users.get(1), "Internet", 7500, "Utilities", "HOUSEHOLD", date, users);
      add(
          owner,
          house,
          owner,
          "Electricity",
          14800 + i * 420,
          "Utilities",
          "HOUSEHOLD",
          date,
          users);
      add(
          owner,
          house,
          owner,
          "Common groceries",
          31700 + i * 310,
          "Groceries",
          "HOUSEHOLD",
          date,
          users);
      add(
          owner,
          house,
          users.get(2),
          "Chicken & fish",
          4800 + i * 180,
          "Groceries",
          "SELECTED_MEMBERS",
          date,
          List.of(owner, users.get(2)));
      add(
          owner,
          null,
          owner,
          "Car insurance",
          16500,
          "Insurance",
          "PERSONAL",
          date,
          List.of(owner));
      add(
          owner,
          null,
          owner,
          "Coffee & dining",
          14300 + i * 730,
          "Dining",
          "PERSONAL",
          date,
          List.of(owner));
      add(owner, null, owner, "Phone", 5500, "Phone", "PERSONAL", date, List.of(owner));
      add(
          owner,
          null,
          owner,
          "Transportation",
          8200 + i * 670,
          "Transportation",
          "PERSONAL",
          date,
          List.of(owner));
    }
    finance.settle(
        users.get(1),
        house,
        new FinanceService.Settlement(users.get(1), owner, 60000, "Cash", LocalDate.now()));
    var phone =
        new ExpenseService.Input(
            "Phone",
            "",
            5500,
            "Phone",
            "PERSONAL",
            null,
            owner,
            LocalDate.now(),
            "EQUAL",
            List.of(owner),
            Map.of(),
            "Fictional demo",
            null);
    recurring.save(
        owner,
        null,
        new RecurringService.Input(phone, LocalDate.now().plusDays(10), "MONTHLY", true));
    var internet =
        new ExpenseService.Input(
            "Internet",
            "",
            7500,
            "Utilities",
            "HOUSEHOLD",
            house,
            owner,
            LocalDate.now(),
            "EQUAL",
            users,
            Map.of(),
            "Fictional demo",
            null);
    recurring.save(
        owner,
        null,
        new RecurringService.Input(internet, LocalDate.now().plusDays(5), "MONTHLY", true));
  }

  void add(
      UUID owner,
      UUID house,
      UUID payer,
      String title,
      long amount,
      String category,
      String scope,
      LocalDate date,
      List<UUID> participants) {
    expenses.create(
        owner,
        new ExpenseService.Input(
            title,
            "Fictional demo",
            amount,
            category,
            scope,
            house,
            payer,
            date,
            "EQUAL",
            participants,
            Map.of(),
            "Fictional development data",
            null),
        null,
        null);
  }
}
