CREATE VIEW v_accounts AS
SELECT u.user_id, u.phone, u.role, a.full_name AS artisan_name, a.location AS artisan_location,
       a.availability_status, a.is_suspended, u.created_at
FROM users u LEFT JOIN artisan_profiles a ON a.user_id = u.user_id;

CREATE VIEW v_artisans AS
SELECT a.artisan_id, a.full_name, u.phone, a.location, a.availability_status, s.skill_name, k.proficiency_level,
       k.verification_status AS skill_verification, k.typical_price,
       (SELECT COUNT(*) FROM endorsements e WHERE e.artisan_id = a.artisan_id) AS endorsements
FROM artisan_profiles a JOIN users u ON u.user_id = a.user_id
LEFT JOIN artisan_skills k ON k.artisan_id = a.artisan_id LEFT JOIN skills s ON s.skill_id = k.skill_id;

CREATE VIEW v_customer_requests AS
SELECT r.request_id, cu.phone AS customer_phone, s.skill_name, r.description, r.location, r.budget, r.urgency, r.status AS request_status,
       j.job_id, ap.full_name AS artisan_name, j.status AS job_status, j.proposed_price, j.agreed_price, r.created_at
FROM service_requests r JOIN users cu ON cu.user_id = r.customer_id JOIN skills s ON s.skill_id = r.skill_id
LEFT JOIN jobs j ON j.request_id = r.request_id LEFT JOIN artisan_profiles ap ON ap.artisan_id = j.artisan_id;

CREATE VIEW v_payments AS
SELECT p.payment_id, p.job_id, ap.full_name AS artisan_name, cu.phone AS payer_phone, p.payment_type, p.amount, p.currency,
       p.status, p.provider, p.provider_reference, p.created_at, p.settled_at
FROM payments p JOIN jobs j ON j.job_id = p.job_id JOIN artisan_profiles ap ON ap.artisan_id = j.artisan_id
JOIN users cu ON cu.user_id = p.payer_id;

CREATE VIEW v_payouts AS
SELECT po.payout_id, ap.full_name AS artisan_name, po.amount, po.commission, po.status, po.note, po.provider_reference, po.job_id
FROM payouts po JOIN artisan_profiles ap ON ap.artisan_id = po.artisan_id;

CREATE VIEW v_ledger_balances AS
SELECT account,
       CASE WHEN account = 'collection'
            THEN SUM(CASE WHEN direction = 'DEBIT' THEN amount ELSE -amount END)
            ELSE SUM(CASE WHEN direction = 'CREDIT' THEN amount ELSE -amount END) END AS balance
FROM ledger_entries GROUP BY account;

CREATE VIEW v_chat AS
SELECT m.created_at, m.job_id, m.sender_role, m.body, m.proposed_price FROM job_messages m ORDER BY m.created_at;
