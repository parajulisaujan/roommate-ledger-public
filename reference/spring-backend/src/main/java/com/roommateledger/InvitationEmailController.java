package com.roommateledger;

import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.security.Principal;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.*;

@RestController
class InvitationEmailController {
  private final HouseholdService households;
  private final EmailProvider email;
  private final String frontend;

  InvitationEmailController(
      HouseholdService households,
      EmailProvider email,
      @Value("${app.frontend-url}") String frontend) {
    this.households = households;
    this.email = email;
    this.frontend = frontend;
  }

  record Address(@NotBlank @Email @Size(max = 254) String email) {}

  @PostMapping("/api/households/{id}/invitations/email")
  void send(Principal p, @PathVariable UUID id, @Valid @RequestBody Address address) {
    if (!email.available())
      throw new ApiException(
          503,
          "EMAIL_UNAVAILABLE",
          "Email delivery is unavailable. Share an invitation code instead.");
    var invitation = households.invite(AuthController.user(p), id);
    try {
      email.send(
          address.email(),
          "RoommateLedger household invitation",
          "Sign in or create your account at "
              + frontend
              + ". Open Household and enter this single-use code: "
              + invitation.get("token")
              + "\nThe code expires in 7 days.");
    } catch (RuntimeException e) {
      throw new ApiException(
          503,
          "EMAIL_UNAVAILABLE",
          "The email could not be delivered. Retry or share an invitation code.");
    }
  }
}
