package com.roommateledger;

import com.fasterxml.jackson.databind.*;
import java.net.URI;
import java.net.http.*;
import java.nio.ByteBuffer;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/**
 * Connects to a configured vision adapter; the contract is documented in docs/receipt-provider.md.
 */
@Component
@org.springframework.boot.autoconfigure.condition.ConditionalOnProperty(
    name = "app.receipt.provider",
    havingValue = "adapter",
    matchIfMissing = true)
public class HttpReceiptExtractionProvider implements ReceiptExtractionProvider {
  private final String endpoint, key;
  private final ObjectMapper mapper;
  private final HttpClient client;
  private final Duration timeout;

  @Autowired
  public HttpReceiptExtractionProvider(
      @Value("${app.receipt.endpoint}") String endpoint,
      @Value("${app.receipt.api-key}") String key,
      ObjectMapper mapper) {
    this(
        endpoint,
        key,
        mapper,
        HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build(),
        Duration.ofSeconds(45));
  }

  HttpReceiptExtractionProvider(
      String endpoint, String key, ObjectMapper mapper, HttpClient client, Duration timeout) {
    this.endpoint = endpoint;
    this.key = key;
    this.client = client;
    this.timeout = timeout;
    this.mapper =
        mapper
            .copy()
            .enable(
                DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES,
                DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES,
                DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
            .disable(
                DeserializationFeature.ACCEPT_FLOAT_AS_INT,
                DeserializationFeature.ACCEPT_EMPTY_STRING_AS_NULL_OBJECT);
    this.mapper.disable(MapperFeature.ALLOW_COERCION_OF_SCALARS);
    if (!endpoint.isBlank() && !key.isBlank()) {
      URI uri;
      try {
        uri = URI.create(endpoint);
      } catch (IllegalArgumentException e) {
        throw new IllegalArgumentException("Receipt provider must use an absolute HTTPS URL.");
      }
      if (!"https".equals(uri.getScheme())
          || uri.getHost() == null
          || uri.getUserInfo() != null
          || uri.getFragment() != null)
        throw new IllegalArgumentException(
            "Receipt provider must use an absolute HTTPS URL without embedded credentials or"
                + " fragments.");
    }
  }

  public boolean available() {
    return !endpoint.isBlank() && !key.isBlank();
  }

  public ReceiptService.Draft extract(byte[] image, String mime) {
    if (!available())
      throw new ApiException(
          503,
          "EXTRACTION_UNAVAILABLE",
          "Automated extraction is not configured. Enter receipt items manually.");
    try {
      URI uri = URI.create(endpoint);
      if (!"https".equals(uri.getScheme())) throw new IllegalStateException("HTTPS required");
      var request =
          HttpRequest.newBuilder(uri)
              .timeout(timeout)
              .header("Content-Type", mime)
              .header("Authorization", "Bearer " + key)
              .POST(HttpRequest.BodyPublishers.ofByteArray(image))
              .build();
      var pending = client.sendAsync(request, info -> new BoundedSubscriber());
      try {
        var response = pending.get(timeout.toMillis(), TimeUnit.MILLISECONDS);
        byte[] bytes = response.body();
        if (response.statusCode() != 200) throw new IllegalStateException("Invalid response");
        var draft = mapper.readValue(bytes, ReceiptService.Draft.class);
        ReceiptService.validateDraft(draft, false);
        // Provider output may describe items, but never determines participants or scope.
        var items =
            draft.items().stream()
                .map(
                    i ->
                        new ReceiptService.Item(
                            i.description(),
                            i.rawDescription(),
                            i.quantity(),
                            i.unitPrice(),
                            i.amount(),
                            i.category(),
                            i.confidence(),
                            "PERSONAL",
                            java.util.List.of()))
                .toList();
        return new ReceiptService.Draft(
            draft.merchant(),
            draft.date(),
            "USD",
            null,
            null,
            items,
            draft.subtotal(),
            draft.discounts(),
            draft.tax(),
            draft.fees(),
            draft.total());
      } finally {
        if (!pending.isDone()) pending.cancel(true);
      }
    } catch (Exception e) {
      if (e instanceof InterruptedException) Thread.currentThread().interrupt();
      throw new ApiException(
          502,
          "RECEIPT_EXTRACTION_FAILED",
          "Extraction could not be completed. Retry the upload or enter items manually.");
    }
  }

  /** Bound the body before buffering; the overall future deadline also covers a stalled body. */
  static final class BoundedSubscriber implements HttpResponse.BodySubscriber<byte[]> {
    private final HttpResponse.BodySubscriber<byte[]> delegate =
        HttpResponse.BodySubscribers.ofByteArray();
    private Flow.Subscription subscription;
    private long received;
    private boolean rejected;

    public CompletionStage<byte[]> getBody() {
      return delegate.getBody();
    }

    public void onSubscribe(Flow.Subscription subscription) {
      this.subscription = subscription;
      delegate.onSubscribe(subscription);
    }

    public void onNext(List<ByteBuffer> buffers) {
      if (rejected) return;
      received += buffers.stream().mapToLong(ByteBuffer::remaining).sum();
      if (received > 262144) {
        rejected = true;
        subscription.cancel();
        delegate.onError(new IllegalStateException("Receipt response exceeds limit"));
      } else delegate.onNext(buffers);
    }

    public void onError(Throwable error) {
      delegate.onError(error);
    }

    public void onComplete() {
      if (!rejected) delegate.onComplete();
    }
  }
}
