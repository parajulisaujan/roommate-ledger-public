package com.roommateledger;

import static org.assertj.core.api.Assertions.*;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
@ActiveProfiles("test")
@Transactional
class DemoAndReceiptTest {
  @Autowired Store db;
  @Autowired HouseholdService households;
  @Autowired ExpenseService expenses;
  @Autowired FinanceService finance;
  @Autowired RecurringService recurring;
  @Autowired PasswordEncoder encoder;

  @Test
  void fictionalSeedIsOptInAndIdempotent() {
    var seed =
        new DemoData(
            db, households, expenses, finance, recurring, encoder, "fictional-test-password");
    seed.run();
    seed.run();
    UUID owner =
        Store.uuid(db.one("SELECT id FROM app_user WHERE email='demo@example.test'").get("id"));
    assertThat(households.list(owner)).hasSize(1);
    assertThat(
            Store.number(
                db.one("SELECT COUNT(*) AS n FROM expense WHERE owner_id=?", owner).get("n")))
        .isEqualTo(54);
    assertThat(recurring.list(owner, null)).hasSize(1);
  }

  @Test
  void proportionalTaxDiscountAndFeesConserveCents() {
    var a =
        new ReceiptService.Item(
            "Rice", "Rice", BigDecimal.ONE, 1299L, 1299, "Groceries", null, "PERSONAL", List.of());
    var b =
        new ReceiptService.Item(
            "Soap",
            "Soap",
            BigDecimal.ONE,
            999L,
            999,
            "Household Supplies",
            null,
            "PERSONAL",
            List.of());
    var d =
        new ReceiptService.Draft(
            "Store", LocalDate.now(), "USD", null, null, List.of(a, b), 2298, 100, 190, 22, 2410);
    ReceiptService.validateDraft(d, true);
    assertThat(ReceiptService.adjusted(d)).containsExactly(1362L, 1048L);
  }
}
