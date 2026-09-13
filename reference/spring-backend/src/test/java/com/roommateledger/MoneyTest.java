package com.roommateledger;

import static org.assertj.core.api.Assertions.*;

import java.util.*;
import org.junit.jupiter.api.Test;

class MoneyTest {
  final UUID a = new UUID(0, 1), b = new UUID(0, 2), c = new UUID(0, 3), d = new UUID(0, 4);

  @Test
  void equalFourAndThree() {
    assertThat(Money.split(10000, "EQUAL", List.of(a, b, c, d), null).values()).containsOnly(2500L);
    assertThat(Money.split(10000, "EQUAL", List.of(c, b, a), null))
        .containsEntry(a, 3334L)
        .containsEntry(b, 3333L)
        .containsEntry(c, 3333L);
    assertThat(Money.split(9000, "EQUAL", List.of(a, b, c), null).values()).containsOnly(3000L);
    assertThat(Money.split(4000, "EQUAL", List.of(a), null)).containsEntry(a, 4000L);
  }

  @Test
  void fixedAndPercentage() {
    assertThat(
            Money.split(
                10000, "PERCENTAGE", List.of(a, b, c), Map.of(a, 5000L, b, 3000L, c, 2000L)))
        .containsEntry(a, 5000L)
        .containsEntry(b, 3000L)
        .containsEntry(c, 2000L);
    assertThat(Money.split(1, "PERCENTAGE", List.of(a, b), Map.of(a, 0L, b, 10000L)))
        .containsEntry(a, 0L)
        .containsEntry(b, 1L);
    assertThatThrownBy(() -> Money.split(100, "FIXED", List.of(a, b), Map.of(a, 10L, b, 10L)))
        .isInstanceOf(ApiException.class);
    assertThatThrownBy(
            () -> Money.split(100, "PERCENTAGE", List.of(a, b), Map.of(a, 4000L, b, 4000L)))
        .isInstanceOf(ApiException.class);
    assertThatThrownBy(() -> Money.split(100, "EQUAL", List.of(a, a), null))
        .isInstanceOf(ApiException.class);
    assertThatThrownBy(() -> Money.split(-1, "EQUAL", List.of(a), null))
        .isInstanceOf(ApiException.class);
  }

  @Test
  void conservedAcrossManyAmounts() {
    for (long total = 1; total < 10000; total += 17) {
      var result =
          Money.split(total, "PERCENTAGE", List.of(a, b, c), Map.of(a, 3333L, b, 3333L, c, 3334L));
      assertThat(result.values().stream().mapToLong(Long::longValue).sum()).isEqualTo(total);
    }
  }
}
