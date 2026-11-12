-- ACbridge backend schema (SQLite flavour of app/models.py)

CREATE TABLE artisan_profiles (
	artisan_id CHAR(32) NOT NULL, 
	user_id CHAR(32) NOT NULL, 
	full_name VARCHAR(120) NOT NULL, 
	location VARCHAR(160) NOT NULL, 
	description TEXT, 
	whatsapp_number VARCHAR(20), 
	availability_status VARCHAR(16) DEFAULT 'AVAILABLE' NOT NULL, 
	is_suspended BOOLEAN DEFAULT 'false' NOT NULL, 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_artisan_profiles PRIMARY KEY (artisan_id), 
	CONSTRAINT ck_artisan_profiles_availability_valid CHECK (availability_status IN ('AVAILABLE', 'BUSY', 'UNAVAILABLE')), 
	CONSTRAINT uq_artisan_profiles_user_id UNIQUE (user_id), 
	CONSTRAINT fk_artisan_profiles_user_id_users FOREIGN KEY(user_id) REFERENCES users (user_id)
);

CREATE TABLE artisan_skills (
	artisan_id CHAR(32) NOT NULL, 
	skill_id CHAR(32) NOT NULL, 
	proficiency_level VARCHAR(16) NOT NULL, 
	verification_status VARCHAR(16) DEFAULT 'UNVERIFIED' NOT NULL, 
	typical_price INTEGER, 
	CONSTRAINT pk_artisan_skills PRIMARY KEY (artisan_id, skill_id), 
	CONSTRAINT ck_artisan_skills_proficiency_valid CHECK (proficiency_level IN ('BEGINNER', 'INTERMEDIATE', 'EXPERT')), 
	CONSTRAINT ck_artisan_skills_verification_valid CHECK (verification_status IN ('UNVERIFIED', 'PENDING', 'VERIFIED', 'REJECTED')), 
	CONSTRAINT ck_artisan_skills_price_non_negative CHECK (typical_price IS NULL OR typical_price >= 0), 
	CONSTRAINT fk_artisan_skills_artisan_id_artisan_profiles FOREIGN KEY(artisan_id) REFERENCES artisan_profiles (artisan_id), 
	CONSTRAINT fk_artisan_skills_skill_id_skills FOREIGN KEY(skill_id) REFERENCES skills (skill_id)
);

CREATE TABLE audit_log (
	audit_id CHAR(32) NOT NULL, 
	actor_type VARCHAR(12) NOT NULL, 
	actor_id VARCHAR(40), 
	action VARCHAR(40) NOT NULL, 
	target VARCHAR(80) NOT NULL, 
	payload_hash VARCHAR(64) NOT NULL, 
	timestamp DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_audit_log PRIMARY KEY (audit_id)
);

CREATE TABLE endorsements (
	endorsement_id CHAR(32) NOT NULL, 
	artisan_id CHAR(32) NOT NULL, 
	endorser_id CHAR(32) NOT NULL, 
	evidence_description TEXT NOT NULL, 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_endorsements PRIMARY KEY (endorsement_id), 
	CONSTRAINT uq_endorsements_artisan_endorser UNIQUE (artisan_id, endorser_id), 
	CONSTRAINT fk_endorsements_artisan_id_artisan_profiles FOREIGN KEY(artisan_id) REFERENCES artisan_profiles (artisan_id), 
	CONSTRAINT fk_endorsements_endorser_id_users FOREIGN KEY(endorser_id) REFERENCES users (user_id)
);

CREATE TABLE hardship_claims (
	claim_id CHAR(32) NOT NULL, 
	job_id CHAR(32) NOT NULL, 
	claimant_id CHAR(32) NOT NULL, 
	kind VARCHAR(32) NOT NULL, 
	affected_party VARCHAR(16) NOT NULL, 
	description TEXT NOT NULL, 
	document_path VARCHAR(255), 
	status VARCHAR(16) DEFAULT 'PENDING' NOT NULL, 
	decided_by CHAR(32), 
	decision_notes TEXT, 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	decided_at DATETIME, 
	CONSTRAINT pk_hardship_claims PRIMARY KEY (claim_id), 
	CONSTRAINT ck_hardship_claims_kind_valid CHECK (kind IN ('DEATH', 'ACCIDENT_OR_SERIOUS_ILLNESS')), 
	CONSTRAINT ck_hardship_claims_party_valid CHECK (affected_party IN ('CUSTOMER', 'ARTISAN')), 
	CONSTRAINT ck_hardship_claims_status_valid CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED')), 
	CONSTRAINT ck_hardship_claims_approved_needs_document CHECK (status <> 'APPROVED' OR document_path IS NOT NULL), 
	CONSTRAINT fk_hardship_claims_job_id_jobs FOREIGN KEY(job_id) REFERENCES jobs (job_id), 
	CONSTRAINT fk_hardship_claims_claimant_id_users FOREIGN KEY(claimant_id) REFERENCES users (user_id), 
	CONSTRAINT fk_hardship_claims_decided_by_users FOREIGN KEY(decided_by) REFERENCES users (user_id)
);

CREATE TABLE job_events (
	event_id CHAR(32) NOT NULL, 
	job_id CHAR(32) NOT NULL, 
	actor_id CHAR(32) NOT NULL, 
	event_type VARCHAR(40) NOT NULL, 
	event_metadata JSON, 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_job_events PRIMARY KEY (event_id), 
	CONSTRAINT fk_job_events_job_id_jobs FOREIGN KEY(job_id) REFERENCES jobs (job_id), 
	CONSTRAINT fk_job_events_actor_id_users FOREIGN KEY(actor_id) REFERENCES users (user_id)
);

CREATE TABLE job_messages (
	message_id CHAR(32) NOT NULL, 
	job_id CHAR(32) NOT NULL, 
	sender_id CHAR(32) NOT NULL, 
	sender_role VARCHAR(8) NOT NULL, 
	body TEXT NOT NULL, 
	proposed_price INTEGER, 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_job_messages PRIMARY KEY (message_id), 
	CONSTRAINT ck_job_messages_body_length CHECK (length(body) BETWEEN 1 AND 500), 
	CONSTRAINT ck_job_messages_sender_role_valid CHECK (sender_role IN ('CUSTOMER', 'ARTISAN')), 
	CONSTRAINT ck_job_messages_proposed_price_positive CHECK (proposed_price IS NULL OR proposed_price > 0), 
	CONSTRAINT fk_job_messages_job_id_jobs FOREIGN KEY(job_id) REFERENCES jobs (job_id), 
	CONSTRAINT fk_job_messages_sender_id_users FOREIGN KEY(sender_id) REFERENCES users (user_id)
);

CREATE TABLE jobs (
	job_id CHAR(32) NOT NULL, 
	request_id CHAR(32) NOT NULL, 
	artisan_id CHAR(32) NOT NULL, 
	pricing_mode VARCHAR(24) DEFAULT 'FIXED_PRICE' NOT NULL, 
	proposed_price INTEGER, 
	proposed_by VARCHAR(8), 
	agreed_price INTEGER, 
	terms_agreed_at DATETIME, 
	probation_ends_at DATETIME, 
	artisan_agreed BOOLEAN DEFAULT 'false' NOT NULL, 
	status VARCHAR(24) DEFAULT 'REQUESTED' NOT NULL, 
	customer_confirmed BOOLEAN DEFAULT 'false' NOT NULL, 
	artisan_confirmed BOOLEAN DEFAULT 'false' NOT NULL, 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	completed_at DATETIME, 
	CONSTRAINT pk_jobs PRIMARY KEY (job_id), 
	CONSTRAINT ck_jobs_status_valid CHECK (status IN ('REQUESTED', 'ACCEPTED', 'IN_PROGRESS', 'PENDING_CONFIRMATION', 'COMPLETED', 'DISPUTED', 'CANCELLED')), 
	CONSTRAINT ck_jobs_pricing_mode_valid CHECK (pricing_mode IN ('FIXED_PRICE', 'INSPECTION_REQUIRED')), 
	CONSTRAINT ck_jobs_price_non_negative CHECK (agreed_price IS NULL OR agreed_price >= 0), 
	CONSTRAINT ck_jobs_proposed_price_non_negative CHECK (proposed_price IS NULL OR proposed_price >= 0), 
	CONSTRAINT ck_jobs_started_needs_agreed_price CHECK (status NOT IN ('IN_PROGRESS', 'PENDING_CONFIRMATION', 'COMPLETED') OR agreed_price IS NOT NULL), 
	CONSTRAINT ck_jobs_completed_needs_both_confirmations CHECK (status <> 'COMPLETED' OR (customer_confirmed = true AND artisan_confirmed = true AND completed_at IS NOT NULL)), 
	CONSTRAINT uq_jobs_request_id UNIQUE (request_id), 
	CONSTRAINT fk_jobs_request_id_service_requests FOREIGN KEY(request_id) REFERENCES service_requests (request_id), 
	CONSTRAINT fk_jobs_artisan_id_artisan_profiles FOREIGN KEY(artisan_id) REFERENCES artisan_profiles (artisan_id)
);

CREATE TABLE ledger_entries (
	entry_id CHAR(32) NOT NULL, 
	tx_key VARCHAR(100) NOT NULL, 
	payment_id CHAR(32), 
	payout_id CHAR(32), 
	account VARCHAR(20) NOT NULL, 
	direction VARCHAR(6) NOT NULL, 
	amount INTEGER NOT NULL, 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_ledger_entries PRIMARY KEY (entry_id), 
	CONSTRAINT ck_ledger_entries_account_valid CHECK (account IN ('collection', 'platform_revenue', 'artisan_pending', 'artisan_paid', 'refund_payable')), 
	CONSTRAINT ck_ledger_entries_direction_valid CHECK (direction IN ('DEBIT', 'CREDIT')), 
	CONSTRAINT ck_ledger_entries_amount_positive CHECK (amount > 0), 
	CONSTRAINT uq_ledger_tx_line UNIQUE (tx_key, account, direction), 
	CONSTRAINT fk_ledger_entries_payment_id_payments FOREIGN KEY(payment_id) REFERENCES payments (payment_id), 
	CONSTRAINT fk_ledger_entries_payout_id_payouts FOREIGN KEY(payout_id) REFERENCES payouts (payout_id)
);

CREATE TABLE payments (
	payment_id CHAR(32) NOT NULL, 
	job_id CHAR(32) NOT NULL, 
	payer_id CHAR(32) NOT NULL, 
	payment_type VARCHAR(16) NOT NULL, 
	amount INTEGER NOT NULL, 
	currency VARCHAR(3) DEFAULT 'XAF' NOT NULL, 
	status VARCHAR(16) DEFAULT 'PENDING' NOT NULL, 
	provider VARCHAR(24) NOT NULL, 
	provider_reference VARCHAR(64), 
	description VARCHAR(200), 
	idempotency_key VARCHAR(80), 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	settled_at DATETIME, 
	CONSTRAINT pk_payments PRIMARY KEY (payment_id), 
	CONSTRAINT ck_payments_type_valid CHECK (payment_type IN ('COMMISSION', 'ASSIGNMENT_FEE', 'JOB_PAYMENT')), 
	CONSTRAINT ck_payments_status_valid CHECK (status IN ('PENDING', 'SUCCEEDED', 'FAILED', 'RELEASED', 'REFUNDED')), 
	CONSTRAINT ck_payments_amount_positive CHECK (amount > 0), 
	CONSTRAINT fk_payments_job_id_jobs FOREIGN KEY(job_id) REFERENCES jobs (job_id), 
	CONSTRAINT fk_payments_payer_id_users FOREIGN KEY(payer_id) REFERENCES users (user_id)
);

CREATE TABLE payouts (
	payout_id CHAR(32) NOT NULL, 
	job_id CHAR(32) NOT NULL, 
	artisan_id CHAR(32) NOT NULL, 
	payment_id CHAR(32) NOT NULL, 
	amount INTEGER NOT NULL, 
	commission INTEGER DEFAULT '0' NOT NULL, 
	status VARCHAR(10) DEFAULT 'PENDING' NOT NULL, 
	provider_reference VARCHAR(64), 
	note VARCHAR(300), 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_payouts PRIMARY KEY (payout_id), 
	CONSTRAINT ck_payouts_status_valid CHECK (status IN ('PENDING', 'RELEASED', 'HELD', 'PAID', 'FAILED')), 
	CONSTRAINT ck_payouts_amount_positive CHECK (amount > 0), 
	CONSTRAINT ck_payouts_commission_non_negative CHECK (commission >= 0), 
	CONSTRAINT uq_payouts_job_id UNIQUE (job_id), 
	CONSTRAINT fk_payouts_job_id_jobs FOREIGN KEY(job_id) REFERENCES jobs (job_id), 
	CONSTRAINT fk_payouts_artisan_id_artisan_profiles FOREIGN KEY(artisan_id) REFERENCES artisan_profiles (artisan_id), 
	CONSTRAINT fk_payouts_payment_id_payments FOREIGN KEY(payment_id) REFERENCES payments (payment_id)
);

CREATE TABLE reviews (
	review_id CHAR(32) NOT NULL, 
	job_id CHAR(32) NOT NULL, 
	reviewer_id CHAR(32) NOT NULL, 
	rating SMALLINT NOT NULL, 
	comment TEXT, 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_reviews PRIMARY KEY (review_id), 
	CONSTRAINT ck_reviews_rating_range CHECK (rating BETWEEN 1 AND 5), 
	CONSTRAINT uq_reviews_job_reviewer UNIQUE (job_id, reviewer_id), 
	CONSTRAINT fk_reviews_job_id_jobs FOREIGN KEY(job_id) REFERENCES jobs (job_id), 
	CONSTRAINT fk_reviews_reviewer_id_users FOREIGN KEY(reviewer_id) REFERENCES users (user_id)
);

CREATE TABLE service_requests (
	request_id CHAR(32) NOT NULL, 
	customer_id CHAR(32) NOT NULL, 
	skill_id CHAR(32) NOT NULL, 
	description TEXT NOT NULL, 
	location VARCHAR(160) NOT NULL, 
	budget INTEGER, 
	needs_inspection BOOLEAN DEFAULT 'false' NOT NULL, 
	urgency VARCHAR(12) DEFAULT 'NOT_URGENT' NOT NULL, 
	status VARCHAR(16) DEFAULT 'OPEN' NOT NULL, 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_service_requests PRIMARY KEY (request_id), 
	CONSTRAINT ck_service_requests_status_valid CHECK (status IN ('OPEN', 'MATCHED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')), 
	CONSTRAINT ck_service_requests_budget_non_negative CHECK (budget IS NULL OR budget >= 0), 
	CONSTRAINT ck_service_requests_urgency_valid CHECK (urgency IN ('TODAY', 'THIS_WEEK', 'NOT_URGENT')), 
	CONSTRAINT fk_service_requests_customer_id_users FOREIGN KEY(customer_id) REFERENCES users (user_id), 
	CONSTRAINT fk_service_requests_skill_id_skills FOREIGN KEY(skill_id) REFERENCES skills (skill_id)
);

CREATE TABLE skills (
	skill_id CHAR(32) NOT NULL, 
	skill_name VARCHAR(80) NOT NULL, 
	description TEXT, 
	safety_critical BOOLEAN DEFAULT 'false' NOT NULL, 
	CONSTRAINT pk_skills PRIMARY KEY (skill_id), 
	CONSTRAINT uq_skills_skill_name UNIQUE (skill_name)
);

CREATE TABLE users (
	user_id CHAR(32) NOT NULL, 
	phone VARCHAR(20) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	role VARCHAR(16) NOT NULL, 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_users PRIMARY KEY (user_id), 
	CONSTRAINT ck_users_role_valid CHECK (role IN ('CUSTOMER', 'ARTISAN', 'VERIFIER', 'ADMIN')), 
	CONSTRAINT uq_users_phone UNIQUE (phone)
);

CREATE TABLE verification_checks (
	check_id CHAR(32) NOT NULL, 
	artisan_id CHAR(32) NOT NULL, 
	skill_id CHAR(32), 
	verifier_id CHAR(32), 
	check_type VARCHAR(16) NOT NULL, 
	status VARCHAR(24) DEFAULT 'PENDING' NOT NULL, 
	evidence_description TEXT NOT NULL, 
	evidence_file_path VARCHAR(255), 
	decision_notes TEXT, 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	reviewed_at DATETIME, 
	CONSTRAINT pk_verification_checks PRIMARY KEY (check_id), 
	CONSTRAINT ck_verification_checks_type_valid CHECK (check_type IN ('IDENTITY', 'SKILL')), 
	CONSTRAINT ck_verification_checks_status_valid CHECK (status IN ('PENDING', 'UNDER_REVIEW', 'APPROVED', 'REJECTED', 'NEEDS_MORE_EVIDENCE')), 
	CONSTRAINT ck_verification_checks_skill_check_needs_skill CHECK (check_type = 'IDENTITY' OR skill_id IS NOT NULL), 
	CONSTRAINT fk_verification_checks_artisan_id_artisan_profiles FOREIGN KEY(artisan_id) REFERENCES artisan_profiles (artisan_id), 
	CONSTRAINT fk_verification_checks_skill_id_skills FOREIGN KEY(skill_id) REFERENCES skills (skill_id), 
	CONSTRAINT fk_verification_checks_verifier_id_users FOREIGN KEY(verifier_id) REFERENCES users (user_id)
);

CREATE TABLE webhook_events (
	webhook_id CHAR(32) NOT NULL, 
	provider VARCHAR(24) NOT NULL, 
	event_id VARCHAR(80) NOT NULL, 
	payload_hash VARCHAR(64) NOT NULL, 
	received_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_webhook_events PRIMARY KEY (webhook_id), 
	CONSTRAINT uq_webhook_provider_event UNIQUE (provider, event_id)
);

CREATE INDEX ix_artisan_profiles_availability_status ON artisan_profiles (availability_status);

CREATE INDEX ix_artisan_profiles_location ON artisan_profiles (location);

CREATE INDEX ix_artisan_skills_skill_id_verification_status ON artisan_skills (skill_id, verification_status);

CREATE INDEX ix_audit_log_target ON audit_log (target);

CREATE INDEX ix_endorsements_artisan_id ON endorsements (artisan_id);

CREATE INDEX ix_hardship_claims_status ON hardship_claims (status);

CREATE INDEX ix_job_events_job_id_created_at ON job_events (job_id, created_at);

CREATE INDEX ix_job_messages_job_id_created_at ON job_messages (job_id, created_at);

CREATE INDEX ix_jobs_artisan_id ON jobs (artisan_id);

CREATE INDEX ix_jobs_status ON jobs (status);

CREATE INDEX ix_ledger_entries_payment_id ON ledger_entries (payment_id);

CREATE INDEX ix_payments_payer_id ON payments (payer_id);

CREATE INDEX ix_payments_status ON payments (status);

CREATE INDEX ix_payouts_status ON payouts (status);

CREATE INDEX ix_service_requests_customer_id ON service_requests (customer_id);

CREATE INDEX ix_service_requests_location ON service_requests (location);

CREATE INDEX ix_service_requests_skill_id ON service_requests (skill_id);

CREATE INDEX ix_service_requests_status ON service_requests (status);

CREATE INDEX ix_verification_checks_artisan_id_check_type ON verification_checks (artisan_id, check_type);

CREATE INDEX ix_verification_checks_status ON verification_checks (status);

CREATE UNIQUE INDEX uq_hardship_one_open_claim_per_job ON hardship_claims (job_id) WHERE status = 'PENDING';

CREATE UNIQUE INDEX uq_payments_idempotency ON payments (payer_id, idempotency_key) WHERE idempotency_key IS NOT NULL;

CREATE UNIQUE INDEX uq_payments_one_active_per_type ON payments (job_id, payment_type) WHERE status <> 'FAILED';
