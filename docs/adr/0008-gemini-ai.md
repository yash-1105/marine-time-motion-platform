# 8. Gemini for AI Features

Date: 2026-09-14

## Context
The platform requires an AI copilot, narrative generation, and mapping suggestions.

## Decision
We will use the Gemini API (via Google AI/Vertex) for these features. The model name will be injected via configuration, never hard-coded.

## Consequences
- Easy to upgrade to newer models as they are released.
- Requires secure key management in deployment.
