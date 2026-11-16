---
title: Timeouts and retries
version: "2.3"
status: current
updated: 2026-09-01
product: NovaPay Commerce API
---
# Timeouts and retries

## Gateway timeout

The API gateway waits **10 seconds** (10000 ms) for a response from the backing service. After that it returns `504 ERR_UPSTREAM_TIMEOUT`. A 504 almost always means a slow dependency, not a client problem. Compare the latency of the route's dependencies for the same minutes.

## Client timeouts

Set the client timeout to at least **15 seconds** (15000 ms), longer than the gateway timeout. If the client gives up first, the gateway logs status `499` (client closed request) and the server never sends a response. Clients can send their timeout in `X-Client-Timeout-Ms` to help diagnosis.

A 499 with a short client timeout and healthy server latency is a client configuration problem.

## Retries

- Retry only `429`, `502`, `503` and `504`, and only idempotent requests or requests with an `Idempotency-Key`.
- Use exponential backoff starting at 1 second, doubling each attempt, plus random jitter, up to 5 attempts.
- Reuse the same `Idempotency-Key` for retries of the same operation. Many reuses of one key within a minute indicate a retry loop.
- Never retry `400`, `401`, `403` or `415`: the request will fail again.
