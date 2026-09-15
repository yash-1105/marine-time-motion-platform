# Known limitations and production-hardening backlog

- The Phase 07 duplicate `LeadTimeResult` persisted-state failure remains unresolved.
- The validation harness fixture reset can violate `canonical.event_occurrence` uniqueness during identity merge; it is not changed by Phase 15.
- MinIO/GCS adapter configuration, malware scanning, delivery adapters, scheduled execution, Railway/Vercel live deployment, and production backup restore require external deployment credentials and are not represented as completed connectivity.
- Weekly, monthly, quarterly, and benchmark reporting templates are registered/deferred.
