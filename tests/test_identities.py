"""Tests for identity management endpoints."""
import pytest


def test_submit_valid_identity(client, keypair):
    """Submit a valid identity request."""
    key_path, pubkey, fingerprint = keypair

    response = client.post("/identities/request", json={
        "name": "Test User",
        "email": "newuser@example.com",
        "pubkey": pubkey,
        "url": "https://example.com"
    })

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "pending"
    assert "id" in data
    assert "message" in data


def test_submit_duplicate_email(client, approved_identity, keypair2):
    """Submit identity with duplicate email should return 409."""
    # approved_identity has email test@example.com
    key_path, pubkey, fingerprint = keypair2

    response = client.post("/identities/request", json={
        "name": "Another User",
        "email": "test@example.com",  # Duplicate
        "pubkey": pubkey,
    })

    assert response.status_code == 409
    assert "email" in response.json()["detail"].lower()


def test_submit_invalid_pubkey(client):
    """Submit identity with invalid pubkey should return 422."""
    response = client.post("/identities/request", json={
        "name": "Test User",
        "email": "user@example.com",
        "pubkey": "not-a-valid-ssh-key",
    })

    assert response.status_code == 422


def test_submit_wrong_key_type(client):
    """Submit identity with non-ed25519 key should return 422."""
    response = client.post("/identities/request", json={
        "name": "Test User",
        "email": "user@example.com",
        "pubkey": "ssh-rsa AAAAB3NzaC1yc2EAAA... rsa@example.com",
    })

    assert response.status_code == 422


def test_list_identities_empty(client):
    """List identities when registry is empty."""
    response = client.get("/identities")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["identities"] == []


def test_list_identities_with_approved(client, approved_identity):
    """List identities shows only approved ones."""
    response = client.get("/identities")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["identities"]) == 1

    identity = data["identities"][0]
    assert identity["email"] == "test@example.com"
    assert identity["name"] == "Test User"
    assert "key_fingerprint" in identity
    assert "approved_at" in identity


def test_list_identities_does_not_show_pending(client, keypair):
    """List identities should not show pending ones."""
    key_path, pubkey, fingerprint = keypair

    # Submit but don't approve
    client.post("/identities/request", json={
        "name": "Pending User",
        "email": "pending@example.com",
        "pubkey": pubkey,
    })

    response = client.get("/identities")

    assert response.status_code == 200
    data = response.json()
    # Should not include the pending identity
    assert data["total"] == 0


def test_get_crl_empty(client):
    """Get CRL when it's empty."""
    response = client.get("/identities/crl")

    assert response.status_code == 200
    data = response.json()
    assert "crl" in data
    assert data["crl"] == []


def test_get_crl_after_revocation(client, approved_identity, admin_headers):
    """Get CRL after revoking an identity."""
    # Revoke the approved identity
    identity_id = approved_identity.id
    response = client.post(
        f"/admin/identities/{identity_id}/revoke",
        headers=admin_headers,
        json={"reason": "key compromised"}
    )
    assert response.status_code == 200

    # Check CRL
    response = client.get("/identities/crl")

    assert response.status_code == 200
    data = response.json()
    assert len(data["crl"]) == 1

    crl_entry = data["crl"][0]
    assert crl_entry["key_fingerprint"] == approved_identity.key_fingerprint
    assert crl_entry["reason"] == "key compromised"
    assert "revoked_at" in crl_entry


def test_rate_limit(client, tmp_path):
    """Test rate limiting on identity submissions."""
    from lib import generate_keypair

    # Submit 3 requests with unique keys (should succeed)
    for i in range(3):
        # Generate a unique key for each request
        key_path = tmp_path / f"ratelimit_key_{i}"
        generate_keypair(str(key_path), comment=f"user{i}@example.com")
        with open(f"{key_path}.pub", "r") as f:
            pubkey = f.read().strip()

        response = client.post("/identities/request", json={
            "name": f"User {i}",
            "email": f"user{i}@example.com",
            "pubkey": pubkey,
        })
        assert response.status_code == 202, f"Request {i} failed: {response.json()}"

    # 4th request should be rate limited (even with unique key)
    key_path = tmp_path / "ratelimit_key_3"
    generate_keypair(str(key_path), comment="user3@example.com")
    with open(f"{key_path}.pub", "r") as f:
        pubkey = f.read().strip()

    response = client.post("/identities/request", json={
        "name": "User 3",
        "email": "user3@example.com",
        "pubkey": pubkey,
    })

    assert response.status_code == 429
    assert "rate limit" in response.json()["detail"].lower()
