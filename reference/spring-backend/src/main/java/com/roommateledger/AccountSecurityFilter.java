package com.roommateledger;

import jakarta.servlet.*;
import jakarta.servlet.http.*;
import java.io.IOException;
import java.util.*;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

class AccountSecurityFilter extends OncePerRequestFilter {
  private final Store db;
  private final AbuseControl limits;
  private final boolean requireVerification;

  AccountSecurityFilter(Store db, AbuseControl limits, boolean requireVerification) {
    this.db = db;
    this.limits = limits;
    this.requireVerification = requireVerification;
  }

  protected void doFilterInternal(
      HttpServletRequest req, HttpServletResponse res, FilterChain chain)
      throws ServletException, IOException {
    try {
      var auth = SecurityContextHolder.getContext().getAuthentication();
      boolean signed =
          auth != null && auth.isAuthenticated() && !(auth instanceof AnonymousAuthenticationToken);
      String path = req.getRequestURI();
      if (signed) {
        var rows =
            db.list(
                "SELECT deactivated,session_version,email_verified FROM app_user WHERE id=?",
                UUID.fromString(auth.getName()));
        long version = auth.getDetails() instanceof Long v ? v : 0;
        if (rows.isEmpty()
            || Boolean.TRUE.equals(rows.getFirst().get("deactivated"))
            || Store.number(rows.getFirst().get("session_version")) != version) {
          if (req.getSession(false) != null) req.getSession(false).invalidate();
          SecurityContextHolder.clearContext();
          throw new ApiException(401, "UNAUTHORIZED", "Your session ended. Sign in again.");
        }
        if (requireVerification
            && !Boolean.TRUE.equals(rows.getFirst().get("email_verified"))
            && !path.startsWith("/api/auth/")
            && !path.startsWith("/api/account/")
            && !path.equals("/api/profile"))
          throw new ApiException(
              403,
              "EMAIL_UNVERIFIED",
              "Verify your email to use your ledger. Open Settings to resend the link.");
      }
      if (req.getMethod().equals("POST")) {
        String group =
            switch (path) {
              case "/api/auth/login" -> "login";
              case "/api/auth/register" -> "registration";
              case "/api/auth/forgot-password" -> "forgot";
              case "/api/auth/reset-password" -> "reset";
              case "/api/auth/verify-email", "/api/account/resend-verification" -> "verification";
              case "/api/receipts/extract" -> "extraction";
              case "/api/account/password", "/api/account/deactivate" -> "account";
              default ->
                  path.matches("/api/households/[^/]+/invitations(?:/email)?")
                      ? "invitations"
                      : null;
            };
        if (group != null) limits.check(group, signed ? auth.getName() : req.getRemoteAddr());
      }
      chain.doFilter(req, res);
    } catch (ApiException e) {
      res.setStatus(e.status);
      res.setContentType("application/json");
      if (e.status == 429) res.setHeader("Retry-After", "900");
      res.getWriter().write("{\"code\":\"" + e.code + "\",\"message\":\"" + e.getMessage() + "\"}");
    }
  }
}
