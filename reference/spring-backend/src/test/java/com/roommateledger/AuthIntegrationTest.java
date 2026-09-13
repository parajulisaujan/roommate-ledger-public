package com.roommateledger;

import static org.assertj.core.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class AuthIntegrationTest {
  @Autowired MockMvc mvc;
  @Autowired ObjectMapper mapper;

  @Test
  void registrationSessionCsrfAndLogout() throws Exception {
    String email = UUID.randomUUID() + "@example.test";
    String payload =
        mapper.writeValueAsString(
            Map.of("name", "Test Account", "email", email, "password", "a-long-test-password"));
    mvc.perform(post("/api/auth/register").contentType("application/json").content(payload))
        .andExpect(status().isForbidden());
    var result =
        mvc.perform(
                post("/api/auth/register")
                    .with(csrf())
                    .contentType("application/json")
                    .content(payload))
            .andExpect(status().isOk())
            .andExpect(jsonPath("password_hash").doesNotExist())
            .andReturn();
    var session = (MockHttpSession) result.getRequest().getSession(false);
    assertThat(session).isNotNull();
    mvc.perform(get("/api/auth/me").session(session))
        .andExpect(status().isOk())
        .andExpect(jsonPath("email").value(email));
    var household =
        mvc.perform(
                post("/api/households")
                    .session(session)
                    .with(csrf())
                    .contentType("application/json")
                    .content("{\"name\":\"Endpoint test\"}"))
            .andExpect(status().isOk())
            .andReturn();
    String id = mapper.readTree(household.getResponse().getContentAsString()).get("id").asText();
    mvc.perform(get("/api/households/" + id + "/activity").session(session))
        .andExpect(status().isOk());
    mvc.perform(
            patch("/api/households/" + id)
                .session(session)
                .with(csrf())
                .contentType("application/json")
                .content("{\"name\":\"Renamed test\"}"))
        .andExpect(status().isOk());
    mvc.perform(get("/api/recurring").param("householdId", id).session(session))
        .andExpect(status().isOk());
    mvc.perform(get("/api/receipts/capabilities").session(session))
        .andExpect(status().isOk())
        .andExpect(jsonPath("automatedExtraction").value(false));
    mvc.perform(post("/api/auth/logout").session(session).with(csrf()))
        .andExpect(status().isNoContent());
    mvc.perform(get("/api/auth/me")).andExpect(status().isUnauthorized());
    mvc.perform(
            post("/api/auth/login").with(csrf()).contentType("application/json").content(payload))
        .andExpect(status().isOk());
    mvc.perform(
            post("/api/auth/login")
                .with(csrf())
                .contentType("application/json")
                .content(payload.replace("a-long-test-password", "an-incorrect-password")))
        .andExpect(status().isUnauthorized());
  }
}
