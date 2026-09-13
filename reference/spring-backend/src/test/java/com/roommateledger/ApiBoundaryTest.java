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
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Transactional
class ApiBoundaryTest {
  @Autowired MockMvc mvc;
  @Autowired Store db;
  @Autowired HouseholdService households;

  UUID account() {
    UUID id = UUID.randomUUID();
    db.run(
        "INSERT INTO app_user(id,name,email,password_hash) VALUES(?,?,?,?)",
        id,
        "Fictional audit",
        id + "@example.test",
        "unused");
    return id;
  }

  @Test
  void fractionalCentsAndInvalidDatesAreSafeClientErrors() throws Exception {
    UUID id = account();
    for (String amount : List.of("100.5", "null")) {
      mvc.perform(
              post("/api/expenses")
                  .with(user(id.toString()))
                  .with(csrf())
                  .contentType("application/json")
                  .content(
                      "{\"title\":\"Invalid\",\"amount\":"
                          + amount
                          + ",\"category\":\"Other\",\"scope\":\"PERSONAL\",\"payerId\":\""
                          + id
                          + "\",\"date\":\"2026-01-01\",\"splitMethod\":\"EQUAL\"}"))
          .andExpect(status().isBadRequest())
          .andExpect(jsonPath("code").value("VALIDATION_ERROR"))
          .andExpect(jsonPath("trace").doesNotExist());
    }
    mvc.perform(
            patch("/api/profile")
                .with(user(id.toString()))
                .with(csrf())
                .contentType("application/json")
                .content(
                    "{\"name\":\"Audit\",\"diet\":\"Vegan\",\"timezone\":\"Invalid/Timezone\",\"notifications\":false}"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("trace").doesNotExist());
    mvc.perform(get("/api/analytics/personal?month=invalid").with(user(id.toString())))
        .andExpect(status().isBadRequest());
    assertThat(db.list("SELECT id FROM expense WHERE owner_id=?", id)).isEmpty();
  }

  @Test
  void outsidersCannotReadAnyHouseholdProjection() throws Exception {
    UUID owner = account(), outsider = account();
    UUID house = Store.uuid(households.create(owner, "Fictional API audit").get("id"));
    for (String suffix : List.of("members", "activity", "balances", "settlements", "analytics"))
      mvc.perform(get("/api/households/" + house + "/" + suffix).with(user(outsider.toString())))
          .andExpect(status().isForbidden())
          .andExpect(jsonPath("trace").doesNotExist());
    for (String resource : List.of("expenses", "recurring"))
      mvc.perform(
              get("/api/" + resource)
                  .param("householdId", house.toString())
                  .with(user(outsider.toString())))
          .andExpect(status().isForbidden());
  }
}
