---
title: Rate limits
version: "2.3"
status: current
updated: 2026-09-01
product: NovaPay Commerce API
---
# Rate limits

Each API key may send **100 requests per minute**, with bursts of up to 20 requests per second. Limits are per key, not per IP.

## Response headers

Every response includes:

- `X-RateLimit-Limit`: the per-minute limit (100)
- `X-RateLimit-Remaining`: requests left in the current minute
- `X-RateLimit-Reset`: seconds until the window resets

When the limit is exceeded the API returns `429 ERR_RATE_LIMITED` with `X-RateLimit-Remaining: 0` and a `Retry-After` header in seconds.

## How to respond to 429

Wait at least `Retry-After` seconds, then retry with exponential backoff and jitter. Do not retry immediately: immediate retries count against the same limit and make the problem worse.

## Retry storms

A common cause of sustained 429s is a client retry loop. After a burst of timeouts the client retries every failed call at once, often reusing the same `Idempotency-Key`. Signs: repeated idempotency keys from one client, and 504 or 499 timeouts shortly before the 429s. See Timeouts and retries.
