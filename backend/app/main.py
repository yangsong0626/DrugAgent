from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import ensure_runtime_dirs
from app.storage.database import init_db


def create_app() -> FastAPI:
    ensure_runtime_dirs()
    init_db()

    app = FastAPI(title="Patent-to-SAR Agent API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1):[0-9]+",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()
