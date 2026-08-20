"""Brand Kits: identidade visual reutilizável (logo, cores, fontes, estilo de legenda)
e o layout do Brand Studio (canvas 9:16 com camadas)."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select, update

from .. import config
from ..db.base import session
from ..db.models import BrandKit, CutCandidate, Render, utcnow
from ..pipeline import compose
from ..schemas.api import OkOut
from .deps import require_token

router = APIRouter(dependencies=[Depends(require_token)])

ALLOWED_LOGO_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
ALLOWED_ASSET_TYPES = {**ALLOWED_LOGO_TYPES, "video/mp4": ".mp4", "video/webm": ".webm"}

# mudanças nestes campos tornam obsoletas as prévias dos cortes que usam o kit
VISUAL_KIT_FIELDS = {"logo_position", "logo_opacity", "primary_color", "secondary_color",
                     "font_family", "caption_preset", "caption_style", "headline_template",
                     "layout"}


class BrandKitIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    logo_position: str = Field(default="tr", pattern="^(tl|tr|bl|br)$")
    logo_opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    primary_color: str = "#FFFFFF"
    secondary_color: str = "#FFD400"
    font_family: str = "Inter"
    caption_preset: str = "bold_karaoke"
    caption_style: dict | None = None
    layout: dict | None = None  # canvas do Brand Studio (None = clássico tela cheia)
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
    layout: dict | None = None  # null explícito remove o layout (volta ao clássico)
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
                       layout=k.layout, headline_template=k.headline_template,
                       is_default=k.is_default, created_at=k.created_at, updated_at=k.updated_at)


def _valida_layout_ou_422(layout: dict | None) -> None:
    if layout is None:
        return
    erros = compose.validate_layout(layout)
    if erros:
        raise HTTPException(422, "Layout inválido: " + "; ".join(erros))


def _invalidate_kit_previews(s, kit_id: str) -> None:
    """Prévias de cortes que usam este kit ficam obsoletas quando o kit muda."""
    cut_ids = [c for (c,) in s.execute(
        select(CutCandidate.id).where(CutCandidate.brand_kit_id == kit_id)).all()]
    if not cut_ids:
        return
    rows = s.execute(select(Render).where(Render.cut_id.in_(cut_ids),
                                          Render.kind == "preview")).scalars().all()
    for r in rows:
        s.delete(r)
    for cid in cut_ids:
        (config.data_dir() / "media" / "previews" / f"{cid}.mp4").unlink(missing_ok=True)


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


@router.get("/brand-kits/templates")
def list_templates():
    """Templates prontos do Brand Studio (aplicáveis a qualquer kit)."""
    return {"templates": compose.TEMPLATES}


@router.post("/brand-kits", response_model=BrandKitOut, status_code=201)
def create_kit(body: BrandKitIn):
    _valida_layout_ou_422(body.layout)
    with session() as s:
        if body.is_default:
            _clear_default(s)
        k = BrandKit(**body.model_dump())
        s.add(k)
        s.flush()
        return to_out(k)


@router.get("/brand-kits/{kit_id}/layout/effective")
def effective_layout(kit_id: str):
    """Layout para o Estúdio: o persistido, ou o equivalente do kit legado.

    Migração automática de leitura — TODO kit abre no Estúdio, sem exceção."""
    with session() as s:
        k = s.get(BrandKit, kit_id)
        if k is None:
            raise HTTPException(404, "Brand kit não encontrado")
        if k.layout:
            return {"layout": k.layout, "persisted": True}
        legado = {"logo_path": k.logo_path, "logo_position": k.logo_position,
                  "logo_opacity": k.logo_opacity}
        return {"layout": compose.layout_from_legacy(legado), "persisted": False}


@router.patch("/brand-kits/{kit_id}", response_model=BrandKitOut)
def patch_kit(kit_id: str, body: BrandKitPatch):
    with session() as s:
        k = s.get(BrandKit, kit_id)
        if k is None:
            raise HTTPException(404, "Brand kit não encontrado")
        data = body.model_dump(exclude_none=True)
        if "layout" in body.model_fields_set:  # null explícito REMOVE o layout
            _valida_layout_ou_422(body.layout)
            data["layout"] = body.layout
        if data.get("is_default"):
            _clear_default(s, except_id=kit_id)
        visual = any(f in data and getattr(k, f) != data[f] for f in VISUAL_KIT_FIELDS)
        for key, value in data.items():
            setattr(k, key, value)
        if visual:
            _invalidate_kit_previews(s, kit_id)
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
        _invalidate_kit_previews(s, kit_id)
        k.updated_at = utcnow()
        s.flush()
        return to_out(k)


@router.post("/brand-kits/{kit_id}/assets")
async def upload_asset(kit_id: str, file: UploadFile):
    """Arquivo de camada do Estúdio (imagem ou vídeo decorativo) → {"path"}."""
    if file.content_type not in ALLOWED_ASSET_TYPES:
        raise HTTPException(422, "Use PNG, JPEG, WebP, MP4 ou WebM")
    content = await file.read()
    limite = 60 * 1024 * 1024 if file.content_type.startswith("video/") else 10 * 1024 * 1024
    if len(content) > limite:
        raise HTTPException(422, f"Arquivo muito grande (máx. {limite // (1024 * 1024)} MB)")
    with session() as s:
        if s.get(BrandKit, kit_id) is None:
            raise HTTPException(404, "Brand kit não encontrado")
    dest_dir = config.data_dir() / "media" / "brand" / "assets"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{kit_id}-{uuid.uuid4().hex[:10]}{ALLOWED_ASSET_TYPES[file.content_type]}"
    dest.write_bytes(content)
    return {"path": str(dest)}
