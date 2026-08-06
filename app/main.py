from __future__ import annotations

from fastapi import FastAPI, status
from fastapi.responses import RedirectResponse

from app.api.deps import ServiceDep
from app.api.errors import raise_for_domain_error
from app.api.routes import router
from app.domain.errors import DomainError


async def redirect_to_target(short_code: str, service: ServiceDep) -> RedirectResponse:
    try:
        link = await service.resolve(short_code)
    except DomainError as exc:
        raise_for_domain_error(exc)
    return RedirectResponse(
        url=link.target_url.value, status_code=status.HTTP_307_TEMPORARY_REDIRECT
    )


def create_app() -> FastAPI:
    application = FastAPI(title="Link Shortener (FastAPI track)")
    application.include_router(router)
    application.add_api_route("/{short_code}", redirect_to_target, methods=["GET"])
    return application


app = create_app()
