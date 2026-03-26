import hashlib
import json
import tarfile
import tempfile
from datetime import datetime, UTC
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import Response

from lib import load_manifest, verify_data
SKILL_NAMESPACE = "skill-manifest"

from app.models import SkillRecord

router = APIRouter(prefix="/skills", tags=["skills"])


def verify_package_security(tar_path: Path) -> None:
    """Verify tar.gz package for path traversal attacks."""
    with tarfile.open(tar_path, 'r:gz') as tar:
        for member in tar.getmembers():
            if '..' in member.name or member.name.startswith('/'):
                raise ValueError(f"Unsafe path in tar: {member.name}")


def compute_manifest_hash(manifest_json: str) -> str:
    """Compute SHA256 hash of manifest JSON."""
    return "sha256:" + hashlib.sha256(manifest_json.encode()).hexdigest()


@router.post("/submit", status_code=201)
async def submit_skill(
    request: Request,
    manifest: str = Form(...),
    package: UploadFile = File(...)
):
    """Submit a signed skill package."""
    state = request.app.state.registry_state

    # Parse manifest
    try:
        manifest_data = json.loads(manifest)
        # Write manifest to temp file for load_manifest
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp_manifest:
            json.dump(manifest_data, tmp_manifest)
            tmp_manifest_path = Path(tmp_manifest.name)
        try:
            skill_manifest = load_manifest(str(tmp_manifest_path))
        finally:
            tmp_manifest_path.unlink(missing_ok=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid manifest: {str(e)}")

    # Check author exists (any status) so we can check CRL before rejecting
    author_email = skill_manifest.author
    author_identity = None
    for identity in state.identities.values():
        if identity.email == author_email:
            author_identity = identity
            break

    # Check CRL first (covers revoked identities)
    if author_identity:
        for crl_entry in state.crl:
            if crl_entry.key_fingerprint == author_identity.key_fingerprint:
                raise HTTPException(
                    status_code=403,
                    detail=f"Author key has been revoked: {crl_entry.reason}"
                )

    # Now require approved status
    if not author_identity or author_identity.status != "approved":
        raise HTTPException(
            status_code=403,
            detail=f"Author {author_email} is not an approved identity"
        )

    # Save package to temp file
    package_data = await package.read()
    if len(package_data) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(status_code=400, detail="Package exceeds 10MB limit")

    with tempfile.NamedTemporaryFile(suffix='.tar.gz', delete=False) as tmp_package:
        tmp_package.write(package_data)
        tmp_package_path = Path(tmp_package.name)

    try:
        # Security check
        verify_package_security(tmp_package_path)

        # Extract to temp directory for verification
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            with tarfile.open(tmp_package_path, 'r:gz') as tar:
                tar.extractall(tmpdir_path)

            # Verify manifest signature using skill-signer
            # Create temporary allowed_signers file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.pub', delete=False) as signers_file:
                signers_file.write(f"{author_email} {author_identity.pubkey}\n")
                signers_file.flush()
                allowed_signers_path = Path(signers_file.name)

            try:
                # Reconstruct signing payload (manifest dict without signature field,
                # serialized with sort_keys and compact separators — matches skill_signer's
                # signing_payload() method exactly)
                signing_payload = skill_manifest.signing_payload()

                # Verify the manifest data signature
                result = verify_data(
                    data=signing_payload,
                    signature=skill_manifest.signature,
                    allowed_signers_path=str(allowed_signers_path),
                    identity=author_email,
                    namespace=SKILL_NAMESPACE
                )
                if not result.valid:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Signature verification failed: {result.error or 'invalid signature'}"
                    )
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Signature verification failed: {str(e)}"
                )
            finally:
                allowed_signers_path.unlink(missing_ok=True)

            # Verify file hashes from manifest
            for file_name, file_entry in skill_manifest.files.items():
                file_path = tmpdir_path / file_name
                if not file_path.exists():
                    raise HTTPException(
                        status_code=400,
                        detail=f"File listed in manifest not found in package: {file_name}"
                    )

                # Compute actual hash
                hasher = hashlib.sha256()
                with open(file_path, 'rb') as f:
                    hasher.update(f.read())
                actual_hash = hasher.hexdigest()

                if actual_hash != file_entry.sha256:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Hash mismatch for {file_name}: expected {file_entry.sha256}, got {actual_hash}"
                    )

        # Reject duplicate version (immutable releases)
        skill_key = f"{skill_manifest.skill_name}@{skill_manifest.skill_version}"
        if skill_key in state.skills:
            raise HTTPException(
                status_code=409,
                detail=f"Version {skill_manifest.skill_version} of '{skill_manifest.skill_name}' already exists. Versions are immutable."
            )

        # Store package
        package_path = request.app.state.storage.store_package(
            skill_manifest.skill_name,
            skill_manifest.skill_version,
            package_data
        )

        # Compute manifest hash
        manifest_hash = compute_manifest_hash(manifest)

        # Create skill record
        record = SkillRecord(
            name=skill_manifest.skill_name,
            version=skill_manifest.skill_version,
            author_email=author_email,
            key_fingerprint=author_identity.key_fingerprint,
            manifest_hash=manifest_hash,
            package_path=package_path,
            published_at=datetime.now(UTC).isoformat(),
            verified=True
        )

        state.skills[skill_key] = record
        request.app.state.storage.save_state(state)

        return {
            "name": record.name,
            "version": record.version,
            "author_email": record.author_email,
            "verified": record.verified,
            "published_at": record.published_at,
        }

    finally:
        tmp_package_path.unlink(missing_ok=True)


@router.get("")
async def list_skills(request: Request):
    """List all published skills."""
    state = request.app.state.registry_state
    skills = [
        {
            "name": skill.name,
            "version": skill.version,
            "author_email": skill.author_email,
            "key_fingerprint": skill.key_fingerprint,
            "published_at": skill.published_at,
            "verified": skill.verified,
        }
        for skill in state.skills.values()
    ]
    return {"skills": skills, "total": len(skills)}


@router.get("/{name}")
async def get_skill_latest(name: str, request: Request):
    """Get the latest version of a skill."""
    state = request.app.state.registry_state

    # Find all versions of this skill
    matching_skills = [
        skill for key, skill in state.skills.items()
        if skill.name == name
    ]

    if not matching_skills:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")

    # Sort by version (simple string sort, could be improved with proper semver)
    latest = max(matching_skills, key=lambda s: s.version)

    return {
        "name": latest.name,
        "version": latest.version,
        "author_email": latest.author_email,
        "key_fingerprint": latest.key_fingerprint,
        "manifest_hash": latest.manifest_hash,
        "published_at": latest.published_at,
        "verified": latest.verified,
    }


@router.get("/{name}/{version}")
async def get_skill_version(name: str, version: str, request: Request):
    """Get a specific version of a skill."""
    state = request.app.state.registry_state
    skill_key = f"{name}@{version}"

    skill = state.skills.get(skill_key)
    if not skill:
        raise HTTPException(
            status_code=404,
            detail=f"Skill '{name}' version '{version}' not found"
        )

    return {
        "name": skill.name,
        "version": skill.version,
        "author_email": skill.author_email,
        "key_fingerprint": skill.key_fingerprint,
        "manifest_hash": skill.manifest_hash,
        "published_at": skill.published_at,
        "verified": skill.verified,
    }


@router.get("/{name}/{version}/download")
async def download_skill(name: str, version: str, request: Request):
    """Download a skill package."""
    state = request.app.state.registry_state
    skill_key = f"{name}@{version}"

    skill = state.skills.get(skill_key)
    if not skill:
        raise HTTPException(
            status_code=404,
            detail=f"Skill '{name}' version '{version}' not found"
        )

    # Check CRL before serving
    for crl_entry in state.crl:
        if crl_entry.key_fingerprint == skill.key_fingerprint:
            raise HTTPException(
                status_code=403,
                detail=f"Skill author key has been revoked: {crl_entry.reason}"
            )

    # Load and serve package
    package_data = request.app.state.storage.load_package(skill.package_path)

    return Response(
        content=package_data,
        media_type="application/gzip",
        headers={
            "Content-Disposition": f"attachment; filename={name}-{version}.tar.gz"
        }
    )
