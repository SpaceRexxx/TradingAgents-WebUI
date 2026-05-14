from fastapi import Request

from backend.config import Settings, get_settings
from backend.services.registry import RunRegistry


def settings_singleton() -> Settings:
    return get_settings()


def get_registry(request: Request) -> RunRegistry:
    return request.app.state.registry
