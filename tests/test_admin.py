"""Tests for admin endpoints."""
import pytest


def test_get_pending_without_auth(client):
    """Get pending identities without authentication should return 401."""
    response = client.get("/admin/pending")
    assert response.status_code == 401


def test_get_pending_with_wrong_key(client):
    """Get pending identities with wrong admin key should return 401."""
    response = client.get("/admin/pending", headers={"X-Admin-Key": "wrong-key"})
    assert response.status_code == 401


def test_get_pending_empty(client, admin_headers):
    """Get pending identities when queue is empty."""
    response = client.get("/admin/pending", headers=admin_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["pending"] == []


def test_get_pending_with_requests(client, admin_headers, keypair):
    """Get pending identities with some requests in queue."""
    key_path, pubkey, fingerprint = keypair

    # Submit a pending request
    response = client.post("/identities/request", json={
        "name": "Pending User",
        "email": "pending@example.com",
        "pubkey": pubkey,
    })
    assert response.status_code == 202

    # Get pending queue
    response = client.get("/admin/pending", headers=admin_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["pending"]) == 1

    pending_identity = data["pending"][0]
    assert pending_identity["email"] == "pending@example.com"
    assert pending_identity["status"] == "pending"


def test_approve_pending_identity(client, admin_headers, keypair):
    """Approve a pending identity request."""
    key_path, pubkey, fingerprint = keypair

    # Submit identity
    response = client.post("/identities/request", json={
        "name": "Test User",
        "email": "approve@example.com",
        "pubkey": pubkey,
    })
    assert response.status_code == 202
    identity_id = response.json()["id"]

    # Approve it
    response = client.post(
        f"/admin/identities/{identity_id}/approve",
        headers=admin_headers,
        json={"note": "Verified via email"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == identity_id
    assert data["status"] == "approved"

    # Verify it appears in approved list
    response = client.get("/identities")
    assert response.status_code == 200
    identities = response.json()["identities"]
    assert any(i["email"] == "approve@example.com" for i in identities)


def test_approve_nonexistent_identity(client, admin_headers):
    """Approve nonexistent identity should return 404."""
    response = client.post(
        "/admin/identities/nonexistent-id/approve",
        headers=admin_headers,
        json={}
    )

    assert response.status_code == 404


def test_approve_already_approved(client, admin_headers, approved_identity):
    """Approve already-approved identity should return 409."""
    identity_id = approved_identity.id

    response = client.post(
        f"/admin/identities/{identity_id}/approve",
        headers=admin_headers,
        json={}
    )

    assert response.status_code == 409
    assert "already approved" in response.json()["detail"].lower()


def test_reject_pending_identity(client, admin_headers, keypair):
    """Reject a pending identity request."""
    key_path, pubkey, fingerprint = keypair

    # Submit identity
    response = client.post("/identities/request", json={
        "name": "Reject User",
        "email": "reject@example.com",
        "pubkey": pubkey,
    })
    assert response.status_code == 202
    identity_id = response.json()["id"]

    # Reject it
    response = client.post(
        f"/admin/identities/{identity_id}/reject",
        headers=admin_headers,
        json={"reason": "Invalid information"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == identity_id
    assert data["status"] == "rejected"

    # Verify it's no longer in pending
    response = client.get("/admin/pending", headers=admin_headers)
    assert response.status_code == 200
    pending = response.json()["pending"]
    assert not any(p["id"] == identity_id for p in pending)


def test_reject_approved_identity(client, admin_headers, approved_identity):
    """Reject approved identity should return 400."""
    identity_id = approved_identity.id

    response = client.post(
        f"/admin/identities/{identity_id}/reject",
        headers=admin_headers,
        json={"reason": "Changed mind"}
    )

    assert response.status_code == 400


def test_revoke_approved_identity(client, admin_headers, approved_identity):
    """Revoke an approved identity."""
    identity_id = approved_identity.id
    key_fingerprint = approved_identity.key_fingerprint

    response = client.post(
        f"/admin/identities/{identity_id}/revoke",
        headers=admin_headers,
        json={"reason": "key compromised"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == identity_id
    assert data["status"] == "revoked"
    assert data["reason"] == "key compromised"
    assert "revoked_at" in data

    # Verify identity is no longer in approved list
    response = client.get("/identities")
    assert response.status_code == 200
    identities = response.json()["identities"]
    assert not any(i["email"] == "test@example.com" for i in identities)

    # Verify it's in the CRL
    response = client.get("/identities/crl")
    assert response.status_code == 200
    crl = response.json()["crl"]
    assert any(
        entry["key_fingerprint"] == key_fingerprint and entry["reason"] == "key compromised"
        for entry in crl
    )


def test_revoke_pending_identity(client, admin_headers, keypair):
    """Revoke pending identity should return 400."""
    key_path, pubkey, fingerprint = keypair

    # Submit but don't approve
    response = client.post("/identities/request", json={
        "name": "Pending User",
        "email": "pending@example.com",
        "pubkey": pubkey,
    })
    assert response.status_code == 202
    identity_id = response.json()["id"]

    # Try to revoke
    response = client.post(
        f"/admin/identities/{identity_id}/revoke",
        headers=admin_headers,
        json={"reason": "test"}
    )

    assert response.status_code == 400
    assert "cannot" in response.json()["detail"].lower() or "can only" in response.json()["detail"].lower()


def test_admin_operations_require_auth(client, keypair):
    """All admin operations should require authentication."""
    key_path, pubkey, fingerprint = keypair

    # Submit an identity first
    response = client.post("/identities/request", json={
        "name": "User",
        "email": "user@example.com",
        "pubkey": pubkey,
    })
    identity_id = response.json()["id"]

    # Try approve without auth
    response = client.post(f"/admin/identities/{identity_id}/approve", json={})
    assert response.status_code == 401  # Unauthorized

    # Try reject without auth
    response = client.post(f"/admin/identities/{identity_id}/reject", json={"reason": "test"})
    assert response.status_code == 401  # Unauthorized

    # Try revoke without auth
    response = client.post(f"/admin/identities/{identity_id}/revoke", json={"reason": "test"})
    assert response.status_code == 401  # Unauthorized
