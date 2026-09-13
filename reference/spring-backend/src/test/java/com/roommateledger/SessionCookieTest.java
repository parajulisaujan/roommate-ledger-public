package com.roommateledger;

import static org.assertj.core.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
      "server.servlet.session.cookie.secure=true",
      "server.servlet.session.cookie.same-site=lax"
    })
@ActiveProfiles("test")
class SessionCookieTest {
  @Autowired TestRestTemplate http;

  @Test
  void productionSessionCookieIsSecureHttpOnlyAndSameSite() {
    var response = http.getForEntity("/api/auth/csrf", String.class);
    assertThat(response.getStatusCode().value()).isEqualTo(200);
    assertThat(response.getHeaders().getFirst("Set-Cookie"))
        .contains("JSESSIONID=", "Secure", "HttpOnly", "SameSite=Lax");
  }
}
