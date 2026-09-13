package com.roommateledger;

import static org.assertj.core.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.env.MockEnvironment;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Transactional
class OperationalSecurityTest {
  @Autowired MockMvc mvc;
  @Autowired Store db;
  @Autowired HouseholdService households;

  @Test
  void healthIsMinimalAndOtherActuatorEndpointsArePrivate() throws Exception {
    mvc.perform(get("/actuator/health/readiness"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("status").value("UP"))
        .andExpect(jsonPath("components").doesNotExist());
    mvc.perform(get("/actuator/health/liveness")).andExpect(status().isOk());
    mvc.perform(get("/actuator/env")).andExpect(status().isUnauthorized());
  }

  @Test
  void rateLimitsAreConfigurableAndIndependent() {
    var limits = new AbuseControl(new MockEnvironment().withProperty("app.rate.extraction", "1"));
    limits.check("extraction", "a");
    assertThatThrownBy(() -> limits.check("extraction", "a")).isInstanceOf(ApiException.class);
    limits.check("extraction", "b");
    limits.check("login", "a");
  }

  @Test
  void exportsRespectMembershipAndNeutralizeSpreadsheetFormulas() throws Exception {
    UUID owner = UUID.randomUUID(), outsider = UUID.randomUUID();
    for (UUID id : List.of(owner, outsider))
      db.run(
          "INSERT INTO app_user(id,name,email,password_hash) VALUES(?,?,?,?)",
          id,
          "Fictional",
          id + "@example.test",
          "unused");
    UUID house = Store.uuid(households.create(owner, "Fictional export").get("id"));
    mvc.perform(
            get("/api/export/expenses")
                .param("householdId", house.toString())
                .with(user(outsider.toString())))
        .andExpect(status().isForbidden());
    mvc.perform(
            get("/api/export/settlements")
                .param("householdId", house.toString())
                .with(user(outsider.toString())))
        .andExpect(status().isForbidden());
    mvc.perform(get("/api/export/expenses").with(user(owner.toString())))
        .andExpect(status().isOk())
        .andExpect(header().string("Cache-Control", "no-store"))
        .andExpect(content().string(org.hamcrest.Matchers.containsString("amount_cents")));
    assertThat(ExportController.cell("=HYPERLINK(\"bad\")"))
        .startsWith("\"'=")
        .contains("\"\"bad\"\"");
  }

  @Test
  void productionConfigurationFailsClosedWithoutHttpsOrEmail() {
    EmailProvider unavailable = org.mockito.Mockito.mock(EmailProvider.class);
    assertThatThrownBy(
            () -> new ProductionConfiguration(unavailable, "http://localhost:3000", true))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(
            () -> new ProductionConfiguration(unavailable, "https://app.example.test", true))
        .isInstanceOf(IllegalArgumentException.class);
  }
}
