package com.roommateledger;

public interface EmailProvider {
  boolean available();

  void send(String recipient, String subject, String text);
}
