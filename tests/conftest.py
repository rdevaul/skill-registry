import json
import tarfile
import tempfile
from pathlib import Path
from typing import Tuple
from datetime import datetime, UTC

import pytest
from fastapi.testclient import TestClient
from lib import generate_keypair, sign_data, load_manifest, create_manifest, save_manifest, sign_manifest

from app.config import Settings
from app.models import RegistryState, IdentityRecord
from app.storage import LocalStorageBackend


@pytest.fixture
def settings_override(tmp_path):
    """Override settings for testing."""
    data_dir = tmp_path / "test_data"
    data_dir.mkdir()

    return Settings(
        REGISTRY_ADMIN_KEY="test-admin-key",
        REGISTRY_STORAGE_BACKEND="local",
        REGISTRY_DATA_DIR=str(data_dir),
        REGISTRY_BASE_URL="http://testserver",
        REGISTRY_TITLE="Test Registry"
    )


@pytest.fixture
def client(settings_override, tmp_path, monkeypatch):
    """Create a TestClient with overridden settings."""
    # Monkey-patch the settings module to use our test settings
    monkeypatch.setattr("app.config.settings", settings_override)

    # Clear rate limiter before each test
    from app.routers.identities import clear_rate_limit_store
    clear_rate_limit_store()

    # Import here to avoid circular dependencies
    from app.main import create_app

    app = create_app()

    # The app will have initialized storage and state in lifespan,
    # but we need to use TestClient which doesn't run lifespan by default
    # So we manually initialize
    storage = LocalStorageBackend(settings_override.REGISTRY_DATA_DIR)
    state = storage.load_state()

    # Attach to app state
    app.state.storage = storage
    app.state.registry_state = state

    return TestClient(app)


@pytest.fixture
def admin_headers():
    """Return admin authentication headers."""
    return {"X-Admin-Key": "test-admin-key"}


@pytest.fixture
def keypair2(tmp_path) -> Tuple[str, str, str]:
    """Generate a second Ed25519 keypair for testing.

    Returns:
        Tuple of (private_key_path, pubkey_str, fingerprint)
    """
    key_path = tmp_path / "test_key2"

    # Generate keypair using lib
    generate_keypair(str(key_path), comment="test2@example.com")

    # Read public key
    with open(f"{key_path}.pub", "r") as f:
        pubkey = f.read().strip()

    # Get fingerprint using ssh-keygen
    import subprocess
    result = subprocess.run(
        ['ssh-keygen', '-lf', f"{key_path}.pub"],
        capture_output=True,
        text=True,
        check=True
    )
    fingerprint = result.stdout.split()[1]  # SHA256:...

    return (str(key_path), pubkey, fingerprint)


@pytest.fixture(scope="session")
def keypair(tmp_path_factory) -> Tuple[str, str, str]:
    """Generate a real Ed25519 keypair for testing.

    Returns:
        Tuple of (private_key_path, pubkey_str, fingerprint)
    """
    tmp_dir = tmp_path_factory.mktemp("keypair")
    key_path = tmp_dir / "test_key"

    # Generate keypair using skill_signer
    generate_keypair(str(key_path), comment="test@example.com")

    # Read public key
    with open(f"{key_path}.pub", "r") as f:
        pubkey = f.read().strip()

    # Get fingerprint using ssh-keygen
    import subprocess
    result = subprocess.run(
        ['ssh-keygen', '-lf', f"{key_path}.pub"],
        capture_output=True,
        text=True,
        check=True
    )
    fingerprint = result.stdout.split()[1]  # SHA256:...

    return (str(key_path), pubkey, fingerprint)


@pytest.fixture
def approved_identity(client, keypair, admin_headers) -> IdentityRecord:
    """Submit and approve a test identity using the keypair fixture.

    Returns:
        The approved IdentityRecord
    """
    key_path, pubkey, fingerprint = keypair

    # Submit identity request
    response = client.post("/identities/request", json={
        "name": "Test User",
        "email": "test@example.com",
        "pubkey": pubkey,
        "url": "https://example.com"
    })
    assert response.status_code == 202
    identity_id = response.json()["id"]

    # Approve it
    response = client.post(
        f"/admin/identities/{identity_id}/approve",
        headers=admin_headers,
        json={"note": "Test approval"}
    )
    assert response.status_code == 200

    # Get the approved identity from state
    state = client.app.state.registry_state
    return state.identities[identity_id]


@pytest.fixture
def signed_skill_package(keypair, tmp_path) -> Tuple[str, bytes]:
    """Create a temporary signed skill package.

    Returns:
        Tuple of (manifest_json, package_bytes)
    """
    key_path, pubkey, fingerprint = keypair

    # Create skill directory
    skill_dir = tmp_path / "test-skill"
    skill_dir.mkdir()

    # Create SKILL.md (heading must match expected skill name in tests)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text("""# test-skill

A test skill for the registry.

## Usage

This is a test skill.
""")

    # Create another file
    readme = skill_dir / "README.md"
    readme.write_text("# Test Skill\n\nThis is a test skill.")

    # Create manifest using create_manifest
    manifest_obj = create_manifest(
        skill_path=str(skill_dir),
        author="test@example.com",
        version="1.0.0",
        dependencies=[]
    )

    # Sign the manifest
    signed_manifest_obj = sign_manifest(
        manifest=manifest_obj,
        key_path=key_path,
        identity="test@example.com"
    )

    # Save the signed manifest to skill directory
    save_manifest(signed_manifest_obj, str(skill_dir))

    # Read the manifest JSON
    manifest_path = skill_dir / "MANIFEST.sig.json"
    with open(manifest_path, "r") as f:
        manifest_json = f.read()

    # Create tar.gz package
    package_path = tmp_path / "test-skill.tar.gz"
    with tarfile.open(package_path, "w:gz") as tar:
        tar.add(skill_dir, arcname=".")

    # Read package bytes
    with open(package_path, "rb") as f:
        package_bytes = f.read()

    return (manifest_json, package_bytes)
