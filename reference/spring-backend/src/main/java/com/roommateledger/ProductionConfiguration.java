package com.roommateledger;

import java.net.URI;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.*;

@Configuration
@Profile({"production", "staging"})
class ProductionConfiguration {
  ProductionConfiguration(
      EmailProvider email,
      @Value("${app.frontend-url}") String frontend,
      @Value("${app.email.starttls:true}") boolean tls) {
    URI uri = URI.create(frontend);
    if (!"https".equals(uri.getScheme())
        || uri.getHost() == null
        || uri.getHost().equals("localhost")
        || uri.getHost().equals("127.0.0.1")
        || uri.getUserInfo() != null
        || uri.getQuery() != null
        || uri.getFragment() != null
        || !uri.getPath().isEmpty())
      throw new IllegalArgumentException(
          "FRONTEND_URL must be an exact public HTTPS origin in staging/production.");
    if (!email.available() || !tls)
      throw new IllegalArgumentException(
          "Staging/production requires configured email delivery with STARTTLS for account recovery"
              + " and verification.");
  }
}
