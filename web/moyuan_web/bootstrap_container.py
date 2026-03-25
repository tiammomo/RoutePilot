"""Unified entrypoints for initializing and resolving the shared dependency container."""

from __future__ import annotations

from .dependencies.container import Container, get_container


def initialize_dependency_container() -> Container:
    """Initialize and return the shared dependency container."""
    return get_container()
