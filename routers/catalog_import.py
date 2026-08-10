"""routers/catalog_import.py — Onboarding masivo de catálogo (Excel + imágenes)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from database.models import Settings, User
from database.session import get_session
from services.catalog_import_service import CatalogImportService
from services.settings_service import SettingsService
from web.compat_templates import CompatTemplates
from web.dependencies import get_settings, get_tenant, require_auth

router = APIRouter(tags=["Catalog Import"])

MAX_IMAGES_PER_IMPORT = 3500
MAX_IMAGE_SIZE_BYTES = 8 * 1024 * 1024  # 8MB por imagen


def _templates():
    return CompatTemplates(directory="templates")


@router.get("/catalog-import", response_class=HTMLResponse)
def catalog_import_page(
    request: Request,
    user: User = Depends(require_auth),
    settings: Settings = Depends(get_settings),
):
    SettingsService.ensure_admin(user)
    return _templates().TemplateResponse(
        "catalog_import.html",
        {"request": request, "user": user, "settings": settings, "active_page": "catalog_import"},
    )


@router.post("/api/catalog/import")
async def import_catalog(
    excel_file: UploadFile = File(...),
    images: list[UploadFile] = File(default=[]),
    session: Session = Depends(get_session),
    user: User = Depends(require_auth),
    tenant_id: int = Depends(get_tenant),
):
    SettingsService.ensure_admin(user)

    if not excel_file.filename or not excel_file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "El archivo de datos debe ser un Excel (.xlsx/.xls)")

    if len(images) > MAX_IMAGES_PER_IMPORT:
        raise HTTPException(400, f"Máximo {MAX_IMAGES_PER_IMPORT} imágenes por importación")

    excel_bytes = await excel_file.read()

    images_payload: dict[str, bytes] = {}
    for img in images:
        content = await img.read()
        if len(content) > MAX_IMAGE_SIZE_BYTES:
            raise HTTPException(400, f"'{img.filename}' supera el tamaño máximo permitido (8MB)")
        images_payload[img.filename] = content

    try:
        result = CatalogImportService.run(session, tenant_id, excel_bytes, images_payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        session.rollback()
        raise HTTPException(500, f"No se pudo procesar la importación: {exc}")

    return {
        "status": "success",
        "products_created": result.products_created,
        "products_updated": result.products_updated,
        "images_matched": result.images_matched,
        "products_without_image": result.products_without_image,
        "unmatched_images": result.unmatched_images,
        "row_errors": result.row_errors,
    }
