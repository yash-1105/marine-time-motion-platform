# Security threat model

| Threat | Control | Verification |
|---|---|---|
| Tenant/port/terminal data exposure | Principal scope is authoritative; Copilot rejects supplied scope/query arguments and report artifact access is tenant scoped. | `test_copilot_core.py` and route authorization tests |
| Prompt injection in source records | Source content is data only; it is never added as Copilot instructions. The model sees a fixed tool surface. | `test_injected_source_content_is_not_a_tool_instruction` |
| SQL/SSRF through Copilot | No model database credential or SQL tool exists; unsupported tools, SQL, query expressions and unknown arguments are rejected. Sarvam is called only at its fixed HTTPS endpoint. | `test_model_cannot_supply_scope_or_sql` |
| Browser attacks | Exact configured CORS origins, cookie-write origin validation, CSP, clickjacking, referrer and MIME-sniffing headers. | `test_security_headers_present` |
| Unsafe uploads | Filename canonicalisation, extension allowlist, bounded streaming write, OOXML signature check, temporary cleanup. Malware scanning and content-disarm require the production scanner integration and remain a deployment prerequisite. | `test_upload_rejects_unsupported_extension` |
| Secret/PII leakage | Backend-only provider configuration, structured event metadata without raw provider key, production exceptions omit internals. | configuration review |

Audit events are append-only at the application boundary. Database administrators must restrict `UPDATE`/`DELETE` privileges on `audit.audit_event`, retain database audit backups, and monitor anomalous access.
