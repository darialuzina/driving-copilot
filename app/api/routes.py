from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import ServiceDep, to_response
from app.api.errors import raise_for_domain_error
from app.api.schemas import CreateLinkRequest, LinkResponse
from app.domain.errors import DomainError

router = APIRouter(prefix="/links", tags=["links"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_link(data: CreateLinkRequest, service: ServiceDep) -> LinkResponse:
    try:
        link = await service.create_link(
            data.url, ttl_seconds=data.ttl_seconds, custom_code=data.custom_code
        )
    except DomainError as exc:
        raise_for_domain_error(exc)
    return to_response(link)


@router.get("")
async def list_links(service: ServiceDep) -> list[LinkResponse]:
    links = await service.list_links()
    return [to_response(item) for item in links]


@router.get("/{short_code}")
async def get_link(short_code: str, service: ServiceDep) -> LinkResponse:
    try:
        link = await service.get_link(short_code)
    except DomainError as exc:
        raise_for_domain_error(exc)
    return to_response(link)


@router.post("/{short_code}/disable")
async def disable_link(short_code: str, service: ServiceDep) -> LinkResponse:
    try:
        link = await service.disable_link(short_code)
    except DomainError as exc:
        raise_for_domain_error(exc)
    return to_response(link)
