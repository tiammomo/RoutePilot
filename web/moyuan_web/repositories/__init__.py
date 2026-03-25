"""Repository abstractions and concrete persistence adapters."""

# Repositories Package
from .session_repository import SessionRepository
from .session_repository_impl import SessionRepositoryImpl

__all__ = ['SessionRepository', 'SessionRepositoryImpl']
