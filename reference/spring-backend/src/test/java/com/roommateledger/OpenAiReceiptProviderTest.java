package com.roommateledger;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.http.*;
import java.time.Duration;
import java.util.concurrent.*;
import org.junit.jupiter.api.*;
import org.mockito.ArgumentCaptor;

class OpenAiReceiptProviderTest {
  HttpClient client = mock(HttpClient.class);
  ObjectMapper mapper = new ObjectMapper().findAndRegisterModules();
  String receipt =
      """
      {"merchant":"Fictional store","date":"2026-01-01","currency":"USD","items":[{"description":"Rice","rawDescription":"RICE","quantity":1,"unitPrice":100,"amount":100,"category":"Groceries","confidence":null}],"subtotal":100,"discounts":0,"tax":0,"fees":0,"total":100}
      """;

  OpenAiReceiptProvider provider() {
    return new OpenAiReceiptProvider(
        "fictional-key", "configured-model", mapper, client, Duration.ofMillis(100));
  }

  @SuppressWarnings("unchecked")
  void respond(int status, String text, String state) throws Exception {
    HttpResponse<byte[]> response = mock(HttpResponse.class);
    when(response.statusCode()).thenReturn(status);
    when(response.body())
        .thenReturn(
            mapper.writeValueAsBytes(
                java.util.Map.of(
                    "status",
                    state,
                    "output",
                    java.util.List.of(
                        java.util.Map.of(
                            "content",
                            java.util.List.of(
                                java.util.Map.of("type", "output_text", "text", text)))))));
    when(client.sendAsync(any(HttpRequest.class), any(HttpResponse.BodyHandler.class)))
        .thenReturn(CompletableFuture.completedFuture(response));
  }

  @Test
  void successfulVisionResponseIsOnlyPrivateDraftData() throws Exception {
    respond(200, receipt, "completed");
    var draft = provider().extract(new byte[] {1}, "image/png");
    assertThat(draft.total()).isEqualTo(100);
    assertThat(draft.householdId()).isNull();
    assertThat(draft.payerId()).isNull();
    assertThat(draft.items().getFirst().scope()).isEqualTo("PERSONAL");
    assertThat(draft.items().getFirst().participants()).isEmpty();
    var request = ArgumentCaptor.forClass(HttpRequest.class);
    verify(client).sendAsync(request.capture(), any());
    assertThat(request.getValue().uri().toString())
        .isEqualTo("https://api.openai.com/v1/responses");
    assertThat(request.getValue().headers().firstValue("Authorization"))
        .contains("Bearer fictional-key");
  }

  @Test
  void missingCredentialsNeverCallNetwork() {
    assertThatThrownBy(
            () ->
                new OpenAiReceiptProvider("", "", mapper, client, Duration.ofSeconds(1))
                    .extract(new byte[] {1}, "image/png"))
        .isInstanceOf(ApiException.class);
    verifyNoInteractions(client);
  }

  @Test
  void malformedMissingAndInvalidMoneyAreRejected() throws Exception {
    for (String malformed :
        java.util.List.of(
            "not JSON",
            receipt.replace("\"total\":100", "\"total\":null"),
            receipt.replace("\"total\":100", "\"total\":100.5"),
            receipt.replace("\"total\":100", "\"total\":\"100\""),
            receipt.replace("\"subtotal\":100,", ""),
            receipt.replace("\"rawDescription\":\"RICE\",", ""),
            receipt.replace("\"amount\":100", "\"amount\":-100"),
            receipt + "{}")) {
      respond(200, malformed, "completed");
      assertThatThrownBy(() -> provider().extract(new byte[] {1}, "image/png"))
          .isInstanceOf(ApiException.class);
    }
  }

  @Test
  void providerFailureAndIncompleteOutputAreSafe() throws Exception {
    respond(429, "sensitive upstream details", "failed");
    assertThatThrownBy(() -> provider().extract(new byte[] {1}, "image/png"))
        .hasMessageNotContaining("sensitive");
    respond(200, receipt, "incomplete");
    assertThatThrownBy(() -> provider().extract(new byte[] {1}, "image/png"))
        .isInstanceOf(ApiException.class);
  }

  @SuppressWarnings("unchecked")
  @Test
  void timeoutCancelsAndTransportFailureIsSafe() {
    CompletableFuture<HttpResponse<byte[]>> pending = new CompletableFuture<>();
    when(client.sendAsync(any(HttpRequest.class), any(HttpResponse.BodyHandler.class)))
        .thenReturn(pending);
    assertThatThrownBy(() -> provider().extract(new byte[] {1}, "image/png"))
        .isInstanceOf(ApiException.class);
    assertThat(pending.isCancelled()).isTrue();
    when(client.sendAsync(any(HttpRequest.class), any(HttpResponse.BodyHandler.class)))
        .thenReturn(CompletableFuture.failedFuture(new IllegalStateException("secret")));
    assertThatThrownBy(() -> provider().extract(new byte[] {1}, "image/png"))
        .hasMessageNotContaining("secret");
  }
}
