# skill-registry — Specification v0.1

## Overview

`skill-registry` is a FastAPI-based registry server for cryptographically signed AI agent skills.
It provides identity management (signer enrollment, approval, revocation), skill publication,
and a minimal web frontend showing registry stats.

It depends on `skill-signer` (PyPI) for manifest validation and trust operations.

## Architecture

```
skill-registry/
├── app/
│   __init__.py
│   main.py              # FastAPI app factory, lifespan
│   config.py            # Settings (env vars, defaults)
│   models.py            # Pydantic models: IdentityRequest, Skill, RegistryState
│   storage.py           # S3-backed (or local-file) JSON state persistence
│   auth.py              # Admin API key middleware
│   routers/
│       identities.py    # /identities endpoints
│       skills.py        # /skills endpoints
│       admin.py         # /admin endpoints (auth-gated)
│       stats.py         # /stats endpoint
│   templates/
│       index.html       # Jinja2: registry homepage
│       admin.html       # Jinja2: admin pending queue
│   static/
│       style.css        # Minimal CSS (no framework)
├── tests/
│   conftest.py          # pytest fixtures, TestClient, tmp state dir
│   test_identities.py
│   test_skills.py
│   test_admin.py
│   test_stats.py
│   test_storage.py
├── scripts/
│   deploy.sh            # EC2 deploy helper
│   seed.py              # Seed a dev registry with test data
├── pyproject.toml
├── README.md
└── .env.example
```

## Data Model

### RegistryState (persisted as JSON)

```json
{
  "version": "1.0.0",
  "identities": {
    "<id-uuid>": {
      "id": "uuid",
      "name": "Dark Matter Lab",
      "email": "rdevaul@gmail.com",
      "pubkey": "ssh-ed25519 AAAA...",
      "key_fingerprint": "SHA256:...",
      "status": "approved",          // pending | approved | revoked
      "submitted_at": "ISO8601",
      "approved_at": "ISO8601",
      "revoked_at": null,
      "revoke_reason": null
    }
  },
  "skills": {
    "<skill-name>@<version>": {
      "name": "example-skill",
      "version": "1.0.0",
      "author_email": "rdevaul@gmail.com",
      "key_fingerprint": "SHA256:...",
      "manifest_hash": "sha256:...",
      "package_url": "s3://bucket/skills/name-version.tar.gz",
      "published_at": "ISO8601",
      "verified": true
    }
  },
  "crl": [
    {
      "key_fingerprint": "SHA256:...",
      "revoked_at": "ISO8601",
      "reason": "key compromised"
    }
  ]
}
```

## API Endpoints

### Identity Management

#### `POST /identities/request`
Submit an identity for approval.

Request body:
```json
{
  "name": "Dark Matter Lab",
  "email": "rdevaul@gmail.com",
  "pubkey": "ssh-ed25519 AAAA...",
  "url": "https://example.com"   // optional, for context
}
```

Response 202:
```json
{
  "id": "uuid",
  "status": "pending",
  "message": "Identity request received. You will be notified when approved."
}
```

Validation:
- pubkey must be valid SSH ed25519 key
- email must be valid format
- Duplicate email or fingerprint (non-revoked) returns 409

#### `GET /identities`
List all approved identities (public).

Response 200:
```json
{
  "identities": [
    {
      "name": "Dark Matter Lab",
      "email": "rdevaul@gmail.com",
      "key_fingerprint": "SHA256:...",
      "approved_at": "ISO8601"
    }
  ],
  "total": 1
}
```

#### `GET /identities/crl`
Public certificate revocation list.

Response 200:
```json
{
  "crl": [
    {
      "key_fingerprint": "SHA256:...",
      "revoked_at": "ISO8601",
      "reason": "key compromised"
    }
  ]
}
```

### Skill Registry

#### `POST /skills/submit`
Submit a signed skill package. Multipart form: `manifest` (JSON) + `package` (tar.gz).

Validation steps (server-side):
1. Parse and validate manifest JSON against SkillManifest schema
2. Verify author email is in approved identities
3. Check author key fingerprint is not in CRL
4. Build temporary allowed_signers from approved identity pubkey
5. Run `skill-signer verify` logic against submitted manifest + package files
6. If valid: store package to S3 (or local), update registry state
7. Return 201 with skill metadata

Response 201:
```json
{
  "name": "example-skill",
  "version": "1.0.0",
  "author_email": "rdevaul@gmail.com",
  "verified": true,
  "published_at": "ISO8601"
}
```

Response 400 if verification fails (include reason).
Response 403 if author not in approved identities.

#### `GET /skills`
List all published skills.

Response 200:
```json
{
  "skills": [
    {
      "name": "example-skill",
      "version": "1.0.0",
      "author_email": "rdevaul@gmail.com",
      "key_fingerprint": "SHA256:...",
      "published_at": "ISO8601",
      "verified": true
    }
  ],
  "total": 1
}
```

#### `GET /skills/{name}`
Get latest version of a skill.

#### `GET /skills/{name}/{version}`
Get specific version.

#### `GET /skills/{name}/{version}/download`
Download the skill package (redirect to S3 URL or serve directly).

#### `POST /skills/{name}/{version}/verify`
Re-verify a published skill on demand (checks manifest + current package).

### Stats

#### `GET /stats`
```json
{
  "approved_signers": 3,
  "pending_requests": 1,
  "published_skills": 12,
  "last_updated": "ISO8601"
}
```

### Admin (requires `X-Admin-Key` header)

#### `GET /admin/pending`
List pending identity requests.

#### `POST /admin/identities/{id}/approve`
Approve a pending identity request.

Request body (optional):
```json
{ "note": "Verified via email" }
```

Response 200:
```json
{ "id": "uuid", "status": "approved" }
```

#### `POST /admin/identities/{id}/reject`
Reject a pending request with reason.

#### `POST /admin/identities/{id}/revoke`
Revoke an approved identity. Body: `{ "reason": "key compromised" }`.
Also adds key fingerprint to CRL.

#### `GET /admin/dashboard`
Returns HTML admin view (Jinja2 template) — lists pending queue + recent activity.

### Web Frontend

#### `GET /`
Jinja2-rendered homepage. Shows:
- Stats bar: N signers · M skills · last updated
- "Install" one-liner: `pip install skill-signer`
- Table: approved signers (name, fingerprint, date)
- Table: published skills (name, version, author, date, ✓ badge)
- Footer with GitHub link

No JavaScript required. Minimal CSS. Clean, readable.

## Storage Backends

Configurable via `REGISTRY_STORAGE_BACKEND` env var.

### `local` (default for dev)
State stored as `registry_state.json` in `REGISTRY_DATA_DIR` (default: `./data/`).
Packages stored in `REGISTRY_DATA_DIR/packages/`.
Auto-created on startup.

### `s3`
State stored in S3 as `state/registry_state.json`.
Packages stored under `packages/`.
Config: `AWS_BUCKET_NAME`, `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`
(or IAM role — prefer IAM role in production).

State is loaded into memory on startup, written back on every mutation.
For this scale (hundreds of skills), this is fine. No database needed.

## Configuration (env vars)

```
REGISTRY_ADMIN_KEY=<secret>       # Required. Admin API key.
REGISTRY_STORAGE_BACKEND=local    # local | s3
REGISTRY_DATA_DIR=./data          # For local backend
AWS_BUCKET_NAME=skill-registry    # For s3 backend
AWS_REGION=us-west-1
REGISTRY_BASE_URL=https://registry.example.com
REGISTRY_TITLE=Skill Registry     # Shown in frontend header
```

## Dependencies

```
fastapi>=0.110
uvicorn[standard]>=0.27
pydantic>=2.0
jinja2>=3.1
python-multipart>=0.0.9
boto3>=1.34              # optional, for s3 backend
skill-signer>=0.1.0      # manifest validation
```

Dev/test:
```
pytest>=7.0
pytest-cov
httpx>=0.27              # for TestClient
```

## Tests

### `conftest.py`
- `test_client` fixture: TestClient with local storage backend, temp dir
- `admin_headers` fixture: `{"X-Admin-Key": "test-key"}`
- `sample_identity` fixture: pre-approved test identity with a real generated keypair
- `sample_signed_skill` fixture: a real signed skill directory (uses skill-signer to sign)

### `test_identities.py`
- submit valid identity → 202, status=pending
- submit duplicate email → 409
- submit invalid pubkey → 422
- list identities (empty, then populated)
- get CRL (empty, then after revocation)

### `test_admin.py`
- get pending without auth → 401
- get pending with wrong key → 401
- approve pending identity → status becomes approved
- reject pending identity → removed from queue
- revoke approved identity → status=revoked, appears in CRL
- approve already-approved → 409

### `test_skills.py`
- submit skill from approved author with valid signature → 201, verified=true
- submit skill from unapproved author → 403
- submit skill with invalid/tampered manifest → 400
- submit skill with revoked key → 403
- list skills (empty, then populated)
- get skill by name → metadata
- get nonexistent skill → 404
- download skill → package bytes

### `test_stats.py`
- stats reflect current state: signer count, skill count, pending count

### `test_storage.py`
- local backend: write state, reload, verify round-trip
- state version compatibility

## Deployment (EC2)

Target: existing t2.micro (us-west-1). Add to existing Caddy config.

```
# /etc/caddy/Caddyfile addition
registry.yourdomain.com {
    reverse_proxy localhost:8400
}
```

launchd plist: `com.glados.skill-registry`
Port: 8400
Log: `/tmp/skill-registry.log`

## Security Notes

- Admin key stored in env var, never in state file or logs
- Package uploads: max 10MB, validate tar.gz before extraction
- Rate limit identity submissions: 3/hour per IP (via slowapi or middleware)
- All state mutations are atomic writes (write temp + rename)
- CRL checked on every skill submission AND download
