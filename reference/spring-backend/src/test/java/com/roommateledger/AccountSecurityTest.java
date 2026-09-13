package com.roommateledger;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import java.time.*;
import java.util.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest(properties = "app.email.verification-required=true")
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Transactional
class AccountSecurityTest {
  @Autowired AccountService accounts;
  @Autowired Store db;
  @Autowired PasswordEncoder encoder;
  @Autowired MockMvc mvc;
  @Autowired HouseholdService households;
  @Autowired ExpenseService expenses;
  @MockitoBean EmailProvider email;
  UUID id;
  String address;
  String delivered;
  final String password = "fictional-original-password";

  @BeforeEach
  void setup() {
    id = UUID.randomUUID();
    address = id + "@example.test";
    db.run(
        "INSERT INTO app_user(id,name,email,password_hash,email_verified) VALUES(?,?,?,?,true)",
        id,
        "Fictional account",
        address,
        encoder.encode(password));
    when(email.available()).thenReturn(true);
    doAnswer(
            i -> {
              delivered = i.getArgument(2);
              return null;
            })
        .when(email)
        .send(anyString(), anyString(), anyString());
  }

  String token(String kind) {
    return delivered.split("#" + kind + "=")[1].split("\\s")[0];
  }

  MockHttpSession login() throws Exception {
    return (MockHttpSession)
        mvc.perform(
                post("/api/auth/login")
                    .with(csrf())
                    .contentType("application/json")
                    .content("{\"email\":\"" + address + "\",\"password\":\"" + password + "\"}"))
            .andExpect(status().isOk())
            .andReturn()
            .getRequest()
            .getSession(false);
  }

  @Test
  void resetIsHashedOneUseAndRevokesEverySession() throws Exception {
    var session = login();
    accounts.requestReset(address);
    String token = token("reset");
    assertThat(db.one("SELECT token_hash FROM account_token WHERE user_id=?", id).get("token_hash"))
        .isEqualTo(AccountService.hash(token))
        .isNotEqualTo(token);
    accounts.reset(token, "fictional-new-password");
    assertThat(
            encoder.matches(
                "fictional-new-password",
                db.one("SELECT password_hash FROM app_user WHERE id=?", id)
                    .get("password_hash")
                    .toString()))
        .isTrue();
    mvc.perform(get("/api/auth/me").session(session)).andExpect(status().isUnauthorized());
    assertThatThrownBy(() -> accounts.reset(token, "fictional-other-password"))
        .isInstanceOf(ApiException.class);
  }

  @Test
  void expiredAndSupersededTokensCannotReset() {
    accounts.requestReset(address);
    String old = token("reset");
    accounts.requestReset(address);
    String latest = token("reset");
    assertThatThrownBy(() -> accounts.reset(old, "fictional-new-password"))
        .isInstanceOf(ApiException.class);
    db.run(
        "UPDATE account_token SET expires_at=? WHERE user_id=?",
        OffsetDateTime.now().minusHours(1),
        id);
    assertThatThrownBy(() -> accounts.reset(latest, "fictional-new-password"))
        .isInstanceOf(ApiException.class);
  }

  @Test
  void unknownEmailAndMissingDeliveryAreGeneric() throws Exception {
    String known =
        mvc.perform(
                post("/api/auth/forgot-password")
                    .with(csrf())
                    .contentType("application/json")
                    .content("{\"email\":\"" + address + "\"}"))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();
    mvc.perform(
            post("/api/auth/forgot-password")
                .with(csrf())
                .contentType("application/json")
                .content("{\"email\":\"absent@example.test\"}"))
        .andExpect(status().isOk())
        .andExpect(content().json(known));
    when(email.available()).thenReturn(false);
    accounts.requestReset(address);
    assertThat(accounts.capabilities()).containsEntry("emailDeliveryAvailable", false);
  }

  @Test
  void verificationGateAllowsRecoveryThenUnlocksLedger() throws Exception {
    db.run("UPDATE app_user SET email_verified=false WHERE id=?", id);
    var session = login();
    mvc.perform(get("/api/households").session(session))
        .andExpect(status().isForbidden())
        .andExpect(jsonPath("code").value("EMAIL_UNVERIFIED"));
    mvc.perform(get("/api/auth/me").session(session)).andExpect(status().isOk());
    accounts.requestVerification(id);
    String token = token("verify");
    accounts.verify(token);
    mvc.perform(get("/api/households").session(session)).andExpect(status().isOk());
    assertThatThrownBy(() -> accounts.verify(token)).isInstanceOf(ApiException.class);
  }

  @Test
  void passwordChangeRequiresCurrentPasswordAndInvalidatesSessions() throws Exception {
    var session = login();
    assertThatThrownBy(() -> accounts.changePassword(id, "wrong", "fictional-new-password"))
        .isInstanceOf(ApiException.class);
    accounts.changePassword(id, password, "fictional-new-password");
    mvc.perform(get("/api/auth/me").session(session)).andExpect(status().isUnauthorized());
  }

  @Test
  void deactivationPreservesFinancialRowsAndDeniesLogin() throws Exception {
    UUID house = Store.uuid(households.create(id, "Fictional retained history").get("id"));
    var expense =
        expenses.create(
            id,
            new ExpenseService.Input(
                "Retained bill",
                "",
                10000,
                "Other",
                "HOUSEHOLD",
                house,
                id,
                LocalDate.now(),
                "EQUAL",
                List.of(),
                Map.of(),
                "",
                null),
            null,
            null);
    accounts.deactivate(id, password);
    assertThat(db.one("SELECT amount FROM expense WHERE id=?", expense.get("id")).get("amount"))
        .isEqualTo(10000L);
    assertThat(db.list("SELECT * FROM allocation WHERE expense_id=?", expense.get("id")))
        .hasSize(1);
    mvc.perform(
            post("/api/auth/login")
                .with(csrf())
                .contentType("application/json")
                .content("{\"email\":\"" + address + "\",\"password\":\"" + password + "\"}"))
        .andExpect(status().isUnauthorized());
  }

  @Test
  void ownerCannotAbandonActiveRoommates() {
    UUID house = Store.uuid(households.create(id, "Fictional active home").get("id")),
        other = UUID.randomUUID();
    db.run(
        "INSERT INTO app_user(id,name,email,password_hash) VALUES(?,?,?,?)",
        other,
        "Other",
        other + "@example.test",
        "unused");
    households.accept(other, households.invite(id, house).get("token"));
    assertThatThrownBy(() -> accounts.deactivate(id, password)).isInstanceOf(ApiException.class);
    assertThat(db.one("SELECT deactivated FROM app_user WHERE id=?", id).get("deactivated"))
        .isEqualTo(false);
  }
}
