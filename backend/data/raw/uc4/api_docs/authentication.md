---
title: Authentication
version: "2.3"
status: current
updated: 2026-09-01
product: NovaPay Commerce API
---
# Authentication

NovaPay supports two credentials: API keys for server-to-server calls, and short-lived bearer tokens issued by `POST /v1/auth/token`.

## API keys

Send the key in the `X-Api-Key` header. Live keys start with `nvp_live_` and work only against production. Test keys start with `nvp_test_` and work only in the sandbox. A test key sent to production returns `401 ERR_AUTH_INVALID_KEY`.

Never log full keys. The gateway logs only the key prefix (`nvp_live` or `nvp_test`).

## Bearer tokens

Tokens are JWTs with a lifetime (TTL) of **3600 seconds**. Send them as `Authorization: Bearer <token>`. An expired token returns `401 ERR_AUTH_TOKEN_EXPIRED` and the response header `WWW-Authenticate: Bearer error="invalid_token", error_description="token expired"`.

Clients should refresh tokens before expiry, ideally when 80% of the TTL has passed. The gateway records the token's age in seconds (`auth.token_age_s`) without storing the token itself.

## Generic 401 responses

When the gateway cannot tell why a credential failed, it returns `401 ERR_UNAUTHORIZED` with no detail. Check the token age and the key prefix in the request log to narrow it down.
