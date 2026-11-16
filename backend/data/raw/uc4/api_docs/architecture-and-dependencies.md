---
title: Architecture and dependencies
version: "2.3"
status: current
updated: 2026-09-01
product: NovaPay Commerce API
---
# Architecture and dependencies

Requests pass through the API gateway to a route's service, which calls one or more dependencies.

## Route dependencies

| Route | Service | Direct dependencies |
|---|---|---|
| POST /v1/orders | orders-api | payments-svc, inventory-svc |
| GET /v1/orders/{id} | orders-api | orders-db |
| POST /v1/payments | payments-api | bank-gateway (external) |
| POST /v1/refunds | payments-api | payments-svc |
| GET /v1/inventory/{sku} | inventory-api | inventory-db |
| GET /v1/customers/{id} | customers-api | customer-db |
| GET /v1/search | search-api | search-cluster |

## Indirect dependencies

payments-svc calls bank-gateway; inventory-svc calls inventory-db. So a bank-gateway incident can affect payments, refunds and order creation, and an inventory-db incident affects inventory reads and order creation.

## Blast radius

| Dependency | Routes affected |
|---|---|
| bank-gateway | 3 (payments, refunds, orders) |
| payments-svc | 2 (orders, refunds) |
| inventory-db | 2 (inventory, orders) |
| inventory-svc | 1 (orders) |
| orders-db | 1 |
| customer-db | 1 |
| search-cluster | 1 |
