"""routers/platform.py — Landing publica de VibeCloud (marketing)."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["Platform"])


@router.get("/plataforma", response_class=HTMLResponse)
def platform_landing(request: Request):
    from web.compat_templates import CompatTemplates
    tpl = CompatTemplates(directory="templates")
    return tpl.TemplateResponse("platform_landing.html", {"request": request})
