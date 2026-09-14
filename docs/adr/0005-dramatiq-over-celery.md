# 5. Dramatiq over Celery

Date: 2026-09-14

## Context
We need a background task queue for ingestion, OCR processing, and KPI calculations. Celery is standard but complex and often overkill.

## Decision
We will use Dramatiq with Redis as the broker.

## Consequences
- Simpler configuration and maintenance.
- Built-in retries and dead-letter queue support.
- Meets our durability requirements without the overhead of Celery.
