from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.ratelimit import RateLimitMiddleware

from app.api.routers import (
    analytics,
    audio,
    auth,
    catalog,
    contests,
    live_search,
    me,
    payments,
    subscription,
)
from app.config import settings


def create_app() -> FastAPI:
    # 🔴 Документация API закрыта (аудит снаружи 24.09): /api/docs, /api/redoc и
    # /api/openapi.json отдавались всем — полная карта маршрутов, параметров и
    # схем ответов. Атакующему это экономит всю разведку. Mini App она не нужна,
    # а разработчику доступна локально: API_DOCS=true в .env.
    docs_on = settings.api_docs
    app = FastAPI(
        title="Infinity Music API",
        version="1.0",
        docs_url="/docs" if docs_on else None,
        redoc_url="/redoc" if docs_on else None,
        openapi_url="/openapi.json" if docs_on else None,
    )

    if settings.cors_origins_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins_list,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Лимитер частоты: у бота антифлуд есть, у API не было. Дорогие пути
    # (/search/live, /search/fetch, /transfer) на боксе 961 МБ — прямой DoS.
    app.add_middleware(RateLimitMiddleware)

    app.include_router(auth.router)
    app.include_router(catalog.router)
    app.include_router(me.router)
    app.include_router(audio.router)
    app.include_router(payments.router)
    app.include_router(subscription.router)
    app.include_router(contests.router)
    app.include_router(live_search.router)
    app.include_router(analytics.router)

    @app.exception_handler(OverflowError)
    async def id_out_of_range(request: Request, exc: OverflowError) -> JSONResponse:
        # /track/99999999999999999999: FastAPI принимает любое int, а SQLite
        # падает на числе шире 64 бит — был 500. Такой записи быть не может.
        return JSONResponse({"detail": "Не найдено"}, status_code=404)

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
