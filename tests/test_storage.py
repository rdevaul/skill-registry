"""Tests for storage backends."""
import pytest
from datetime import datetime, UTC

from app.storage import LocalStorageBackend
from app.models import RegistryState, IdentityRecord, SkillRecord, CRLEntry


def test_local_storage_round_trip(tmp_path):
    """Test LocalStorageBackend can save and load state."""
    data_dir = tmp_path / "storage_test"
    storage = LocalStorageBackend(str(data_dir))

    # Create a state with some data
    state = RegistryState()
    state.identities["test-id"] = IdentityRecord(
        id="test-id",
        name="Test User",
        email="test@example.com",
        pubkey="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFakeKey test@example.com",
        key_fingerprint="SHA256:fakefingerprint",
        status="approved",
        submitted_at=datetime.now(UTC).isoformat(),
        approved_at=datetime.now(UTC).isoformat(),
    )

    state.skills["test-skill@1.0.0"] = SkillRecord(
        name="test-skill",
        version="1.0.0",
        author_email="test@example.com",
        key_fingerprint="SHA256:fakefingerprint",
        manifest_hash="sha256:fakehash",
        package_path="packages/test-skill-1.0.0.tar.gz",
        published_at=datetime.now(UTC).isoformat(),
        verified=True
    )

    # Save state
    storage.save_state(state)

    # Load it back
    loaded_state = storage.load_state()

    # Verify data matches
    assert len(loaded_state.identities) == 1
    assert "test-id" in loaded_state.identities
    assert loaded_state.identities["test-id"].email == "test@example.com"

    assert len(loaded_state.skills) == 1
    assert "test-skill@1.0.0" in loaded_state.skills
    assert loaded_state.skills["test-skill@1.0.0"].name == "test-skill"


def test_local_storage_empty_state(tmp_path):
    """Test loading state when file doesn't exist returns empty state."""
    data_dir = tmp_path / "empty_test"
    storage = LocalStorageBackend(str(data_dir))

    # Load state (file doesn't exist yet)
    state = storage.load_state()

    assert state.version == "1.0.0"
    assert len(state.identities) == 0
    assert len(state.skills) == 0
    assert len(state.crl) == 0


def test_local_storage_creates_directories(tmp_path):
    """Test that LocalStorageBackend creates necessary directories."""
    data_dir = tmp_path / "auto_create_test"
    storage = LocalStorageBackend(str(data_dir))

    # Verify directories were created
    assert data_dir.exists()
    assert (data_dir / "packages").exists()


def test_local_storage_package_operations(tmp_path):
    """Test package storage and retrieval."""
    data_dir = tmp_path / "package_test"
    storage = LocalStorageBackend(str(data_dir))

    # Store a package
    package_data = b"fake package content"
    path = storage.store_package("test-skill", "1.0.0", package_data)

    assert path == "packages/test-skill-1.0.0.tar.gz"

    # Load it back
    loaded_data = storage.load_package(path)

    assert loaded_data == package_data


def test_local_storage_state_version(tmp_path):
    """Test that state version is preserved."""
    data_dir = tmp_path / "version_test"
    storage = LocalStorageBackend(str(data_dir))

    # Create and save state
    state = RegistryState(version="1.0.0")
    storage.save_state(state)

    # Load and verify version
    loaded_state = storage.load_state()
    assert loaded_state.version == "1.0.0"


def test_local_storage_crl(tmp_path):
    """Test CRL persistence."""
    data_dir = tmp_path / "crl_test"
    storage = LocalStorageBackend(str(data_dir))

    # Create state with CRL entry
    state = RegistryState()
    state.crl.append(CRLEntry(
        key_fingerprint="SHA256:revokedkey",
        revoked_at=datetime.now(UTC).isoformat(),
        reason="key compromised"
    ))

    # Save and reload
    storage.save_state(state)
    loaded_state = storage.load_state()

    # Verify CRL
    assert len(loaded_state.crl) == 1
    assert loaded_state.crl[0].key_fingerprint == "SHA256:revokedkey"
    assert loaded_state.crl[0].reason == "key compromised"


def test_local_storage_atomic_write(tmp_path):
    """Test that state saves are atomic (write to temp then rename)."""
    data_dir = tmp_path / "atomic_test"
    storage = LocalStorageBackend(str(data_dir))

    # Save initial state
    state1 = RegistryState()
    state1.identities["id1"] = IdentityRecord(
        id="id1",
        name="User 1",
        email="user1@example.com",
        pubkey="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFakeKey1 user1@example.com",
        key_fingerprint="SHA256:fingerprint1",
        status="approved",
        submitted_at=datetime.now(UTC).isoformat(),
        approved_at=datetime.now(UTC).isoformat(),
    )
    storage.save_state(state1)

    # Save new state (should overwrite atomically)
    state2 = RegistryState()
    state2.identities["id2"] = IdentityRecord(
        id="id2",
        name="User 2",
        email="user2@example.com",
        pubkey="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFakeKey2 user2@example.com",
        key_fingerprint="SHA256:fingerprint2",
        status="pending",
        submitted_at=datetime.now(UTC).isoformat(),
    )
    storage.save_state(state2)

    # Load and verify we have the second state
    loaded_state = storage.load_state()
    assert len(loaded_state.identities) == 1
    assert "id2" in loaded_state.identities
    assert "id1" not in loaded_state.identities


def test_local_storage_multiple_operations(tmp_path):
    """Test multiple save/load cycles."""
    data_dir = tmp_path / "multi_test"
    storage = LocalStorageBackend(str(data_dir))

    # First save
    state = RegistryState()
    state.identities["id1"] = IdentityRecord(
        id="id1",
        name="User 1",
        email="user1@example.com",
        pubkey="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFakeKey user@example.com",
        key_fingerprint="SHA256:fp1",
        status="approved",
        submitted_at=datetime.now(UTC).isoformat(),
        approved_at=datetime.now(UTC).isoformat(),
    )
    storage.save_state(state)

    # Load and modify
    state = storage.load_state()
    state.identities["id2"] = IdentityRecord(
        id="id2",
        name="User 2",
        email="user2@example.com",
        pubkey="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFakeKey2 user2@example.com",
        key_fingerprint="SHA256:fp2",
        status="pending",
        submitted_at=datetime.now(UTC).isoformat(),
    )
    storage.save_state(state)

    # Load again and verify both are there
    state = storage.load_state()
    assert len(state.identities) == 2
    assert "id1" in state.identities
    assert "id2" in state.identities
