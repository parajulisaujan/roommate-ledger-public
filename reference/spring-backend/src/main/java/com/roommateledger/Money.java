package com.roommateledger;

import java.math.*;
import java.util.*;

public final class Money {
  public static final long MAX = 100_000_000_000L;

  private Money() {}

  public static void positive(long cents) {
    if (cents <= 0 || cents > MAX)
      throw ApiException.invalid("Amount must be positive and at most $1 billion.");
  }

  public static Map<UUID, Long> split(
      long total, String method, List<UUID> participants, Map<UUID, Long> values) {
    positive(total);
    if (participants == null
        || participants.isEmpty()
        || participants.size() > 100
        || participants.stream().anyMatch(Objects::isNull)
        || new HashSet<>(participants).size() != participants.size())
      throw ApiException.invalid("Choose between 1 and 100 unique participants.");
    var ids = participants.stream().sorted().toList();
    var result = new LinkedHashMap<UUID, Long>();
    if ("EQUAL".equals(method)) {
      for (int i = 0; i < ids.size(); i++)
        result.put(ids.get(i), total / ids.size() + (i < total % ids.size() ? 1L : 0L));
    } else {
      if (values == null
          || !values.keySet().equals(new HashSet<>(ids))
          || values.values().stream().anyMatch(v -> v == null || v < 0 || v > MAX))
        throw ApiException.invalid("Provide one nonnegative value for every participant.");
      long sum = values.values().stream().mapToLong(Long::longValue).sum();
      if ("FIXED".equals(method)) {
        if (sum != total) throw ApiException.invalid("Fixed shares must equal the total.");
        result.putAll(values);
      } else if ("PERCENTAGE".equals(method)) {
        if (sum != 10000) throw ApiException.invalid("Percentages must total exactly 100.00%.");
        long allocated = 0;
        for (UUID id : ids) {
          long share =
              BigInteger.valueOf(total)
                  .multiply(BigInteger.valueOf(values.get(id)))
                  .divide(BigInteger.valueOf(10000))
                  .longValueExact();
          result.put(id, share);
          allocated += share;
        }
        var remainderOrder =
            ids.stream()
                .sorted(
                    Comparator.<UUID, BigInteger>comparing(
                            id ->
                                BigInteger.valueOf(total)
                                    .multiply(BigInteger.valueOf(values.get(id)))
                                    .remainder(BigInteger.valueOf(10000)))
                        .reversed()
                        .thenComparing(Comparator.naturalOrder()))
                .toList();
        for (int i = 0; i < total - allocated; i++)
          result.compute(remainderOrder.get(i), (k, v) -> v + 1);
      } else throw ApiException.invalid("Unknown split method.");
    }
    return result;
  }
}
