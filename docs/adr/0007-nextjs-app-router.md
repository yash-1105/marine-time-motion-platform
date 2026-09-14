# 7. Next.js App Router + Server State

Date: 2026-09-14

## Context
We need a robust frontend framework for complex dashboards and data tables.

## Decision
We will use Next.js 15 (App Router) with a server-state library (TanStack Query).

## Consequences
- Server components for faster initial load.
- TanStack Query manages API cache, reducing Redux/context boilerplate.
