package com.roommateledger;

import java.time.Instant;
import java.util.*;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

/** Bounded single-instance limiter. Ingress must enforce per-client limits behind a proxy. */
@Component
class AbuseControl {
  private final Environment env;
  private final Map<String, Window> windows = new HashMap<>();

  private record Window(int count, long expires) {}

  AbuseControl(Environment env) {
    this.env = env;
  }

  synchronized void check(String group, String subject) {
    long now = Instant.now().getEpochSecond();
    windows.entrySet().removeIf(e -> e.getValue().expires <= now);
    int limit = env.getProperty("app.rate." + group, Integer.class, 20);
    int duration = env.getProperty("app.rate.window-seconds", Integer.class, 900);
    String key = group + ":" + AccountService.hash(subject);
    var old = windows.get(key);
    if (limit < 1
        || duration < 1
        || (old != null && old.count >= limit)
        || (old == null && windows.size() >= 10000))
      throw new ApiException(429, "RATE_LIMITED", "Too many requests. Wait before trying again.");
    windows.put(
        key,
        new Window(old == null ? 1 : old.count + 1, old == null ? now + duration : old.expires));
  }
}
