---
title: Troubleshooting guide
version: "2.3"
status: current
updated: 2026-09-01
product: NovaPay Commerce API
---
# Troubleshooting guide

All steps below are read-only. Anything that changes keys, allowlists, deployments, pools or certificates is a privileged action: escalate to the owning team instead of doing it.

## 401 Unauthorized

1. Check `auth.token_age_s` in the request log. Above 3600 means the token expired.
2. Check `auth.key_prefix`. `nvp_test` on production means the wrong key.
3. Escalate only if both look correct.

## 403 Forbidden

1. Compare `auth.scopes` with the route's required scope.
2. For payments and refunds, check `client_ip_allowlisted`.
3. Allowlist changes are done by the merchant's account owner (escalate).

## 400 and 415

1. Compare the payload field list (`payload_shape.fields`) with the route's required fields.
2. Check the Changelog for newly required fields.
3. For 415, check the `Content-Type` header.

## 429 Too Many Requests

1. Count the client's requests per minute; compare with 100/min.
2. Look for repeated `Idempotency-Key` values and earlier timeouts: a retry storm.
3. Confirm the client honours `Retry-After`.

## 499, 504 and other timeouts

1. For 504, open the dependency latency dashboard for the same minutes.
2. For 499, compare `X-Client-Timeout-Ms` with the route's p95 latency.

## 500, 502 and 503

1. Check the change history for a deploy to the route's service in the 20 minutes before errors started.
2. Look for `ERR_DB_POOL_EXHAUSTED` and rising latency (connection pool).
3. For 502, check upstream TLS (certificate expiry) with a read-only TLS check.
4. For 503, check the dependency's health endpoint.
5. Rollbacks, restarts and certificate rotation are privileged: escalate to the service owner with the correlation IDs.
