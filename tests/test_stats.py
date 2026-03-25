"""Tests for statistics endpoint."""
import io
import pytest


def test_stats_empty_registry(client):
    """Test stats endpoint with empty registry."""
    response = client.get("/stats")

    assert response.status_code == 200
    data = response.json()
    assert data["approved_signers"] == 0
    assert data["pending_requests"] == 0
    assert data["published_skills"] == 0
    assert "last_updated" in data


def test_stats_with_approved_signer(client, approved_identity):
    """Test stats endpoint with an approved signer."""
    response = client.get("/stats")

    assert response.status_code == 200
    data = response.json()
    assert data["approved_signers"] == 1
    assert data["pending_requests"] == 0
    assert data["published_skills"] == 0


def test_stats_with_pending_request(client, keypair):
    """Test stats endpoint with pending identity request."""
    key_path, pubkey, fingerprint = keypair

    # Submit pending request
    response = client.post("/identities/request", json={
        "name": "Pending User",
        "email": "pending@example.com",
        "pubkey": pubkey,
    })
    assert response.status_code == 202

    # Check stats
    response = client.get("/stats")

    assert response.status_code == 200
    data = response.json()
    assert data["pending_requests"] == 1


def test_stats_with_published_skill(client, approved_identity, signed_skill_package):
    """Test stats endpoint with published skills."""
    manifest_json, package_bytes = signed_skill_package

    # Submit skill
    response = client.post(
        "/skills/submit",
        data={"manifest": manifest_json},
        files={"package": ("test-skill.tar.gz", io.BytesIO(package_bytes), "application/gzip")}
    )
    assert response.status_code == 201

    # Check stats
    response = client.get("/stats")

    assert response.status_code == 200
    data = response.json()
    assert data["approved_signers"] == 1
    assert data["published_skills"] == 1


def test_stats_comprehensive(client, approved_identity, signed_skill_package, keypair, admin_headers):
    """Test stats with various data."""
    key_path, pubkey, fingerprint = keypair
    manifest_json, package_bytes = signed_skill_package

    # Add a pending request (use a fresh keypair for different fingerprint)
    import subprocess, tempfile as _tf, os as _os
    with _tf.TemporaryDirectory() as _d:
        _kp = _os.path.join(_d, "another_key")
        subprocess.run(["ssh-keygen", "-t", "ed25519", "-f", _kp, "-N", "", "-C", "another@example.com"], capture_output=True, check=True)
        with open(f"{_kp}.pub") as _f:
            another_pubkey = _f.read().strip()
    response = client.post("/identities/request", json={
        "name": "Another User",
        "email": "another@example.com",
        "pubkey": another_pubkey,
    })

    # Submit a skill
    response = client.post(
        "/skills/submit",
        data={"manifest": manifest_json},
        files={"package": ("test-skill.tar.gz", io.BytesIO(package_bytes), "application/gzip")}
    )
    assert response.status_code == 201

    # Check stats
    response = client.get("/stats")

    assert response.status_code == 200
    data = response.json()
    assert data["approved_signers"] == 1  # One from approved_identity fixture
    assert data["pending_requests"] == 1  # One we just added
    assert data["published_skills"] == 1   # One we just submitted
    assert "last_updated" in data


def test_stats_excludes_revoked(client, approved_identity, admin_headers):
    """Test that stats excludes revoked identities from approved count."""
    # Initial stats
    response = client.get("/stats")
    assert response.status_code == 200
    initial_approved = response.json()["approved_signers"]
    assert initial_approved == 1

    # Revoke the identity
    identity_id = approved_identity.id
    response = client.post(
        f"/admin/identities/{identity_id}/revoke",
        headers=admin_headers,
        json={"reason": "test revocation"}
    )
    assert response.status_code == 200

    # Check stats again
    response = client.get("/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["approved_signers"] == 0  # Should exclude revoked
