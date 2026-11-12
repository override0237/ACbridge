# Going live: what ACbridge must obtain (all "to confirm with provider")

Nothing below has been verified against the providers' current requirements. Every line is a question to put to MTN and Orange
before any real money is involved. Do not treat this list as complete.

## MTN Mobile Money (MoMo)

| Item | Status |
|---|---|
| Merchant / developer account for the collection (receive-money) product in Cameroon | to confirm with provider |
| Disbursement (send-money-to-artisans) product and whether it needs a separate agreement or approval | to confirm with provider |
| Business documents required (company registration, tax number, bank details, ID of directors, etc.) | to confirm with provider |
| Approval / onboarding process, timeline and any fees (setup, per-transaction, payout) | to confirm with provider |
| Sandbox access, test numbers and the sandbox documentation link to use for the `MtnMomoProvider` adapter | to confirm with provider |
| Whether the provider can split a single payment between ACbridge and the artisan (this module assumes it cannot: the collection account receives the full amount and payouts are separate calls) | to confirm with provider |
| Webhook / callback mechanism: signature scheme, header name, retry policy, IP ranges | to confirm with provider |

## Orange Money

| Item | Status |
|---|---|
| Merchant / developer account for collections in Cameroon | to confirm with provider |
| Disbursement product and conditions | to confirm with provider |
| Business documents required | to confirm with provider |
| Approval process, timeline and fees | to confirm with provider |
| Sandbox access and documentation link for the `OrangeMoneyProvider` adapter | to confirm with provider |
| Split-payment support (see above) | to confirm with provider |
| Callback signature scheme and retry policy | to confirm with provider |

## ACbridge side (to confirm with a lawyer / regulator, not with a provider)

| Item | Status |
|---|---|
| Whether holding customer money until job completion (escrow) needs a licence in Cameroon, or must be done only inside the provider's own collection account | to confirm with provider and legal advisor |
| Tax treatment of the commission and any VAT on platform fees | to confirm with legal advisor |
| Data protection obligations for storing phone numbers and payment references | to confirm with legal advisor |

## Technical steps once approved

1. Implement `MtnMomoProvider` / `OrangeMoneyProvider` behind the same interface as `SimulatedProvider` (`initiate_charge`, `payout`, `refund`).
2. Register the webhook URL `https://<your-api-host>/webhooks/payments/<provider>` with the provider (exact path to confirm with provider)
   and replace the HMAC check in `payment_providers.sign_webhook` with the provider's documented signature scheme.
3. Set `WEBHOOK_SECRET`, `JWT_SECRET`, `ENVIRONMENT=production` and the provider credentials as environment variables only. Never commit them.
4. Remove the simulated approval endpoints (they are already disabled when the provider is not simulated).
5. Re-run reconciliation against the provider's real settlement report before the first payout.
