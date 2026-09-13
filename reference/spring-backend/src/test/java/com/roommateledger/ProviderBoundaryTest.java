package com.roommateledger;

import static org.assertj.core.api.Assertions.*;

import java.nio.ByteBuffer;
import java.util.List;
import java.util.concurrent.Flow;
import org.junit.jupiter.api.Test;

class ProviderBoundaryTest {
  static class Subscription implements Flow.Subscription {
    boolean cancelled;

    public void request(long n) {}

    public void cancel() {
      cancelled = true;
    }
  }

  @Test
  void largeResponsesAreCancelledBeforeBuffering() {
    var body = new HttpReceiptExtractionProvider.BoundedSubscriber();
    var subscription = new Subscription();
    body.onSubscribe(subscription);
    body.onNext(List.of(ByteBuffer.allocate(262145)));
    assertThat(subscription.cancelled).isTrue();
    assertThat(body.getBody().toCompletableFuture()).isCompletedExceptionally();
  }

  @Test
  void validResponseBodyPassesThrough() {
    var body = new HttpReceiptExtractionProvider.BoundedSubscriber();
    body.onSubscribe(new Subscription());
    body.onNext(List.of(ByteBuffer.wrap("{}".getBytes(java.nio.charset.StandardCharsets.UTF_8))));
    body.onComplete();
    assertThat(body.getBody().toCompletableFuture().join())
        .isEqualTo("{}".getBytes(java.nio.charset.StandardCharsets.UTF_8));
  }
}
