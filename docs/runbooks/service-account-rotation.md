# Service Account Credential Rotation Runbook

## Overview
Service accounts are machine-to-machine identities used for integration with external port systems (such as Port Management Systems (PMS), Vessel Traffic Services (VTS/VTMS), and Terminal Operating Systems (TOS)). Service account credentials consist of a `client_id` and a `client_secret` hashed with SHA-256 at rest in the `config.service_account` database table.

## Zero-Downtime Rotation Procedure

1. **Generate New Secret**:
   Generate a cryptographically secure random secret (minimum 32 characters, e.g. using `secrets.token_urlsafe(32)`).

2. **Hash Secret**:
   Compute the SHA-256 hash of the new secret.

3. **Provision Secondary / New Credential in Platform**:
   - Insert a new `config.service_account` record or update the secret hash with a defined expiration buffer, ensuring both credentials remain active during the transition window.
   - Record the action in `audit.audit_event` under action `admin_action` with resource type `service_account`.

4. **Update External Client Integration**:
   Configure the external client (e.g. PMS connector) with the new `client_secret`. Verify that token exchange succeeds via `POST /api/v1/auth/service-token`.

5. **Decommission Old Credential**:
   Once the integration has switched to the new credential, deactivate or remove the old service account record. Verify all requests now utilize the new credential.
