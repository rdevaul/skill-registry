from datetime import datetime, UTC

from fastapi import APIRouter, Request

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("")
async def get_stats(request: Request):
    """Get registry statistics."""
    state = request.app.state.registry_state

    approved_count = sum(
        1 for identity in state.identities.values()
        if identity.status == "approved"
    )
    pending_count = sum(
        1 for identity in state.identities.values()
        if identity.status == "pending"
    )

    return {
        "approved_signers": approved_count,
        "pending_requests": pending_count,
        "published_skills": len(state.skills),
        "last_updated": datetime.now(UTC).isoformat()
    }
