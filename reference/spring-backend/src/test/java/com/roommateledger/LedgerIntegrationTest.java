package com.roommateledger;

import static org.assertj.core.api.Assertions.*;

import java.math.BigDecimal;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
@ActiveProfiles("test")
@Transactional
class LedgerIntegrationTest {
  @Autowired Store db;
  @Autowired HouseholdService households;
  @Autowired ExpenseService expenses;
  @Autowired FinanceService finance;
  @Autowired ReceiptService receipts;
  @Autowired RecurringService recurring;
  UUID a, b, c, d, household;
  LocalDate now = LocalDate.now();

  UUID user(String name) {
    UUID id = UUID.randomUUID();
    db.run(
        "INSERT INTO app_user(id,name,email,password_hash) VALUES(?,?,?,?)",
        id,
        name,
        id + "@example.test",
        "unused");
    return id;
  }

  @BeforeEach
  void setup() {
    a = user("Demo A");
    b = user("Demo B");
    c = user("Demo C");
    d = user("Demo D");
    household = Store.uuid(households.create(a, "Fictional household").get("id"));
    for (UUID id : List.of(b, c, d))
      households.accept(id, households.invite(a, household).get("token"));
    db.run("UPDATE membership SET joined_at=? WHERE household_id=?", now.minusMonths(8), household);
  }

  ExpenseService.Input input(long amount, String scope, LocalDate date, List<UUID> ids) {
    return new ExpenseService.Input(
        "Test expense",
        "Store",
        amount,
        "Groceries",
        scope,
        scope.equals("PERSONAL") ? null : household,
        a,
        date,
        "EQUAL",
        ids,
        Map.of(),
        "",
        null);
  }

  @Test
  void privateDataNeverLeaksToMembersOrOwner() {
    UUID id =
        Store.uuid(
            expenses.create(a, input(16500, "PERSONAL", now, List.of(a)), null, null).get("id"));
    assertThatThrownBy(() -> expenses.get(b, id))
        .isInstanceOf(ApiException.class)
        .hasMessageContaining("access");
    assertThat(Store.number(finance.analytics(b, household, YearMonth.from(now)).get("total")))
        .isZero();
    var bPersonal =
        new ExpenseService.Input(
            "Private",
            "",
            5500,
            "Phone",
            "PERSONAL",
            null,
            b,
            now,
            "EQUAL",
            List.of(b),
            null,
            "",
            null);
    UUID privateId = Store.uuid(expenses.create(b, bPersonal, null, null).get("id"));
    assertThatThrownBy(() -> expenses.get(a, privateId)).isInstanceOf(ApiException.class);
    UUID outsider = user("Outsider");
    assertThatThrownBy(() -> finance.balances(outsider, household))
        .isInstanceOf(ApiException.class);
  }

  @Test
  void sharedBillAndSettlementHaveCorrectSigns() {
    var e = expenses.create(a, input(16000, "HOUSEHOLD", now, List.of()), null, null);
    assertThat(expenses.get(b, Store.uuid(e.get("id")))).containsEntry("amount", 16000L);
    assertThat(balance(a)).isEqualTo(12000);
    assertThat(balance(b)).isEqualTo(-4000);
    finance.settle(b, household, new FinanceService.Settlement(b, a, 4000, "Cash", now));
    assertThat(balance(b)).isZero();
    assertThat(balance(a)).isEqualTo(8000);
    assertThat(
            finance.balances(a, household).stream()
                .mapToLong(r -> Store.number(r.get("balance")))
                .sum())
        .isZero();
  }

  long balance(UUID id) {
    return finance.balances(a, household).stream()
        .filter(r -> id.equals(Store.uuid(r.get("id"))))
        .mapToLong(r -> Store.number(r.get("balance")))
        .findFirst()
        .orElseThrow();
  }

  @Test
  void historyUsesMembershipOnExpenseDate() {
    db.run(
        "UPDATE membership SET joined_at=? WHERE user_id=? AND household_id=?",
        now.withDayOfMonth(1),
        d,
        household);
    db.run(
        "UPDATE membership SET left_at=? WHERE user_id=? AND household_id=?",
        now.withDayOfMonth(1).minusDays(1),
        b,
        household);
    var prior =
        expenses.create(
            a,
            input(9000, "HOUSEHOLD", now.withDayOfMonth(1).minusDays(10), List.of()),
            null,
            null);
    var ids =
        db.list("SELECT user_id FROM allocation WHERE expense_id=?", prior.get("id")).stream()
            .map(r -> Store.uuid(r.get("user_id")))
            .toList();
    assertThat(ids).contains(b).doesNotContain(d);
    var current = expenses.create(a, input(9000, "HOUSEHOLD", now, List.of()), null, null);
    assertThat(
            db.list("SELECT user_id FROM allocation WHERE expense_id=?", current.get("id")).stream()
                .map(r -> Store.uuid(r.get("user_id"))))
        .contains(d)
        .doesNotContain(b);
  }

  ReceiptService.Item item(String name, long amount, String scope, List<UUID> ids) {
    return new ReceiptService.Item(
        name, name, BigDecimal.ONE, amount, amount, "Groceries", null, scope, ids);
  }

  @Test
  void membershipChangesDoNotRewriteFinalizedShares() {
    var expense =
        expenses.create(a, input(10000, "HOUSEHOLD", now.minusDays(1), List.of()), null, null);
    var before =
        db.list(
            "SELECT user_id,amount FROM allocation WHERE expense_id=? ORDER BY user_id",
            expense.get("id"));
    db.run("UPDATE membership SET left_at=? WHERE household_id=? AND user_id=?", now, household, b);
    UUID newcomer = user("Later roommate");
    households.accept(newcomer, households.invite(a, household).get("token"));
    assertThat(
            db.list(
                "SELECT user_id,amount FROM allocation WHERE expense_id=? ORDER BY user_id",
                expense.get("id")))
        .isEqualTo(before);
    assertThat(before).hasSize(4);
    assertThat(balance(b)).isEqualTo(-2500);
    assertThat(balance(newcomer)).isZero();
  }

  @Test
  void mixedReceiptConfirmationIsExactPrivateAndIdempotent() {
    UUID id = receipts.manual(a);
    var draft =
        new ReceiptService.Draft(
            "Fictional Grocery",
            now,
            "USD",
            household,
            a,
            List.of(
                item("Rice", 2000, "HOUSEHOLD", List.of()),
                item("Chicken", 1800, "SELECTED_MEMBERS", List.of(a, b)),
                item("Soap", 1200, "HOUSEHOLD", List.of()),
                item("Shampoo", 1000, "PERSONAL", List.of(a))),
            6000,
            0,
            0,
            0,
            6000);
    receipts.save(a, id, draft);
    assertThat(balance(a)).isZero();
    receipts.confirm(a, id);
    assertThat(balance(a)).isEqualTo(3300);
    assertThat(balance(b)).isEqualTo(-1700);
    assertThat(balance(c)).isEqualTo(-800);
    assertThat(balance(d)).isEqualTo(-800);
    assertThat(Store.number(finance.analytics(a, household, YearMonth.from(now)).get("total")))
        .isEqualTo(5000);
    assertThat(Store.number(finance.analytics(a, null, YearMonth.from(now)).get("personal")))
        .isEqualTo(1000);
    assertThatThrownBy(() -> receipts.get(b, id)).isInstanceOf(ApiException.class);
    assertThatThrownBy(() -> receipts.confirm(a, id)).isInstanceOf(ApiException.class);
  }

  @Test
  void mismatchedReceiptCannotConfirmAndAmountsCanBeCorrected() {
    UUID id = receipts.manual(a);
    var draft =
        new ReceiptService.Draft(
            "Store",
            now,
            "USD",
            null,
            a,
            List.of(item("Rice", 1000, "PERSONAL", List.of(a))),
            1000,
            100,
            80,
            20,
            999);
    receipts.save(a, id, draft);
    assertThatThrownBy(() -> receipts.confirm(a, id)).isInstanceOf(ApiException.class);
    var corrected =
        new ReceiptService.Draft(
            "Store", now, "USD", null, a, draft.items(), 1000, 100, 80, 20, 1000);
    receipts.save(a, id, corrected);
    receipts.confirm(a, id);
    assertThat(Store.number(finance.analytics(a, null, YearMonth.from(now)).get("total")))
        .isEqualTo(1000);
  }

  @Test
  void uploadChecksActualBytesAndUnavailableProviderKeepsDraft() throws Exception {
    assertThatThrownBy(
            () ->
                receipts.upload(
                    a,
                    new MockMultipartFile(
                        "file", "photo.png", "image/png", "not an image".getBytes())))
        .isInstanceOf(ApiException.class);
    byte[] png = getClass().getResourceAsStream("/fixtures/pixel.png").readAllBytes();
    var r = receipts.upload(a, new MockMultipartFile("file", "../../photo.png", "image/png", png));
    assertThat(r).containsEntry("status", "FAILED");
    assertThat(r.get("error").toString()).contains("not configured");
    assertThat(balance(a)).isZero();
    assertThat(receipts.upload(a, new MockMultipartFile("file", "photo.png", "image/png", png)))
        .containsEntry("duplicate", true);
  }

  @Test
  void recurringRecordIsSeparateAndCannotRepeatSameDueDate() {
    UUID id =
        recurring.save(
            a,
            null,
            new RecurringService.Input(
                input(5500, "PERSONAL", now, List.of(a)), now, "MONTHLY", true));
    assertThat(Store.number(finance.analytics(a, null, YearMonth.from(now)).get("total"))).isZero();
    recurring.record(a, id);
    recurring.save(
        a,
        id,
        new RecurringService.Input(
            input(9900, "PERSONAL", now, List.of(a)), now.plusMonths(1), "MONTHLY", true));
    assertThat(Store.number(finance.analytics(a, null, YearMonth.from(now)).get("total")))
        .isEqualTo(5500);
    assertThatThrownBy(() -> recurring.record(a, id)).isInstanceOf(ApiException.class);
  }

  @Test
  void analyticsComparesActualSharesAndHandlesNoBaseline() {
    assertThat(finance.analytics(a, null, YearMonth.from(now)).get("percentChange")).isNull();
    expenses.create(a, input(10000, "PERSONAL", now.minusMonths(1), List.of(a)), null, null);
    expenses.create(a, input(8000, "PERSONAL", now, List.of(a)), null, null);
    var stats = finance.analytics(a, null, YearMonth.from(now));
    assertThat(Store.number(stats.get("previousTotal"))).isEqualTo(10000);
    assertThat(Store.number(stats.get("difference"))).isEqualTo(-2000);
    assertThat((BigDecimal) stats.get("percentChange")).isEqualByComparingTo("-20.0");
  }

  @Test
  void invitationSingleUseAndOwnerPermissions() {
    String token = households.invite(a, household).get("token");
    UUID stranger = user("New");
    households.accept(stranger, token);
    assertThatThrownBy(() -> households.accept(user("Other"), token))
        .isInstanceOf(ApiException.class);
    assertThatThrownBy(() -> households.invite(b, household)).isInstanceOf(ApiException.class);
  }

  @Test
  @Transactional(propagation = org.springframework.transaction.annotation.Propagation.NOT_SUPPORTED)
  void failedConfirmationRollsBackEveryItem() {
    UUID id = receipts.manual(a);
    var draft =
        new ReceiptService.Draft(
            "Store",
            now,
            "USD",
            household,
            a,
            List.of(
                item("Valid first item", 1000, "PERSONAL", List.of(a)),
                item("Invalid participant", 1000, "SELECTED_MEMBERS", List.of(UUID.randomUUID()))),
            2000,
            0,
            0,
            0,
            2000);
    receipts.save(a, id, draft);
    assertThatThrownBy(() -> receipts.confirm(a, id)).isInstanceOf(ApiException.class);
    assertThat(db.list("SELECT id FROM expense WHERE receipt_id=?", id)).isEmpty();
    assertThat(receipts.get(a, id)).containsEntry("status", "NEEDS_REVIEW");
  }
}
