package com.roommateledger;

import static org.assertj.core.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties = "app.cors.allowed-origins=https://ledger.example.test")
@AutoConfigureMockMvc
@ActiveProfiles("test")
class CorsSecurityTest {
  @Autowired MockMvc mvc;

  @Test
  void exactOriginPreflightIsAllowedAndOtherOriginDenied() throws Exception {
    mvc.perform(
            options("/api/expenses")
                .header("Origin", "https://ledger.example.test")
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers", "Content-Type,X-CSRF-TOKEN"))
        .andExpect(status().isOk())
        .andExpect(header().string("Access-Control-Allow-Origin", "https://ledger.example.test"))
        .andExpect(header().string("Access-Control-Allow-Credentials", "true"));
    mvc.perform(
            options("/api/expenses")
                .header("Origin", "https://attacker.example.test")
                .header("Access-Control-Request-Method", "POST"))
        .andExpect(status().isForbidden());
  }

  @Test
  void corsDoesNotBypassAuthenticationOrCsrf() throws Exception {
    mvc.perform(get("/api/analytics/personal").header("Origin", "https://ledger.example.test"))
        .andExpect(status().isUnauthorized());
    mvc.perform(
            post("/api/auth/register")
                .header("Origin", "https://ledger.example.test")
                .contentType("application/json")
                .content("{}"))
        .andExpect(status().isForbidden());
  }

  @Test
  void wildcardAndPathConfigurationAreRejected() {
    for (String origin :
        new String[] {
          "*", "https://*.example.test", "https://example.test/path", "https://example.test/"
        })
      assertThatThrownBy(() -> new SecurityConfig().corsConfigurationSource(origin))
          .isInstanceOf(IllegalArgumentException.class);
  }
}
