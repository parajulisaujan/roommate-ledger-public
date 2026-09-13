package com.roommateledger;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.stereotype.Component;

@Component
class SmtpEmailProvider implements EmailProvider {
  private final JavaMailSenderImpl sender = new JavaMailSenderImpl();
  private final String from;

  SmtpEmailProvider(
      @Value("${app.email.host:}") String host,
      @Value("${app.email.port:587}") int port,
      @Value("${app.email.username:}") String username,
      @Value("${app.email.password:}") String password,
      @Value("${app.email.from:}") String from,
      @Value("${app.email.starttls:true}") boolean tls) {
    this.from = from;
    sender.setHost(host);
    sender.setPort(port);
    sender.setUsername(username);
    sender.setPassword(password);
    var p = sender.getJavaMailProperties();
    p.setProperty("mail.smtp.auth", Boolean.toString(!username.isBlank()));
    p.setProperty("mail.smtp.starttls.enable", Boolean.toString(tls));
    p.setProperty("mail.smtp.starttls.required", Boolean.toString(tls));
    p.setProperty("mail.smtp.ssl.checkserveridentity", "true");
    p.setProperty("mail.smtp.connectiontimeout", "5000");
    p.setProperty("mail.smtp.timeout", "5000");
    p.setProperty("mail.smtp.writetimeout", "5000");
  }

  public boolean available() {
    return sender.getHost() != null && !sender.getHost().isBlank() && !from.isBlank();
  }

  public void send(String recipient, String subject, String text) {
    if (!available()) throw new IllegalStateException("Email delivery is unavailable.");
    var message = new SimpleMailMessage();
    message.setFrom(from);
    message.setTo(recipient);
    message.setSubject(subject);
    message.setText(text);
    sender.send(message);
  }
}
