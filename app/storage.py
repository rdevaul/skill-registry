import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from app.models import RegistryState


class StorageBackend(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    def load_state(self) -> RegistryState:
        """Load the registry state."""
        pass

    @abstractmethod
    def save_state(self, state: RegistryState) -> None:
        """Save the registry state atomically."""
        pass

    @abstractmethod
    def store_package(self, name: str, version: str, data: bytes) -> str:
        """Store a skill package and return its path/key."""
        pass

    @abstractmethod
    def load_package(self, path: str) -> bytes:
        """Load a skill package by its path/key."""
        pass


class LocalStorageBackend(StorageBackend):
    """Local filesystem storage backend."""

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.state_file = self.data_dir / "registry_state.json"
        self.packages_dir = self.data_dir / "packages"

        # Auto-create directories on init
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.packages_dir.mkdir(parents=True, exist_ok=True)

    def load_state(self) -> RegistryState:
        """Load the registry state from JSON file."""
        if not self.state_file.exists():
            return RegistryState()

        with open(self.state_file, "r") as f:
            data = json.load(f)
        return RegistryState(**data)

    def save_state(self, state: RegistryState) -> None:
        """Save the registry state atomically (write to .tmp then rename)."""
        tmp_file = self.state_file.with_suffix(".json.tmp")
        with open(tmp_file, "w") as f:
            json.dump(state.model_dump(), f, indent=2)
        tmp_file.rename(self.state_file)

    def store_package(self, name: str, version: str, data: bytes) -> str:
        """Store a skill package and return its relative path."""
        filename = f"{name}-{version}.tar.gz"
        path = self.packages_dir / filename
        with open(path, "wb") as f:
            f.write(data)
        return f"packages/{filename}"

    def load_package(self, path: str) -> bytes:
        """Load a skill package by its path."""
        full_path = self.data_dir / path
        with open(full_path, "rb") as f:
            return f.read()


class S3StorageBackend(StorageBackend):
    """S3 storage backend (stub implementation)."""

    def __init__(self, bucket_name: str, region: str):
        self.bucket_name = bucket_name
        self.region = region
        raise NotImplementedError(
            "S3 storage backend is not yet implemented. "
            "Please use REGISTRY_STORAGE_BACKEND=local for now."
        )

    def load_state(self) -> RegistryState:
        raise NotImplementedError("S3 backend not implemented")

    def save_state(self, state: RegistryState) -> None:
        raise NotImplementedError("S3 backend not implemented")

    def store_package(self, name: str, version: str, data: bytes) -> str:
        raise NotImplementedError("S3 backend not implemented")

    def load_package(self, path: str) -> bytes:
        raise NotImplementedError("S3 backend not implemented")
