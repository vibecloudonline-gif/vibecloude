"""Onboarding masivo de catálogo: Excel de datos + N imágenes nombradas por código
de producto (item_number/barcode). Reemplaza el flujo manual de import_productos.py
por una feature real, multi-tenant, disponible desde el panel.

Fase 2 del roadmap (VIBECLOUD_ROADMAP_V2.md, sección 5): "la magia" acá es el
emparejamiento automático imagen<->producto por nombre de archivo. No genera
título/descripción — eso lo define el cliente.
"""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
from sqlmodel import Session, select

from database.models import Product, Tenant

# TODO (Fase 5 del roadmap — infra confirmada): cuando se migre a DigitalOcean Spaces,
# reemplazar _save_image_bytes por un upload a bucket S3-compatible y que devuelva la
# URL pública/CDN en vez de una ruta local. El resto del matching no cambia.
UPLOAD_ROOT = "static/uploads"

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def _normalize_code(raw: str) -> str:
    """Normaliza un código de producto para poder cruzarlo: mayúsculas, sin
    espacios ni separadores repetidos. Mismo criterio se aplica al nombre del
    archivo de imagen y a la columna del Excel, para que 'A-001' == 'a_001'."""
    return re.sub(r"[^A-Z0-9]", "", raw.upper())


def _clean_str(val) -> str:
    if val is None:
        return ""
    try:
        if isinstance(val, float) and math.isnan(val):
            return ""
    except TypeError:
        pass
    s = str(val).strip()
    return "" if s.lower() == "nan" else s


def _clean_float(val, default: float = 0.0) -> float:
    try:
        f = float(val)
        return default if math.isnan(f) else f
    except (TypeError, ValueError):
        return default


def _clean_int(val, default: int = 0) -> int:
    try:
        i = int(float(val))
        return i
    except (TypeError, ValueError):
        return default


def _tenant_upload_dir(tenant_id: int) -> str:
    path = os.path.join(UPLOAD_ROOT, str(tenant_id), "products")
    os.makedirs(path, exist_ok=True)
    return path


def _save_image_bytes(tenant_id: int, code: str, filename: str, content: bytes) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        ext = ".jpg"
    safe_code = re.sub(r"[^A-Za-z0-9_-]", "_", code) or "sin_codigo"
    dest_dir = _tenant_upload_dir(tenant_id)
    dest_name = f"{safe_code}{ext}"
    dest_path = os.path.join(dest_dir, dest_name)
    with open(dest_path, "wb") as fh:
        fh.write(content)
    return f"/{dest_path.replace(os.sep, '/')}"


@dataclass
class CatalogImportResult:
    products_created: int = 0
    products_updated: int = 0
    images_matched: int = 0
    products_without_image: list[str] = field(default_factory=list)
    unmatched_images: list[str] = field(default_factory=list)
    row_errors: list[str] = field(default_factory=list)


class CatalogImportService:
    @staticmethod
    def run(
        session: Session,
        tenant_id: int,
        excel_bytes: bytes,
        images: dict[str, bytes],
    ) -> CatalogImportResult:
        """
        images: {filename_original: contenido_bytes}. El nombre de archivo (sin
        extensión) es el código de producto — se cruza contra ItemNumber o
        Barcode de cada fila del Excel.
        """
        tenant = session.get(Tenant, tenant_id)
        if not tenant:
            raise ValueError("Tenant no encontrado")

        result = CatalogImportResult()

        # Indexar imágenes por código normalizado para O(1) lookup por fila.
        images_by_code: dict[str, tuple[str, bytes]] = {}
        for filename, content in images.items():
            code_raw = os.path.splitext(filename)[0]
            code = _normalize_code(code_raw)
            if not code:
                result.unmatched_images.append(filename)
                continue
            images_by_code[code] = (filename, content)

        matched_codes: set[str] = set()

        df = pd.read_excel(pd.io.common.BytesIO(excel_bytes))

        for idx, row in df.iterrows():
            try:
                name = _clean_str(row.get("Name"))
                if not name:
                    continue

                item_number = _clean_str(row.get("ItemNumber"))
                barcode_val = _clean_str(row.get("Barcode"))
                # Código de cruce: preferí ItemNumber, si no hay usá el barcode.
                match_key = _normalize_code(item_number or barcode_val)

                price = _clean_float(row.get("Price"), 0.0)
                price_bulk = _clean_float(row.get("PriceBulk"), price)
                category = _clean_str(row.get("Category")) or None
                description = _clean_str(row.get("Description")) or None
                numeracion = _clean_str(row.get("Numeracion")) or None
                cant_bulto = _clean_int(row.get("CantBulto"), 1)

                existing = None
                if barcode_val:
                    existing = session.exec(
                        select(Product).where(
                            Product.tenant_id == tenant_id,
                            Product.barcode == barcode_val,
                        )
                    ).first()
                elif item_number:
                    existing = session.exec(
                        select(Product).where(
                            Product.tenant_id == tenant_id,
                            Product.item_number == item_number,
                        )
                    ).first()

                image_url = existing.image_url if existing else None
                if match_key and match_key in images_by_code:
                    img_filename, img_content = images_by_code[match_key]
                    image_url = _save_image_bytes(tenant_id, match_key, img_filename, img_content)
                    matched_codes.add(match_key)
                    result.images_matched += 1

                if existing:
                    existing.name = name
                    existing.price = price
                    existing.price_bulk = price_bulk
                    existing.category = category
                    existing.description = description
                    existing.numeracion = numeracion
                    existing.cant_bulto = cant_bulto
                    existing.item_number = item_number or existing.item_number
                    if image_url:
                        existing.image_url = image_url
                    session.add(existing)
                    result.products_updated += 1
                    if not existing.image_url:
                        result.products_without_image.append(item_number or barcode_val or name)
                else:
                    if not barcode_val:
                        barcode_val = f"AUTO-{tenant_id}-{idx}"
                    new_product = Product(
                        tenant_id=tenant_id,
                        name=name,
                        barcode=barcode_val,
                        item_number=item_number or None,
                        price=price,
                        price_bulk=price_bulk,
                        category=category,
                        description=description,
                        numeracion=numeracion,
                        cant_bulto=cant_bulto,
                        image_url=image_url,
                    )
                    session.add(new_product)
                    result.products_created += 1
                    if not image_url:
                        result.products_without_image.append(item_number or barcode_val or name)

            except Exception as exc:
                result.row_errors.append(f"Fila {idx + 2}: {exc}")

        session.commit()

        for code, (filename, _content) in images_by_code.items():
            if code not in matched_codes:
                result.unmatched_images.append(filename)

        return result
