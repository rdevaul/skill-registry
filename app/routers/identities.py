import subprocess
import tempfile
import uuid
from datetime import datetime, UTC
from typing import Dict
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Request

from app.models import IdentityRequest, IdentityRecord

router = APIRouter(prefix="/identities", tags=["identities"])

# Simple in-memory rate limiter: IP -> list of timestamps
rate_limit_store: Dict[str, list] = defaultdict(list)


def clear_rate_limit_store():
    """Clear rate limit store (for testing purposes)."""
    rate_limit_store.clear()


def get_ssh_fingerprint(pubkey: str) -> str:
    """Extract SSH key fingerprint using ssh-keygen."""
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.pub', delete=False) as f:
            f.write(pubkey)
            f.flush()
            result = subprocess.run(
                ['ssh-keygen', '-lf', f.name],
                capture_output=True,
                text=True,
                check=True
            )
            # Output format: "256 SHA256:... comment (ED25519)"
            parts = result.stdout.split()
            if len(parts) >= 2:
                return parts[1]  # SHA256:...
            raise ValueError("Unexpected ssh-keygen output format")
    except subprocess.CalledProcessError as e:
        raise ValueError(f"Invalid SSH key: {e.stderr}")
    except Exception as e:
        raise ValueError(f"Failed to parse SSH key: {str(e)}")


def check_rate_limit(ip: str) -> None:
    """Check if IP has exceeded rate limit (3 requests per hour)."""
    now = datetime.now(UTC)
    hour_ago = now.timestamp() - 3600

    # Clean old entries
    rate_limit_store[ip] = [ts for ts in rate_limit_store[ip] if ts > hour_ago]

    if len(rate_limit_store[ip]) >= 3:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Maximum 3 identity requests per hour."
        )

    rate_limit_store[ip].append(now.timestamp())


@router.post("/request", status_code=202)
async def request_identity(identity: IdentityRequest, request: Request):
    """Submit an identity for approval."""
    # Rate limiting
    client_ip = request.client.host if request.client else "unknown"
    check_rate_limit(client_ip)

    # Get fingerprint
    try:
        fingerprint = get_ssh_fingerprint(identity.pubkey)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Check for duplicates
    state = request.app.state.registry_state
    for existing in state.identities.values():
        if existing.status != "revoked":
            if existing.email == identity.email:
                raise HTTPException(
                    status_code=409,
                    detail=f"Identity with email {identity.email} already exists"
                )
            if existing.key_fingerprint == fingerprint:
                raise HTTPException(
                    status_code=409,
                    detail="Identity with this key fingerprint already exists"
                )

    # Create new identity
    identity_id = str(uuid.uuid4())
    record = IdentityRecord(
        id=identity_id,
        name=identity.name,
        email=identity.email,
        pubkey=identity.pubkey,
        key_fingerprint=fingerprint,
        status="pending",
        submitted_at=datetime.now(UTC).isoformat(),
    )

    # Save to state
    state.identities[identity_id] = record
    request.app.state.storage.save_state(state)

    return {
        "id": identity_id,
        "status": "pending",
        "message": "Identity request received. You will be notified when approved."
    }


@router.get("")
async def list_identities(request: Request):
    """List all approved identities."""
    state = request.app.state.registry_state
    approved = [
        {
            "name": identity.name,
            "email": identity.email,
            "key_fingerprint": identity.key_fingerprint,
            "approved_at": identity.approved_at,
        }
        for identity in state.identities.values()
        if identity.status == "approved"
    ]
    return {"identities": approved, "total": len(approved)}


@router.get("/crl")
async def get_crl(request: Request):
    """Get the certificate revocation list."""
    state = request.app.state.registry_state
    return {"crl": [entry.model_dump() for entry in state.crl]}
