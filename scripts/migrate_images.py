"""scripts/migrate_images.py — Migra imágenes de disco local a GCS.

Uso:
    python scripts/migrate_images.py --dry-run   # solo lista
    python scripts/migrate_images.py              # sube y actualiza DB
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlmodel import Session, select
from database.session import engine
from database.models import Product, LandingPage, TenantFile
from services.storage_service import get_storage, make_storage_key, _strip_exif_and_reencode, ALLOWED_CONTENT_TYPES


def guess_content_type(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(ext, "image/jpeg")


def migrate_product_images(session: Session, dry_run: bool) -> int:
    products = session.exec(
        select(Product).where(
            Product.image_url.isnot(None),
            Product.image_url != "",
            Product.is_deleted == False,
        )
    ).all()

    count = 0
    for p in products:
        if not p.image_url or not p.image_url.startswith("/static/"):
            continue

        local_path = p.image_url.lstrip("/")
        if not os.path.exists(local_path):
            print(f"  SKIP product {p.id}: archivo no existe ({local_path})")
            continue

        ct = guess_content_type(local_path)
        ext = ALLOWED_CONTENT_TYPES.get(ct, ".jpg")
        key = make_storage_key(p.tenant_id, "product", ext)

        if dry_run:
            print(f"  DRY product {p.id}: {local_path} -> {key}")
        else:
            with open(local_path, "rb") as f:
                data = f.read()
            try:
                clean, ct_out = _strip_exif_and_reencode(data, ct)
            except ValueError:
                clean, ct_out = data, ct

            storage = get_storage()
            url = storage.upload(key, clean, ct_out)
            p.image_url = url
            session.add(p)
            session.add(TenantFile(
                tenant_id=p.tenant_id, storage_key=key, file_type="product",
                original_name=os.path.basename(local_path), content_type=ct_out,
                size_bytes=len(clean), public_url=url,
            ))
            print(f"  OK  product {p.id}: {local_path} -> {url}")
        count += 1

    return count


def migrate_style_refs(session: Session, dry_run: bool) -> int:
    ref_dir = "static/images/style-refs"
    if not os.path.isdir(ref_dir):
        return 0

    landings = session.exec(
        select(LandingPage).where(
            LandingPage.reference_image_url.isnot(None),
            LandingPage.reference_image_url != "",
        )
    ).all()

    count = 0
    for lp in landings:
        if not lp.reference_image_url or not lp.reference_image_url.startswith("/static/"):
            continue

        local_path = lp.reference_image_url.lstrip("/")
        if not os.path.exists(local_path):
            print(f"  SKIP landing {lp.id}: archivo no existe ({local_path})")
            continue

        ct = guess_content_type(local_path)
        ext = ALLOWED_CONTENT_TYPES.get(ct, ".jpg")
        key = make_storage_key(lp.tenant_id, "style-ref", ext)

        if dry_run:
            print(f"  DRY landing {lp.id}: {local_path} -> {key}")
        else:
            with open(local_path, "rb") as f:
                data = f.read()
            try:
                clean, ct_out = _strip_exif_and_reencode(data, ct)
            except ValueError:
                clean, ct_out = data, ct

            storage = get_storage()
            url = storage.upload(key, clean, ct_out)
            lp.reference_image_url = url
            session.add(lp)
            session.add(TenantFile(
                tenant_id=lp.tenant_id, storage_key=key, file_type="style-ref",
                original_name=os.path.basename(local_path), content_type=ct_out,
                size_bytes=len(clean), public_url=url,
            ))
            print(f"  OK  landing {lp.id}: {local_path} -> {url}")
        count += 1

    return count


def main():
    parser = argparse.ArgumentParser(description="Migrar imágenes locales al storage configurado")
    parser.add_argument("--dry-run", action="store_true", help="Solo listar, no subir")
    args = parser.parse_args()

    print(f"=== Migración de imágenes {'(DRY RUN)' if args.dry_run else ''} ===")
    print(f"Backend: {os.getenv('STORAGE_BACKEND', 'local')}")

    with Session(engine) as session:
        print("\n-- Productos --")
        n1 = migrate_product_images(session, args.dry_run)

        print("\n-- Style refs (landings) --")
        n2 = migrate_style_refs(session, args.dry_run)

        if not args.dry_run:
            session.commit()

    print(f"\nTotal: {n1} productos, {n2} style-refs")
    if args.dry_run:
        print("(dry run — nada se subió ni modificó)")


if __name__ == "__main__":
    main()
