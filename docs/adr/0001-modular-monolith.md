# 1. Modular Monolith over Microservices

Date: 2026-09-14

## Context
We are building a Marine Time & Motion platform that requires complex joins across vessel calls, journeys, and data quality states. A distributed architecture would introduce network boundaries and distributed transaction complexities.

## Decision
We will build a modular monolith using FastAPI rather than microservices.

## Consequences
- Simpler deployment and local development.
- Code boundaries are maintained by Python modules rather than network APIs.
- Can be split later if scaling requires it.
