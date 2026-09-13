package com.roommateledger;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.net.http.*;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class HttpReceiptProviderTest {
  final ObjectMapper mapper = new ObjectMapper().findAndRegisterModules();
  final HttpClient client = mock(HttpClient.class);

  HttpReceiptExtractionProvider provider() {
    return new HttpReceiptExtractionProvider(
        "https://vision.example.test/extract",
        "test-only-key",
        mapper,
        client,
        Duration.ofMillis(40));
  }

  String fixture() throws Exception {
    UUID person = UUID.randomUUID();
    return mapper.writeValueAsString(
        new ReceiptService.Draft(
            "Fictional store",
            LocalDate.of(2026, 9, 1),
            "USD",
            UUID.randomUUID(),
            person,
            List.of(
                new ReceiptService.Item(
                    "Rice",
                    "RICE",
                    BigDecimal.ONE,
                    100L,
                    100,
                    "Groceries",
                    new BigDecimal("0.9"),
                    "SELECTED_MEMBERS",
                    List.of(person))),
            100,
            0,
            0,
            0,
            100));
  }

  @SuppressWarnings("unchecked")
  void reply(int status, String content) {
    HttpResponse<byte[]> response = mock(HttpResponse.class);
    when(response.statusCode()).thenReturn(status);
    when(response.body()).thenReturn(content.getBytes(java.nio.charset.StandardCharsets.UTF_8));
    when(client.sendAsync(any(HttpRequest.class), any(HttpResponse.BodyHandler.class)))
        .thenReturn(CompletableFuture.completedFuture(response));
  }

  @Test
  void successUsesCredentialsAndDiscardsFinancialAssignments() throws Exception {
    reply(200, fixture());
    var draft = provider().extract(new byte[] {1}, "image/png");
    assertThat(draft.total()).isEqualTo(100);
    assertThat(draft.householdId()).isNull();
    assertThat(draft.payerId()).isNull();
    assertThat(draft.items().getFirst().scope()).isEqualTo("PERSONAL");
    assertThat(draft.items().getFirst().participants()).isEmpty();
    var request = ArgumentCaptor.forClass(HttpRequest.class);
    verify(client).sendAsync(request.capture(), any(HttpResponse.BodyHandler.class));
    assertThat(request.getValue().headers().firstValue("Authorization"))
        .contains("Bearer test-only-key");
    assertThat(request.getValue().headers().firstValue("Content-Type")).contains("image/png");
  }

  @Test
  void absentCredentialsNeverCallNetwork() {
    var provider = new HttpReceiptExtractionProvider("", "", mapper, client, Duration.ofMillis(40));
    assertThat(provider.available()).isFalse();
    assertThatThrownBy(() -> provider.extract(new byte[] {1}, "image/png"))
        .isInstanceOf(ApiException.class)
        .hasMessageContaining("not configured");
    verifyNoInteractions(client);
  }

  @Test
  void malformedMissingFractionalAndUntrustedJsonAreRejected() throws Exception {
    String good = fixture();
    for (String invalid :
        List.of(
            "not-json",
            good.replace("\"amount\":100", "\"amount\":100.9"),
            good.replace("\"amount\":100", "\"amount\":\"100\""),
            good.replace("\"total\":100", "\"total\":null"),
            good.replace(",\"total\":100", ""),
            good.replace("\"currency\":\"USD\"", "\"currency\":\"EUR\""),
            good.replace("\"merchant\":", "\"unexpected\":true,\"merchant\":"),
            good + " {}")) {
      reply(200, invalid);
      assertThatThrownBy(() -> provider().extract(new byte[] {1}, "image/png"))
          .isInstanceOf(ApiException.class)
          .hasMessageContaining("could not be completed");
    }
  }

  @Test
  void failureStatusDoesNotExposeProviderResponse() {
    reply(503, "sensitive upstream diagnostics");
    assertThatThrownBy(() -> provider().extract(new byte[] {1}, "image/png"))
        .hasMessageNotContaining("sensitive")
        .isInstanceOf(ApiException.class);
  }

  @SuppressWarnings("unchecked")
  @Test
  void timeoutCancelsPendingRequest() {
    CompletableFuture<HttpResponse<byte[]>> pending = new CompletableFuture<>();
    when(client.sendAsync(any(HttpRequest.class), any(HttpResponse.BodyHandler.class)))
        .thenReturn(pending);
    assertThatThrownBy(() -> provider().extract(new byte[] {1}, "image/png"))
        .isInstanceOf(ApiException.class);
    assertThat(pending.isCancelled()).isTrue();
  }

  @SuppressWarnings("unchecked")
  @Test
  void connectionFailureIsRecoverable() {
    when(client.sendAsync(any(HttpRequest.class), any(HttpResponse.BodyHandler.class)))
        .thenReturn(
            CompletableFuture.failedFuture(new java.io.IOException("private transport detail")));
    assertThatThrownBy(() -> provider().extract(new byte[] {1}, "image/png"))
        .isInstanceOf(ApiException.class)
        .hasMessageNotContaining("private transport");
  }

  @Test
  void invalidEndpointConfigurationIsRejected() {
    for (String endpoint :
        List.of(
            "http://example.test",
            "https://user:secret@example.test",
            "not a url",
            "https://example.test/#fragment"))
      assertThatThrownBy(
              () ->
                  new HttpReceiptExtractionProvider(
                      endpoint, "configured", mapper, client, Duration.ofSeconds(1)))
          .isInstanceOf(IllegalArgumentException.class);
  }
}
