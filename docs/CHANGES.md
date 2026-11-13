# Backend changes made for the full product

Rule: the backend behaviour stays unchanged. Only **additive** endpoints and tables may be added, and every one is recorded here.
Every existing backend test must stay green (`cd backend && python -m pytest`; currently 158 passed, 1 skipped).

## Phases 0-1 (this commit): none

No backend file was touched. Phases 0 and 1 are the monorepo, shared packages, design tokens, the contrast and security scripts, and the design-system primitives.

## Approved additive set (not started): phase 2 onwards

Approved by the project owner on the condition that nothing existing changes and that only a **sandbox** provider is used (no live SMS, payment or push
provider is called). Each item ships with tests and gets its own entry below when it lands.

| Needed by | Planned addition | Notes |
|---|---|---|
| Phone + one-time-code sign-in (5.1) | `POST /auth/otp/request`, `POST /auth/otp/verify`, `otp_codes` table | New endpoints beside the existing password login, which keeps working. Codes are hashed, single use, expire, and are rate limited. |
| Real SMS delivery records (5.9, 5.8) | `sms_messages` table, `GET /operator/sms`, `GET /me/notifications`, `POST /me/notifications/{id}/read` | A SANDBOX SMS provider records every message (recipient masked in responses, status, timestamp) instead of sending it. |
| Vouch requests and withdrawal (5.2) | `POST /artisans/{id}/vouch-requests`, `GET /me/vouch-requests`, `DELETE /artisans/{id}/endorsements/me`, monthly cap read from settings | Additive. The existing one-vouch-per-pair rule is untouched. |
| Quotes (5.4) | `POST /jobs/{id}/quote-acceptance` style endpoint for the customer to explicitly accept the artisan's final price | Combines with the existing chat and `proposed_price`; does not change them. |
| Job code (5.5) | code created when the customer's payment succeeds, SMS to the customer, `POST /jobs/{id}/complete-with-code`, attempts left | Today the backend completes a job when both sides confirm; the code endpoint is additive. |
| Operator panel (5.9) | `POST /operator/artisans/{id}/suspend` with a reason, verification queue reasons, operator PIN check | PIN stored as a salted hash, never in a client. |

## Stop-and-ask items (will NOT be done without approval)

Changing the commission rate (5%), the payout release rule, the vouch limit or verification threshold, any schema change that alters existing
behaviour, calling a live SMS/payment/push provider, and collecting personal data beyond name, phone and rating.
