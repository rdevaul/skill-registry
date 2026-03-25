from typing import Optional, Dict, List
from datetime import datetime
from pydantic import BaseModel, EmailStr, field_validator


class IdentityRequest(BaseModel):
    """Request to register a new identity."""
    name: str
    email: EmailStr
    pubkey: str
    url: Optional[str] = None

    @field_validator("pubkey")
    @classmethod
    def validate_pubkey(cls, v: str) -> str:
        if not v.startswith("ssh-ed25519 "):
            raise ValueError("pubkey must be an ssh-ed25519 public key")
        return v


class IdentityRecord(BaseModel):
    """An identity in the registry."""
    id: str
    name: str
    email: str
    pubkey: str
    key_fingerprint: str
    status: str  # pending | approved | revoked
    submitted_at: str
    approved_at: Optional[str] = None
    revoked_at: Optional[str] = None
    revoke_reason: Optional[str] = None


class SkillRecord(BaseModel):
    """A published skill in the registry."""
    name: str
    version: str
    author_email: str
    key_fingerprint: str
    manifest_hash: str
    package_path: str
    published_at: str
    verified: bool


class CRLEntry(BaseModel):
    """Certificate Revocation List entry."""
    key_fingerprint: str
    revoked_at: str
    reason: str


class RegistryState(BaseModel):
    """The entire registry state."""
    version: str = "1.0.0"
    identities: Dict[str, IdentityRecord] = {}
    skills: Dict[str, SkillRecord] = {}
    crl: List[CRLEntry] = []
