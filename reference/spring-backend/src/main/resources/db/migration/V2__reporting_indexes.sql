CREATE INDEX settlement_household_sender ON settlement(household_id, from_user);
CREATE INDEX settlement_household_recipient ON settlement(household_id, to_user);
CREATE INDEX audit_household_created ON audit_event(household_id, created_at);
CREATE INDEX recurring_household_due ON recurring_template(household_id, next_due);
CREATE INDEX recurring_owner_due ON recurring_template(owner_id, next_due);
