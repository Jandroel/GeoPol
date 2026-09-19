"""Application composition: middleware and operational routers."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .api import auth, exports, references, review, runs, system, uploads
from .config import settings

app = FastAPI(
    title="GeoPol",
    version=__version__,
    description="Normalización y geocodificación auditable. Datos privados; sin servicios geográficos externos.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.allowed_origins.split(",")],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "Upload-Offset"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


for router in (
    system.router,
    auth.router,
    uploads.router,
    runs.router,
    review.router,
    references.router,
    exports.router,
):
    app.include_router(router)
