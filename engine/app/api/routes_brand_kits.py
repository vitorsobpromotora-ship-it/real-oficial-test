"""Brand Kits: identidade visual reutilizável (logo, cores, fontes, estilo de legenda)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select, update

from .. import config
from ..db.base import session
from ..db.models import BrandKit, utcnow
from ..schemas.api import OkOut
from .deps import require_token

router = APIRouter(dependencies=[Depends(require_token)])

ALLOWED_LOGO_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}


class BrandKitIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    logo_position: str = Field(default="tr", pattern="^(tl|tr|bl|br)$")
    logo_opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    primary_color: str = "#FFFFFF"
    secondary_color: str = "#FFD400"
    font_family: str = "Inter"
    caption_preset: str = "bold_karaoke"
    caption_style: dict | None = None
    headline_template: str = ""
    is_default: bool = False


class BrandKitPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    logo_position: str | None = Field(default=None, pattern="^(tl|tr|bl|br)$")
    logo_opacity: float | None = Field(default=None, ge=0.0, le=1.0)
    primary_color: str | None = None
    secondary_color: str | None = None
    font_family: str | None = None
    caption_preset: str | None = None
    caption_style: dict | None = None
    headline_template: str | None = None
    is_default: bool | None = None


class BrandKitOut(BrandKitIn):
    id: str
    logo_path: str | None
    created_at: str
    updated_at: str


def to_out(k: BrandKit) -> BrandKitOut:
    return BrandKitOut(id=k.id, name=k.name, logo_path=k.logo_path, logo_position=k.logo_position,
                       logo_opacity=k.logo_opacity, primary_color=k.primary_color,
                       secondary_color=k.secondary_color, font_family=k.font_family,
                       caption_preset=k.caption_preset, caption_style=k.caption_style,
                       headline_template=k.headline_template, is_default=k.is_default,
                       created_at=k.created_at, updated_at=k.updated_at)


def _clear_default(s, except_id: str | None = None) -> None:
    stmt = update(BrandKit).values(is_default=False)
    if except_id:
        stmt = stmt.where(BrandKit.id != except_id)
    s.execute(stmt)


@router.get("/brand-kits", response_model=list[BrandKitOut])
def list_kits():
    with session() as s:
        rows = s.execute(select(BrandKit).order_by(BrandKit.created_at)).scalars().all()
        return [to_out(k) for k in rows]


@router.post("/brand-kits", response_model=BrandKitOut, status_code=201)
def create_kit(body: BrandKitIn):
    with session() as s:
        if body.is_default:
            _clear_default(s)
        k = BrandKit(**body.model_dump())
        s.add(k)
        s.flush()
        return to_out(k)


@router.patch("/brand-kits/{kit_id}", response_model=BrandKitOut)
def patch_kit(kit_id: str, body: BrandKitPatch):
    with session() as s:
        k = s.get(BrandKit, kit_id)
        if k is None:
            raise HTTPException(404, "Brand kit não encontrado")
        data = body.model_dump(exclude_none=True)
        if data.get("is_default"):
            _clear_default(s, except_id=kit_id)
        for key, value in data.items():
            setattr(k, key, value)
        k.updated_at = utcnow()
        s.flush()
        return to_out(k)


@router.delete("/brand-kits/{kit_id}", response_model=OkOut)
def delete_kit(kit_id: str):
    with session() as s:
        k = s.get(BrandKit, kit_id)
        if k is None:
            raise HTTPException(404, "Brand kit não encontrado")
        if k.logo_path:
            Path(k.logo_path).unlink(missing_ok=True)
        s.delete(k)
    return OkOut(ok=True, detail="Brand kit excluído")


@router.post("/brand-kits/{kit_id}/logo", response_model=BrandKitOut)
async def upload_logo(kit_id: str, file: UploadFile):
    if file.content_type not in ALLOWED_LOGO_TYPES:
        raise HTTPException(422, "Logo deve ser PNG, JPEG ou WebP")
    content = await file.read()
    if len(content) > 8 * 1024 * 1024:
        raise HTTPException(422, "Logo muito grande (máx. 8 MB)")
    with session() as s:
        k = s.get(BrandKit, kit_id)
        if k is None:
            raise HTTPException(404, "Brand kit não encontrado")
        dest_dir = config.data_dir() / "media" / "brand"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{kit_id}{ALLOWED_LOGO_TYPES[file.content_type]}"
        dest.write_bytes(content)
        k.logo_path = str(dest)
        k.updated_at = utcnow()
        s.flush()
        return to_out(k)
