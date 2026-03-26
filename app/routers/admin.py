from datetime import datetime, UTC
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel

from app.auth import require_admin
from app.models import CRLEntry

router = APIRouter(prefix="/admin", tags=["admin"])


class ApproveNote(BaseModel):
    note: Optional[str] = None


class RejectReason(BaseModel):
    reason: str


class RevokeRequest(BaseModel):
    reason: str


class RetractRequest(BaseModel):
    reason: str


@router.get("/pending", dependencies=[Depends(require_admin)])
async def get_pending(request: Request):
    """List all pending identity requests."""
    state = request.app.state.registry_state
    pending = [
        identity.model_dump()
        for identity in state.identities.values()
        if identity.status == "pending"
    ]
    return {"pending": pending, "total": len(pending)}


@router.post("/identities/{identity_id}/approve", dependencies=[Depends(require_admin)])
async def approve_identity(identity_id: str, request: Request, note: ApproveNote = ApproveNote()):
    """Approve a pending identity request."""
    state = request.app.state.registry_state

    identity = state.identities.get(identity_id)
    if not identity:
        raise HTTPException(status_code=404, detail="Identity not found")

    if identity.status == "approved":
        raise HTTPException(status_code=409, detail="Identity already approved")

    if identity.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve identity with status '{identity.status}'"
        )

    identity.status = "approved"
    identity.approved_at = datetime.now(UTC).isoformat()

    request.app.state.storage.save_state(state)

    return {"id": identity_id, "status": "approved"}


@router.post("/identities/{identity_id}/reject", dependencies=[Depends(require_admin)])
async def reject_identity(identity_id: str, request: Request, reason: RejectReason):
    """Reject a pending identity request."""
    state = request.app.state.registry_state

    identity = state.identities.get(identity_id)
    if not identity:
        raise HTTPException(status_code=404, detail="Identity not found")

    if identity.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot reject identity with status '{identity.status}'"
        )

    # Remove from state
    del state.identities[identity_id]
    request.app.state.storage.save_state(state)

    return {"id": identity_id, "status": "rejected", "reason": reason.reason}


@router.post("/identities/{identity_id}/revoke", dependencies=[Depends(require_admin)])
async def revoke_identity(identity_id: str, request: Request, revoke_req: RevokeRequest):
    """Revoke an approved identity and add to CRL."""
    state = request.app.state.registry_state

    identity = state.identities.get(identity_id)
    if not identity:
        raise HTTPException(status_code=404, detail="Identity not found")

    if identity.status != "approved":
        raise HTTPException(
            status_code=400,
            detail=f"Can only revoke approved identities, current status: '{identity.status}'"
        )

    # Update identity status
    identity.status = "revoked"
    identity.revoked_at = datetime.now(UTC).isoformat()
    identity.revoke_reason = revoke_req.reason

    # Add to CRL
    crl_entry = CRLEntry(
        key_fingerprint=identity.key_fingerprint,
        revoked_at=identity.revoked_at,
        reason=revoke_req.reason
    )
    state.crl.append(crl_entry)

    request.app.state.storage.save_state(state)

    return {
        "id": identity_id,
        "status": "revoked",
        "reason": revoke_req.reason,
        "revoked_at": identity.revoked_at
    }


@router.delete("/skills/{skill_name}/{version}", dependencies=[Depends(require_admin)])
async def retract_skill_version(skill_name: str, version: str, request: Request, body: RetractRequest):
    """Retract a specific version of a skill."""
    state = request.app.state.registry_state

    skill_key = f"{skill_name}@{version}"
    if skill_key not in state.skills:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' version '{version}' not found")

    skill = state.skills.pop(skill_key)
    request.app.state.storage.save_state(state)

    return {
        "retracted": skill_key,
        "author_email": skill.author_email,
        "reason": body.reason,
        "retracted_at": datetime.now(UTC).isoformat()
    }


@router.delete("/skills/{skill_name}", dependencies=[Depends(require_admin)])
async def retract_skill_all_versions(skill_name: str, request: Request, body: RetractRequest):
    """Retract all versions of a skill (full namespace removal)."""
    state = request.app.state.registry_state

    matching = [k for k in state.skills if k.startswith(f"{skill_name}@")]
    if not matching:
        raise HTTPException(status_code=404, detail=f"No versions of skill '{skill_name}' found")

    retracted = []
    for key in matching:
        skill = state.skills.pop(key)
        retracted.append({"version": skill.version, "author_email": skill.author_email})

    request.app.state.storage.save_state(state)

    return {
        "skill": skill_name,
        "retracted_versions": retracted,
        "count": len(retracted),
        "reason": body.reason,
        "retracted_at": datetime.now(UTC).isoformat()
    }
