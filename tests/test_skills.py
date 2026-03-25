"""Tests for skill submission and management endpoints."""
import io
import json
import pytest


def test_submit_skill_from_approved_author(client, approved_identity, signed_skill_package):
    """Submit a valid signed skill from an approved author."""
    manifest_json, package_bytes = signed_skill_package

    response = client.post(
        "/skills/submit",
        data={"manifest": manifest_json},
        files={"package": ("test-skill.tar.gz", io.BytesIO(package_bytes), "application/gzip")}
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "test-skill"
    assert data["version"] == "1.0.0"
    assert data["author_email"] == "test@example.com"
    assert data["verified"] is True
    assert "published_at" in data


def test_submit_skill_from_unapproved_author(client, keypair, signed_skill_package):
    """Submit skill from unapproved author should return 403."""
    manifest_json, package_bytes = signed_skill_package

    # Note: the signed_skill_package uses the keypair fixture which is used by approved_identity,
    # so we need to ensure no approval happened. Let's use a fresh client.
    # Actually, this test might fail if approved_identity was already used.
    # We'll need a different email in the manifest.

    # Parse and modify manifest to use a different email
    manifest = json.loads(manifest_json)
    manifest["author"] = "unapproved@example.com"
    modified_manifest_json = json.dumps(manifest, sort_keys=True, indent=2)

    response = client.post(
        "/skills/submit",
        data={"manifest": modified_manifest_json},
        files={"package": ("test-skill.tar.gz", io.BytesIO(package_bytes), "application/gzip")}
    )

    assert response.status_code == 403
    assert "not an approved identity" in response.json()["detail"].lower()


def test_submit_skill_with_invalid_signature(client, approved_identity, signed_skill_package):
    """Submit skill with tampered/invalid signature should return 400."""
    manifest_json, package_bytes = signed_skill_package

    # Tamper with the manifest to break signature (modify the skill version in the payload)
    manifest = json.loads(manifest_json)
    if "skill" in manifest:
        manifest["skill"]["version"] = "9.9.9-TAMPERED"
    else:
        manifest["version"] = "9.9.9-TAMPERED"
    tampered_manifest_json = json.dumps(manifest, sort_keys=True, indent=2)

    response = client.post(
        "/skills/submit",
        data={"manifest": tampered_manifest_json},
        files={"package": ("test-skill.tar.gz", io.BytesIO(package_bytes), "application/gzip")}
    )

    assert response.status_code == 400
    assert "verification failed" in response.json()["detail"].lower() or "signature" in response.json()["detail"].lower()


def test_submit_skill_with_revoked_key(client, approved_identity, admin_headers, signed_skill_package):
    """Submit skill with revoked author key should return 403."""
    manifest_json, package_bytes = signed_skill_package

    # Revoke the identity
    identity_id = approved_identity.id
    response = client.post(
        f"/admin/identities/{identity_id}/revoke",
        headers=admin_headers,
        json={"reason": "key compromised"}
    )
    assert response.status_code == 200

    # Try to submit skill
    response = client.post(
        "/skills/submit",
        data={"manifest": manifest_json},
        files={"package": ("test-skill.tar.gz", io.BytesIO(package_bytes), "application/gzip")}
    )

    assert response.status_code == 403
    assert "revoked" in response.json()["detail"].lower()


def test_submit_skill_with_invalid_manifest(client, approved_identity):
    """Submit skill with invalid manifest JSON should return 400."""
    response = client.post(
        "/skills/submit",
        data={"manifest": "not valid json"},
        files={"package": ("test-skill.tar.gz", io.BytesIO(b"fake package"), "application/gzip")}
    )

    assert response.status_code == 400
    assert "invalid manifest" in response.json()["detail"].lower()


def test_submit_skill_exceeds_size_limit(client, approved_identity, signed_skill_package):
    """Submit skill that exceeds 10MB limit should return 400."""
    manifest_json, _ = signed_skill_package

    # Create a package that's too large (>10MB)
    large_package = b"x" * (11 * 1024 * 1024)

    response = client.post(
        "/skills/submit",
        data={"manifest": manifest_json},
        files={"package": ("large-skill.tar.gz", io.BytesIO(large_package), "application/gzip")}
    )

    assert response.status_code == 400
    assert "10mb" in response.json()["detail"].lower() or "limit" in response.json()["detail"].lower()


def test_list_skills_empty(client):
    """List skills when registry is empty."""
    response = client.get("/skills")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["skills"] == []


def test_list_skills_with_published(client, approved_identity, signed_skill_package):
    """List skills shows published skills."""
    manifest_json, package_bytes = signed_skill_package

    # Submit a skill
    response = client.post(
        "/skills/submit",
        data={"manifest": manifest_json},
        files={"package": ("test-skill.tar.gz", io.BytesIO(package_bytes), "application/gzip")}
    )
    assert response.status_code == 201

    # List skills
    response = client.get("/skills")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["skills"]) == 1

    skill = data["skills"][0]
    assert skill["name"] == "test-skill"
    assert skill["version"] == "1.0.0"
    assert skill["author_email"] == "test@example.com"
    assert skill["verified"] is True


def test_get_skill_by_name(client, approved_identity, signed_skill_package):
    """Get latest version of a skill by name."""
    manifest_json, package_bytes = signed_skill_package

    # Submit skill
    response = client.post(
        "/skills/submit",
        data={"manifest": manifest_json},
        files={"package": ("test-skill.tar.gz", io.BytesIO(package_bytes), "application/gzip")}
    )
    assert response.status_code == 201

    # Get by name
    response = client.get("/skills/test-skill")

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "test-skill"
    assert data["version"] == "1.0.0"
    assert "manifest_hash" in data


def test_get_nonexistent_skill(client):
    """Get nonexistent skill should return 404."""
    response = client.get("/skills/nonexistent-skill")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_get_skill_by_name_and_version(client, approved_identity, signed_skill_package):
    """Get specific version of a skill."""
    manifest_json, package_bytes = signed_skill_package

    # Submit skill
    response = client.post(
        "/skills/submit",
        data={"manifest": manifest_json},
        files={"package": ("test-skill.tar.gz", io.BytesIO(package_bytes), "application/gzip")}
    )
    assert response.status_code == 201

    # Get by name and version
    response = client.get("/skills/test-skill/1.0.0")

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "test-skill"
    assert data["version"] == "1.0.0"


def test_get_nonexistent_version(client, approved_identity, signed_skill_package):
    """Get nonexistent version should return 404."""
    manifest_json, package_bytes = signed_skill_package

    # Submit skill
    response = client.post(
        "/skills/submit",
        data={"manifest": manifest_json},
        files={"package": ("test-skill.tar.gz", io.BytesIO(package_bytes), "application/gzip")}
    )
    assert response.status_code == 201

    # Try to get wrong version
    response = client.get("/skills/test-skill/2.0.0")

    assert response.status_code == 404


def test_download_skill_package(client, approved_identity, signed_skill_package):
    """Download a skill package."""
    manifest_json, package_bytes = signed_skill_package

    # Submit skill
    response = client.post(
        "/skills/submit",
        data={"manifest": manifest_json},
        files={"package": ("test-skill.tar.gz", io.BytesIO(package_bytes), "application/gzip")}
    )
    assert response.status_code == 201

    # Download it
    response = client.get("/skills/test-skill/1.0.0/download")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/gzip"
    assert "attachment" in response.headers["content-disposition"]
    assert len(response.content) > 0


def test_download_skill_with_revoked_key(client, approved_identity, admin_headers, signed_skill_package):
    """Download skill with revoked author key should return 403."""
    manifest_json, package_bytes = signed_skill_package

    # Submit skill first
    response = client.post(
        "/skills/submit",
        data={"manifest": manifest_json},
        files={"package": ("test-skill.tar.gz", io.BytesIO(package_bytes), "application/gzip")}
    )
    assert response.status_code == 201

    # Revoke the identity
    identity_id = approved_identity.id
    response = client.post(
        f"/admin/identities/{identity_id}/revoke",
        headers=admin_headers,
        json={"reason": "key compromised"}
    )
    assert response.status_code == 200

    # Try to download
    response = client.get("/skills/test-skill/1.0.0/download")

    assert response.status_code == 403
    assert "revoked" in response.json()["detail"].lower()


def test_download_nonexistent_skill(client):
    """Download nonexistent skill should return 404."""
    response = client.get("/skills/nonexistent/1.0.0/download")

    assert response.status_code == 404
