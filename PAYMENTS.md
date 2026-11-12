# ACbridge payments module (sandbox)

**SANDBOX ONLY. No real money moves.** The provider is simulated (`PAYMENT_PROVIDER=simulated`); the app refuses to start in
production with it. No card number, mobile-money PIN or OTP is ever received or stored: the customer would enter those only on the
provider's own prompt.

This module extends the FastAPI backend (`backend/`). It was specified for a Node/Express service; the team chose to build on the
existing Python backend, which already had price proposals, a simulated provider, escrow and an audit trail. The table maps each
requirement to what exists.

## What was added

| Requirement | Where it lives |
|---|---|
| Double-entry ledger, always balanced | `ledger_entries` table, `app/services/ledger_service.py` (posting a transaction whose debits differ from credits raises; `unbalanced_transactions()` must always be empty) |
| Commission recorded the moment the customer pays | `COMMISSION_MODEL=customer_split` (see below) |
| Artisan share held as a pending payout | `payouts` table, `app/services/payout_service.py` |
| Release only after completion, never during a dispute | `release_for_completed_job`; a dispute moves the payout to `HELD` |
| Signed webhooks, replay-safe, one transaction | `POST /webhooks/payments/{provider}` (HMAC-SHA256 of the raw body in `X-Signature`; bad/missing signature = 401; `webhook_events` keyed by event id) |
| Idempotency | `Idempotency-Key` header on `POST /jobs/{id}/pay`, plus one live payment per job (partial unique index) |
| Amount never from the client | `pay_job` reads `agreed_price` from the database; the request body is ignored |
| Per-phone rate limit | 5 payment starts per phone per 10 minutes (`PAY_RATE_LIMIT_CALLS`, `PAY_RATE_LIMIT_WINDOW_SECONDS`) |
| Offer expiry | an offer the artisan does not accept in time is cancelled: 1 hour (urgent), 1 day (this week) or 5 days (not urgent), see `OFFER_TTL_HOURS_*`; once accepted the price is frozen |
| Audit log with payload hashes | `audit_log` table (append-only), SHA-256 of the canonical payload, never the payload |
| Contact details locked until paid | in `customer_split` mode the counterpart phone and WhatsApp link are hidden until the payment succeeded |
| Operator panel API | `GET /operator/payments`, `/operator/ledger`, `/operator/payouts`, `POST /operator/payouts/{id}/hold`, `/release` (reason required), `GET /operator/reconciliation`, `GET /operator/audit` (administrator role) |
| Reconciliation with a Mismatch flag | `app/services/reconciliation_service.py`; `provider_collected_override` simulates a disagreeing provider total |

Mapping notes: a "quote" is the job's price proposal (`proposed_price`, agreed when the artisan accepts); a "dispute" is the job's
`DISPUTED` status; the operator is the existing `ADMIN` role (JWT), not a separate PIN.

## Commission models (`COMMISSION_MODEL`)

| Model | Who pays the commission, and when | Default |
|---|---|---|
| `artisan_upfront` | The artisan pays it before the job is assigned (the teammate's original design). The customer's payment then becomes the artisan's pending payout in full. | yes |
| `customer_split` | The customer pays the full agreed price. The commission is cut from it and booked as platform revenue the moment it succeeds; the rest waits as the artisan's pending payout until the job is complete. The artisan pays nothing up front. | no |

The rate is the single setting `COMMISSION_RATE_BPS` (default **500 = 5%**) with `COMMISSION_MIN` (default 300 FCFA). Per your decision the
rate stays at 5%, not the prompt's 10% / 500 minimum. With a 6,000 FCFA job in `customer_split` mode the ledger shows
**300 in `platform_revenue` and 5,700 in `artisan_pending`** (the prompt's example assumed 10%, i.e. 600 / 5,400).

### Ledger entries

| Event | Entries |
|---|---|
| Customer payment succeeds (split) | DEBIT `collection` P, CREDIT `platform_revenue` C, CREDIT `artisan_pending` P - C |
| Customer payment succeeds (artisan-upfront) | DEBIT `collection` P, CREDIT `artisan_pending` P |
| Artisan fee succeeds | DEBIT `collection` F, CREDIT `platform_revenue` F |
| Payout paid | DEBIT `artisan_pending` S, CREDIT `artisan_paid` S |
| Refund requested | DEBIT `platform_revenue` C and `artisan_pending` S, CREDIT `refund_payable` P |

`collection` and `artisan_paid` describe the provider side (gross collected, money sent out). Refunds are only **recorded**
(`refund_payable`); no provider refund API is called.

## Demo script (sandbox, `COMMISSION_MODEL=customer_split`)

1. Customer proposes 6,000 FCFA (in the app chat or when choosing the artisan). The artisan accepts, then confirms after the cooling-off.
2. Customer pays (`POST /jobs/{id}/pay`) and approves the simulated prompt (or the signed webhook fires).
3. Operator: `GET /operator/ledger` shows `platform_revenue` 300, `artisan_pending` 5,700, `artisan_paid` 0.
4. Both sides confirm completion (the app's job code triggers both confirmations): the payout goes `PENDING` to `RELEASED` to `PAID`.
5. `GET /operator/reconciliation` shows status `OK` and zero differences.

## What this does and does not prevent

No software can stop a customer and an artisan from handing each other cash. This design makes that less attractive and easier to spot:

- It **does**: keep the artisan's phone number, the WhatsApp link and the ability to start work hidden until the customer's payment succeeded
  (`customer_split` mode); tie the artisan's payout to a paid and confirmed job; refuse to accept an expired or changed price; hide phone numbers
  in chat; show the operator completed jobs that have no matching payment; keep an append-only audit trail.
- It **does not**: stop two people who already know each other from paying in cash after the app has introduced them, or from agreeing to leave
  the app before the payment step. Reviews and trust scores are only earned on completed jobs, which gives both sides a reason to stay,
  but it is an incentive, not a guarantee.
- Not built (out of scope or needs a licensed partner): real MTN MoMo / Orange Money calls, refunds through a provider API, holding customer
  funds beyond what the provider's own collection account allows, a separate operator PIN with salted hash (the operator is an
  administrator account protected by the login and its JWT).

## Settings (all from environment variables, see `backend/.env.example`)

`COMMISSION_MODEL`, `COMMISSION_RATE_BPS`, `COMMISSION_MIN`, `OFFER_TTL_HOURS_TODAY` / `_THIS_WEEK` / `_NOT_URGENT`, `DISPUTE_WINDOW_HOURS`, `WEBHOOK_SECRET` (required in production),
`PAY_RATE_LIMIT_CALLS`, `PAY_RATE_LIMIT_WINDOW_SECONDS`, `PAYMENT_PROVIDER`.

`DISPUTE_WINDOW_HOURS` (48) is configurable but not yet enforced: disputes can currently be opened any time before completion.

## Tests

```
cd backend && python -m pytest -q          # 150 passed, 1 skipped
python -m pytest -q tests/test_ledger_payments.py   # 20 passed: the nine required areas plus extras
```

The new tests cover: commission rounding and minimum; every money event balanced; same Idempotency-Key = one payment; frozen price and
expired proposals; bad/missing webhook signature (401, nothing changes); webhook replay (no double credit); disputed payout cannot be released;
operator hold/release with reasons and audit hashes; contact details hidden until paid; reconciliation OK and Mismatch; unpaid completed jobs flagged;
per-phone rate limit; refund requests balanced.
