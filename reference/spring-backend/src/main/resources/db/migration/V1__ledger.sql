CREATE TABLE app_user (
 id UUID PRIMARY KEY, name VARCHAR(80) NOT NULL, email VARCHAR(254) NOT NULL UNIQUE,
 password_hash VARCHAR(100) NOT NULL, diet VARCHAR(32) NOT NULL DEFAULT 'No restriction',
 timezone VARCHAR(60) NOT NULL DEFAULT 'America/Chicago', currency CHAR(3) NOT NULL DEFAULT 'USD' CHECK(currency = 'USD'),
 notifications BOOLEAN NOT NULL DEFAULT false, created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE household (
 id UUID PRIMARY KEY, name VARCHAR(80) NOT NULL, created_by UUID NOT NULL REFERENCES app_user(id),
 created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE membership (
 id UUID PRIMARY KEY, household_id UUID NOT NULL REFERENCES household(id), user_id UUID NOT NULL REFERENCES app_user(id),
 role VARCHAR(10) NOT NULL CHECK(role IN ('OWNER','MEMBER')), joined_at DATE NOT NULL, left_at DATE,
 CHECK(left_at IS NULL OR left_at >= joined_at)
);
CREATE INDEX membership_lookup ON membership(household_id,user_id,joined_at,left_at);
CREATE TABLE invitation (
 id UUID PRIMARY KEY, household_id UUID NOT NULL REFERENCES household(id), token_hash VARCHAR(64) NOT NULL UNIQUE,
 expires_at TIMESTAMP WITH TIME ZONE NOT NULL, accepted_by UUID REFERENCES app_user(id)
);
CREATE TABLE receipt (
 id UUID PRIMARY KEY, owner_id UUID NOT NULL REFERENCES app_user(id), status VARCHAR(20) NOT NULL CHECK(status IN ('UPLOADED','PROCESSING','NEEDS_REVIEW','CONFIRMED','FAILED')),
 fingerprint VARCHAR(64), draft TEXT NOT NULL, error VARCHAR(300), created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX receipt_owner ON receipt(owner_id,created_at);
CREATE TABLE recurring_template (
 id UUID PRIMARY KEY, owner_id UUID NOT NULL REFERENCES app_user(id), household_id UUID REFERENCES household(id),
 draft TEXT NOT NULL, next_due DATE NOT NULL, frequency VARCHAR(10) NOT NULL CHECK(frequency IN ('MONTHLY','WEEKLY','YEARLY')),
 active BOOLEAN NOT NULL DEFAULT true
);
CREATE TABLE expense (
 id UUID PRIMARY KEY, owner_id UUID NOT NULL REFERENCES app_user(id), household_id UUID REFERENCES household(id),
 payer_id UUID NOT NULL REFERENCES app_user(id), title VARCHAR(120) NOT NULL, merchant VARCHAR(120),
 amount BIGINT NOT NULL CHECK(amount > 0 AND amount <= 100000000000), currency CHAR(3) NOT NULL DEFAULT 'USD' CHECK(currency = 'USD'),
 category VARCHAR(40) NOT NULL, scope VARCHAR(20) NOT NULL CHECK(scope IN ('PERSONAL','HOUSEHOLD','SELECTED_MEMBERS')),
 split_method VARCHAR(12) NOT NULL CHECK(split_method IN ('EQUAL','FIXED','PERCENTAGE')), expense_date DATE NOT NULL,
 notes VARCHAR(2000), receipt_id UUID REFERENCES receipt(id), template_id UUID REFERENCES recurring_template(id),
 deleted BOOLEAN NOT NULL DEFAULT false, version INTEGER NOT NULL DEFAULT 0,
 created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
 CHECK((scope = 'PERSONAL' AND household_id IS NULL AND payer_id = owner_id) OR (scope <> 'PERSONAL' AND household_id IS NOT NULL)),
 UNIQUE(template_id,expense_date)
);
CREATE INDEX expense_household_date ON expense(household_id,expense_date);
CREATE INDEX expense_owner_date ON expense(owner_id,expense_date);
CREATE TABLE allocation (
 expense_id UUID NOT NULL REFERENCES expense(id), user_id UUID NOT NULL REFERENCES app_user(id),
 amount BIGINT NOT NULL CHECK(amount >= 0), PRIMARY KEY(expense_id,user_id)
);
CREATE INDEX allocation_user ON allocation(user_id,expense_id);
CREATE TABLE settlement (
 id UUID PRIMARY KEY, household_id UUID NOT NULL REFERENCES household(id), from_user UUID NOT NULL REFERENCES app_user(id),
 to_user UUID NOT NULL REFERENCES app_user(id), amount BIGINT NOT NULL CHECK(amount > 0 AND amount <= 100000000000),
 method VARCHAR(40) NOT NULL, payment_date DATE NOT NULL, created_by UUID NOT NULL REFERENCES app_user(id),
 created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP, CHECK(from_user <> to_user)
);
CREATE TABLE audit_event (
 id UUID PRIMARY KEY, household_id UUID REFERENCES household(id), actor_id UUID NOT NULL REFERENCES app_user(id),
 action VARCHAR(50) NOT NULL, entity_id UUID NOT NULL, created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
