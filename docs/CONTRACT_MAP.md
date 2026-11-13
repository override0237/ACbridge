# Contract map: screen -> endpoint

Status: **E** = endpoint exists in the backend today, **A** = additive endpoint approved but not built yet (see `CHANGES.md`),
**C** = client-only (no endpoint). The apps never fake a result: a screen whose endpoint is **A** shows a designed "not available yet" state until it lands.
Phase = the build phase in which the screen is built in the production apps.

| Screen | Phase | Endpoints | Status |
|---|---|---|---|
| Sign in: phone entry, code entry, resend after 60 s | 2 | `POST /auth/otp/request`, `POST /auth/otp/verify` | A |
| Role choice at first sign-in | 2 | `POST /auth/register` (role CUSTOMER or ARTISAN) | E |
| Sign out | 2 | cookie/token cleared on the client; `POST /auth/logout` | A |
| Artisan profile form | 3 | `POST /artisans`, `PATCH /artisans/{id}`, `POST /artisans/{id}/skills`, `GET /skills` | E |
| Artisan status (vouches received, who vouched) | 3 | `GET /artisans/{id}` (`endorsement_count`), `GET /artisans/{id}/endorsements` | E / A |
| Request a vouch (SMS link) | 3 | `POST /artisans/{id}/vouch-requests` | A |
| Expert view: vouch requests I can answer, vouches left | 3 | `GET /me/vouch-requests`, `POST /artisans/{id}/endorsements` | A / E |
| Withdraw a vouch | 3 | `DELETE /artisans/{id}/endorsements/me` | A |
| Verification threshold shown from the backend | 3 | `GET /pricing` style policy endpoint (`min_endorsements_for_skill_verification`) | A |
| Customer request form | 4 | `POST /service-requests` (trade, neighbourhood, urgency) | E |
| Match results (up to 5, price range) | 4 | `GET /matches/{request_id}` | E |
| Choose an artisan | 4 | `POST /jobs` | E |
| Connect flexibly (chat) | 4 | `GET/POST /jobs/{id}/messages` | E |
| Artisan states the final price (in the chat) | 4 | `POST /jobs/{id}/messages` (`price_status`) | E |
| Customer accepts the quote | 4 | `POST /jobs/{id}/quote-acceptance` | A |
| Artisan job inbox, YES / NO | 5 | `GET /jobs/{id}`, `POST /jobs/{id}/accept`, `POST /jobs/{id}/cancel` | E |
| Offer countdown | 5 | `offer_expires_at` on `GET /jobs/{id}` | E |
| Customer job tracker | 5 | `GET /jobs/{id}` (status, `payments`, events) | E |
| Payments: agreed price card, method, waiting, result, receipt | 5 | `POST /jobs/{id}/pay` (Idempotency-Key), `GET /payments/{id}` (poll every 3 s) | E |
| Artisan completion (6-digit code, attempts left) | 5 | `POST /jobs/{id}/complete-with-code` | A |
| Artisan contact unlock after payment | 5 | `counterpart_phone` on `GET /jobs/{id}` | E |
| Rate a job | 5 | `POST /jobs/{id}/reviews` | E |
| Artisan profile, trust score | 5 | `GET /artisans/{id}`, `GET /artisans/{id}/reputation` | E |
| Customer profile, past requests | 5 | `GET /service-requests` (mine) | A |
| Notifications inbox, read/unread | 7 | `GET /me/notifications`, `POST /me/notifications/{id}/read` | A |
| Operator sign-in (code + PIN) | 6 | `POST /auth/otp/verify`, `POST /operator/pin` | A |
| Verifications queue (approve/reject with reason) | 6 | `GET /verifications`, `POST /verifications/{id}/decision` | E |
| Payments and ledger | 6 | `GET /operator/payments`, `/operator/ledger`, `/operator/payouts` | E |
| Payout Hold / Release (reason required) | 6 | `POST /operator/payouts/{id}/hold`, `/release` | E |
| Reconciliation with Mismatch | 6 | `GET /operator/reconciliation` | E |
| Audit log (filter by action/date) | 6 | `GET /operator/audit` (filters to add) | E / A |
| Message log (real SMS delivery records) | 6 | `GET /operator/sms` | A |
| Suspend / reinstate an artisan (reason) | 6 | `POST /admin/artisans/{id}/suspend`, `/unsuspend` | E (reason field A) |
| Settings: language, theme, text size, voice | 7 | none (stored on the device) | C |
| Help (steps with play buttons) | 7 | none | C |
| Privacy (what is stored, masking, deletion) | 7 | `POST /me/deletion-request` | A |

Health and catalogue: `GET /health`, `GET /skills`.
