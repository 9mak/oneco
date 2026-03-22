"""Uvicorn entry point for the FastAPI app (factory pattern wrapper)."""
from src.data_collector.infrastructure.api.app import create_app

app = create_app()
