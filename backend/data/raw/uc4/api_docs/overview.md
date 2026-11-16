---
title: NovaPay Commerce API overview
version: "2.3"
status: current
updated: 2026-09-01
product: NovaPay Commerce API
---
# NovaPay Commerce API overview

NovaPay is a fictional commerce platform used for this hackathon dataset. The REST API lets merchants create orders, take payments, issue refunds, read inventory and customers, and search the catalogue.

## Base URL and versions

All requests go to `https://api.novapay.example/v1`. The current API version is `2026-09-01` (release 2.3). Send it in the `NovaPay-Version` header; requests without it use the account's pinned version.

## Environments

Production keys start with `nvp_live_`. Sandbox keys start with `nvp_test_` and are rejected by production with `ERR_AUTH_INVALID_KEY`.

## Request format

Every request body must be JSON with `Content-Type: application/json`. Every response carries a `X-Correlation-Id` header; quote it when contacting support.

## Related documents

Authentication, Authorization and scopes, Rate limits, Timeouts and retries, Error reference, Troubleshooting guide, Architecture and dependencies, and the endpoint reference pages.
