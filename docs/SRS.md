# Software requirements summary

This summarises the requirements the product is built to. It is derived from the project's build prompts (hackathon demo, payments module,
full-product prompt) and from the decisions taken while building. It is not a formal SRS document; where the original SRS exists it prevails.

## Users

| Role | Main goal |
|---|---|
| Artisan | Get verified by vouches, receive and accept job offers, finish jobs with a job code, get paid |
| Customer | Ask for an artisan of a trade, bargain in chat, pay safely, rate the job |
| Operator | Review verifications, watch payments and the ledger, hold or release payouts, read the audit log |

## Functional requirements (current decisions)

- **Identity:** phone number plus a one-time SMS code (production). The hackathon demo used usernames and passwords.
- **Verification:** an artisan is verified by at least 2 vouches from verified artisans; one vouch per pair, sealed in a tamper-evident chain.
- **Requests and matching:** any trade (catalogue or free text), urgency Today / This week / Not urgent, up to 5 ranked verified artisans of that trade, price shown as a range.
- **Offers expire:** the artisan must accept within 1 hour (urgent), 1 day (this week) or 5 days (not urgent), or the offer is cancelled.
- **Price:** the customer bargains in the chat; the **artisan** states the final price (amount + currency at the end of a message); the artisan's YES accepts it; the customer's consent is paying. The chat closes once the customer's payment succeeds.
- **Payments:** the customer pays the agreed price once (MTN MoMo or Orange Money, sandbox); the commission (5%, within a 3 to 7% band) is booked when the payment succeeds; the artisan's share is a pending payout released after the job code is verified; double-entry ledger; reconciliation.
- **Job code:** six digits, created when payment succeeds, sent to the customer, entered by the artisan to complete the job.
- **Ratings and trust score:** one rating per completed job; trust score from ratings weighted by job count plus 0.2 per vouch, capped at 5.0.
- **Languages:** French (default) and English, with a placeholder local language that falls back to French.

## Non-functional requirements

- Low literacy, low data: icons plus labels of three words or fewer, text at least 16 px, tap targets at least 48 px, read-aloud buttons, small bundles.
- Accessibility: WCAG 2.2 AA on web (see `ACCESSIBILITY.md`).
- Security: no secret reaches a client; phone numbers masked; append-only ledger and audit log; signed payment webhooks.
- The backend is the source of truth for every business rule.
