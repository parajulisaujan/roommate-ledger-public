package com.roommateledger;

import java.net.URI;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.*;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import org.springframework.web.cors.*;

@Configuration
public class SecurityConfig {
  @Bean
  PasswordEncoder passwordEncoder() {
    return new BCryptPasswordEncoder(12);
  }

  @Bean
  SecurityFilterChain security(
      HttpSecurity http,
      @org.springframework.beans.factory.annotation.Qualifier("corsConfigurationSource")
          CorsConfigurationSource cors,
      Store db,
      AbuseControl limits,
      @Value("${app.email.verification-required:false}") boolean verificationRequired)
      throws Exception {
    return http.cors(c -> c.configurationSource(cors))
        .addFilterAfter(
            new AccountSecurityFilter(db, limits, verificationRequired),
            org.springframework.security.web.authentication.AnonymousAuthenticationFilter.class)
        .authorizeHttpRequests(
            a ->
                a.requestMatchers(
                        "/api/auth/csrf",
                        "/api/auth/register",
                        "/api/auth/login",
                        "/api/health",
                        "/api/auth/capabilities",
                        "/api/auth/forgot-password",
                        "/api/auth/reset-password",
                        "/api/auth/verify-email",
                        "/actuator/health/liveness",
                        "/actuator/health/readiness")
                    .permitAll()
                    .anyRequest()
                    .authenticated())
        .csrf(c -> c.csrfTokenRepository(new HttpSessionCsrfTokenRepository()))
        .requestCache(c -> c.disable())
        .logout(
            l ->
                l.logoutUrl("/api/auth/logout")
                    .deleteCookies("JSESSIONID")
                    .logoutSuccessHandler((req, res, auth) -> res.setStatus(204)))
        .exceptionHandling(
            e ->
                e.authenticationEntryPoint(
                        (req, res, ex) -> {
                          res.setStatus(401);
                          res.setContentType("application/json");
                          res.getWriter()
                              .write("{\"code\":\"UNAUTHORIZED\",\"message\":\"Please sign in.\"}");
                        })
                    .accessDeniedHandler(
                        (req, res, ex) -> {
                          res.setStatus(403);
                          res.setContentType("application/json");
                          res.getWriter()
                              .write(
                                  "{\"code\":\"FORBIDDEN\",\"message\":\"Access denied or session"
                                      + " expired. Refresh and try again.\"}");
                        }))
        .build();
  }

  @Bean
  CorsConfigurationSource corsConfigurationSource(
      @Value("${app.cors.allowed-origins:}") String origins) {
    var source = new UrlBasedCorsConfigurationSource();
    if (origins.isBlank()) return source;
    var allowed = Arrays.stream(origins.split(",")).map(String::trim).toList();
    for (String origin : allowed) {
      URI uri = URI.create(origin);
      if (!Set.of("https", "http").contains(Objects.toString(uri.getScheme(), ""))
          || uri.getHost() == null
          || uri.getUserInfo() != null
          || uri.getQuery() != null
          || uri.getFragment() != null
          || !uri.getPath().isEmpty())
        throw new IllegalArgumentException(
            "CORS_ALLOWED_ORIGINS must contain exact HTTP(S) origins without paths or wildcards.");
    }
    var config = new CorsConfiguration();
    config.setAllowedOrigins(allowed);
    config.setAllowedMethods(List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"));
    config.setAllowedHeaders(List.of("Content-Type", "X-CSRF-TOKEN"));
    config.setAllowCredentials(true);
    config.setMaxAge(3600L);
    source.registerCorsConfiguration("/api/**", config);
    return source;
  }
}
