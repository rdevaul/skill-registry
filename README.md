# skill-registry

A FastAPI-based registry server for cryptographically signed AI agent skills.

## Features

- Identity management with approval workflow
- Cryptographic verification of skill packages using SSH signatures
- Certificate Revocation List (CRL) support
- Local or S3 storage backends
- Admin API with authentication
- Web frontend for browsing registry

## Quick Start (Local Development)

### Prerequisites

- Python 3.10+
- `ssh-keygen` (for key fingerprinting)

### Installation

```bash
# Clone the repository
cd /Users/rich/Projects/skill-registry

# Install dependencies
pip install -e ".[dev]"

# Copy example environment file
cp .env.example .env

# Edit .env and set a secure admin key
# REGISTRY_ADMIN_KEY=your-secret-key-here
```

### Run the server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8400 --reload
```

The server will be available at http://localhost:8400

### Run tests

```bash
pytest tests/ -v --cov=app
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REGISTRY_ADMIN_KEY` | `change-me-in-production` | Secret key for admin API access |
| `REGISTRY_STORAGE_BACKEND` | `local` | Storage backend: `local` or `s3` |
| `REGISTRY_DATA_DIR` | `./data` | Directory for local storage backend |
| `REGISTRY_BASE_URL` | `http://localhost:8400` | Public base URL of the registry |
| `REGISTRY_TITLE` | `Skill Registry` | Registry title shown in web frontend |
| `AWS_BUCKET_NAME` | - | S3 bucket name (for S3 backend) |
| `AWS_REGION` | `us-west-1` | AWS region (for S3 backend) |

## API Endpoints

### Public Endpoints

- `GET /` - Web homepage
- `GET /identities` - List approved identities
- `GET /identities/crl` - Certificate revocation list
- `POST /identities/request` - Submit identity for approval
- `GET /skills` - List all published skills
- `GET /skills/{name}` - Get latest version of a skill
- `GET /skills/{name}/{version}` - Get specific skill version
- `GET /skills/{name}/{version}/download` - Download skill package
- `POST /skills/submit` - Submit a signed skill package
- `GET /stats` - Registry statistics

### Admin Endpoints (require `X-Admin-Key` header)

- `GET /admin/dashboard` - Admin web dashboard
- `GET /admin/pending` - List pending identity requests
- `POST /admin/identities/{id}/approve` - Approve identity
- `POST /admin/identities/{id}/reject` - Reject identity
- `POST /admin/identities/{id}/revoke` - Revoke approved identity

## Deployment (EC2)

### Prerequisites

- EC2 instance (t2.micro or larger)
- Caddy or nginx for reverse proxy
- systemd or launchd for process management

### Setup

1. Install Python 3.10+ on the EC2 instance
2. Clone the repository
3. Install dependencies: `pip install -e .`
4. Create `.env` file with production settings
5. Set up reverse proxy (example for Caddy):

```
# /etc/caddy/Caddyfile
registry.yourdomain.com {
    reverse_proxy localhost:8400
}
```

6. Create systemd service (Linux) or launchd plist (macOS)

#### systemd service example

```ini
[Unit]
Description=Skill Registry
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/skill-registry
Environment="PATH=/home/ubuntu/.local/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/usr/local/bin/uvicorn app.main:app --host 127.0.0.1 --port 8400
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable skill-registry
sudo systemctl start skill-registry
```

#### launchd plist example (macOS)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.glados.skill-registry</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/uvicorn</string>
        <string>app.main:app</string>
        <string>--host</string>
        <string>127.0.0.1</string>
        <string>--port</string>
        <string>8400</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/rich/Projects/skill-registry</string>
    <key>StandardOutPath</key>
    <string>/tmp/skill-registry.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/skill-registry.log</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
```

Load the service:
```bash
launchctl load ~/Library/LaunchAgents/com.glados.skill-registry.plist
```

## Storage Backends

### Local Storage (default)

- State stored in `REGISTRY_DATA_DIR/registry_state.json`
- Packages stored in `REGISTRY_DATA_DIR/packages/`
- Atomic writes using temp files
- Auto-creates directories on startup

### S3 Storage (coming soon)

- State stored in S3 bucket under `state/registry_state.json`
- Packages stored under `packages/`
- Requires AWS credentials or IAM role

## Security

- All identity requests are rate-limited (3/hour per IP)
- Admin API requires authentication via `X-Admin-Key` header
- Package uploads are limited to 10MB
- Tar archives are validated for path traversal attacks
- CRL is checked on every skill download
- All state mutations use atomic writes

## Development

### Project Structure

```
skill-registry/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app factory
│   ├── config.py            # Settings (env vars)
│   ├── models.py            # Pydantic models
│   ├── storage.py           # Storage backends
│   ├── auth.py              # Admin authentication
│   ├── routers/
│   │   ├── identities.py    # Identity endpoints
│   │   ├── skills.py        # Skill endpoints
│   │   ├── admin.py         # Admin endpoints
│   │   └── stats.py         # Stats endpoint
│   ├── templates/           # Jinja2 templates
│   └── static/              # Static files (CSS)
├── tests/                   # Pytest tests
├── pyproject.toml
├── README.md
└── .env.example
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Run `pytest tests/ -v`
6. Submit a pull request

## License

MIT
