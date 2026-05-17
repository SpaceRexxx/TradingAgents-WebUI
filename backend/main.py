from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.deps import get_settings_dep
from backend.routes import (
    analysis,
    diagnostics,
    health,
    history,
    providers,
    quote,
    runs,
    stats,
)
from backend.services.registry import RunRegistry


def create_app() -> FastAPI:
    settings = get_settings_dep()
    app = FastAPI(title="TradingAgents Backend", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.registry = RunRegistry()
    app.include_router(health.router)
    app.include_router(analysis.router)
    app.include_router(history.router)
    app.include_router(diagnostics.router)
    app.include_router(providers.router)
    app.include_router(quote.router)
    app.include_router(runs.router)
    app.include_router(stats.router)
    return app


app = create_app()
