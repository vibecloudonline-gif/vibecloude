"""routers/network.py — VibeNet: Red de Negocios B2B"""
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlmodel import Session, select, func, or_, and_
from typing import Optional
from core.limiter import limiter
from database.session import get_session
from database.models import (
    BusinessCategory, BusinessProfile, Connection, Conversation,
    NetMessage, BusinessReview, FeedPost, Tenant, Settings, User,
    Product,
)
from services.entitlements import can_use_module, get_blocked_message
from web.dependencies import require_auth, get_tenant, get_settings
from web.compat_templates import CompatTemplates

router = APIRouter(tags=["VibeNet"])

def _templates():
    return CompatTemplates(directory="templates")

def _utcnow():
    return datetime.now(timezone.utc)


# ========== PUBLIC (sin login) ==========

@router.get("/red", response_class=HTMLResponse)
@limiter.limit("30/minute")
def red_feed(
    request: Request,
    filtro: str = "",
    session: Session = Depends(get_session),
):
    featured = session.exec(
        select(BusinessProfile).where(BusinessProfile.is_featured == True).limit(6)
    ).all()
    categories = session.exec(
        select(BusinessCategory).where(BusinessCategory.parent_id == None).order_by(BusinessCategory.name)
    ).all()
    feed_items = []
    profile_cache: dict = {}

    def _get_profile(tid: int):
        if tid not in profile_cache:
            profile_cache[tid] = session.exec(
                select(BusinessProfile).where(BusinessProfile.tenant_id == tid)
            ).first()
        return profile_cache[tid]

    if not filtro or filtro == "publicaciones":
        posts = session.exec(
            select(FeedPost).order_by(FeedPost.created_at.desc()).limit(20)
        ).all()
        for p in posts:
            feed_items.append({
                "type": "post", "created_at": p.created_at,
                "profile": _get_profile(p.tenant_id), "data": p,
            })

    if not filtro or filtro == "conexiones":
        recent_conns = session.exec(
            select(Connection).where(Connection.status == "accepted")
            .order_by(Connection.accepted_at.desc()).limit(15)
        ).all()
        for c in recent_conns:
            if c.accepted_at:
                feed_items.append({
                    "type": "connection", "created_at": c.accepted_at,
                    "profile_from": _get_profile(c.from_tenant_id),
                    "profile_to": _get_profile(c.to_tenant_id),
                    "data": c,
                })

    if not filtro or filtro == "productos":
        new_products = session.exec(
            select(Product).where(Product.is_deleted == False)
            .order_by(Product.id.desc()).limit(15)
        ).all()
        for prod in new_products:
            feed_items.append({
                "type": "product", "created_at": _utcnow(),
                "profile": _get_profile(prod.tenant_id), "data": prod,
            })

    if not filtro or filtro == "negocios":
        new_profiles = session.exec(
            select(BusinessProfile).order_by(BusinessProfile.created_at.desc()).limit(10)
        ).all()
        for bp in new_profiles:
            feed_items.append({
                "type": "new_business", "created_at": bp.created_at,
                "profile": bp, "data": bp,
            })

    feed_items.sort(key=lambda x: x["created_at"] or _utcnow(), reverse=True)
    feed_items = feed_items[:30]

    return _templates().TemplateResponse("red_feed.html", {
        "request": request, "featured": featured,
        "feed_items": feed_items, "categories": categories,
        "filtro": filtro,
    })


@router.get("/red/directorio", response_class=HTMLResponse)
@limiter.limit("30/minute")
def red_directorio(
    request: Request,
    q: str = "",
    cat: Optional[int] = None,
    ciudad: str = "",
    session: Session = Depends(get_session),
):
    query = select(BusinessProfile)
    if q:
        query = query.where(
            or_(
                BusinessProfile.display_name.ilike(f"%{q}%"),
                BusinessProfile.tagline.ilike(f"%{q}%"),
            )
        )
    if cat:
        subs = session.exec(
            select(BusinessCategory.id).where(BusinessCategory.parent_id == cat)
        ).all()
        cat_ids = [cat] + list(subs)
        query = query.where(BusinessProfile.category_id.in_(cat_ids))
    if ciudad:
        query = query.where(BusinessProfile.city.ilike(f"%{ciudad}%"))
    profiles = session.exec(query.order_by(BusinessProfile.is_featured.desc(), BusinessProfile.display_name).limit(50)).all()
    categories = session.exec(
        select(BusinessCategory).where(BusinessCategory.parent_id == None).order_by(BusinessCategory.name)
    ).all()
    cat_map = {}
    for p in profiles:
        if p.category_id and p.category_id not in cat_map:
            c = session.get(BusinessCategory, p.category_id)
            if c:
                cat_map[p.category_id] = c
    return _templates().TemplateResponse("red_directorio.html", {
        "request": request, "profiles": profiles, "categories": categories,
        "cat_map": cat_map, "q": q, "cat": cat, "ciudad": ciudad,
    })


@router.get("/red/perfil/{profile_id}", response_class=HTMLResponse)
@limiter.limit("30/minute")
def red_perfil_publico(
    request: Request,
    profile_id: int,
    tab: str = "about",
    session: Session = Depends(get_session),
):
    profile = session.get(BusinessProfile, profile_id)
    if not profile:
        raise HTTPException(404)
    category = session.get(BusinessCategory, profile.category_id) if profile.category_id else None
    reviews = session.exec(
        select(BusinessReview).where(BusinessReview.profile_id == profile.id)
        .order_by(BusinessReview.created_at.desc()).limit(20)
    ).all()
    review_tenants = {}
    for r in reviews:
        if r.reviewer_tenant_id not in review_tenants:
            rp = session.exec(
                select(BusinessProfile).where(BusinessProfile.tenant_id == r.reviewer_tenant_id)
            ).first()
            review_tenants[r.reviewer_tenant_id] = rp
    posts = session.exec(
        select(FeedPost).where(FeedPost.tenant_id == profile.tenant_id)
        .order_by(FeedPost.created_at.desc()).limit(10)
    ).all()
    conn_count = session.exec(
        select(func.count(Connection.id)).where(
            Connection.status == "accepted",
            or_(
                Connection.from_tenant_id == profile.tenant_id,
                Connection.to_tenant_id == profile.tenant_id,
            ),
        )
    ).one()
    products = session.exec(
        select(Product).where(
            Product.tenant_id == profile.tenant_id, Product.is_deleted == False,
        ).limit(12)
    ).all()
    connection_status = None
    viewer_tenant_id = None
    user_id = request.session.get("user_id")
    if user_id:
        viewer_user = session.get(User, user_id)
        if viewer_user:
            viewer_tenant_id = viewer_user.tenant_id
            if viewer_tenant_id and viewer_tenant_id != profile.tenant_id:
                existing = session.exec(
                    select(Connection).where(
                        or_(
                            and_(Connection.from_tenant_id == viewer_tenant_id, Connection.to_tenant_id == profile.tenant_id),
                            and_(Connection.from_tenant_id == profile.tenant_id, Connection.to_tenant_id == viewer_tenant_id),
                        )
                    )
                ).first()
                connection_status = existing.status if existing else None
    social_data = {}
    if profile.social_links_json:
        try:
            social_data = json.loads(profile.social_links_json)
        except (json.JSONDecodeError, TypeError):
            pass
    from database.models import TrustMetrics
    trust = session.exec(
        select(TrustMetrics).where(TrustMetrics.tenant_id == profile.tenant_id)
    ).first()
    return _templates().TemplateResponse("red_perfil.html", {
        "request": request, "profile": profile, "category": category,
        "reviews": reviews, "review_tenants": review_tenants,
        "posts": posts, "conn_count": conn_count, "products": products,
        "connection_status": connection_status,
        "viewer_tenant_id": viewer_tenant_id, "tab": tab,
        "social_data": social_data, "trust": trust,
    })


# ========== PANEL (admin) ==========

@router.get("/panel/red", response_class=HTMLResponse)
def panel_red_dashboard(
    request: Request,
    user: User = Depends(require_auth),
    settings: Settings = Depends(get_settings),
    tenant_id: int = Depends(get_tenant),
    session: Session = Depends(get_session),
):
    tenant = session.get(Tenant, tenant_id)
    if not tenant or not can_use_module(tenant, "network"):
        raise HTTPException(403, get_blocked_message("network"))
    profile = session.exec(
        select(BusinessProfile).where(BusinessProfile.tenant_id == tenant_id)
    ).first()
    pending_in = session.exec(
        select(Connection).where(
            Connection.to_tenant_id == tenant_id, Connection.status == "pending"
        )
    ).all()
    pending_in_profiles = {}
    for c in pending_in:
        p = session.exec(
            select(BusinessProfile).where(BusinessProfile.tenant_id == c.from_tenant_id)
        ).first()
        pending_in_profiles[c.from_tenant_id] = p
    accepted = session.exec(
        select(Connection).where(
            Connection.status == "accepted",
            or_(
                Connection.from_tenant_id == tenant_id,
                Connection.to_tenant_id == tenant_id,
            ),
        )
    ).all()
    acc_profiles = {}
    for c in accepted:
        other = c.to_tenant_id if c.from_tenant_id == tenant_id else c.from_tenant_id
        if other not in acc_profiles:
            p = session.exec(
                select(BusinessProfile).where(BusinessProfile.tenant_id == other)
            ).first()
            acc_profiles[other] = p
    review_count = 0
    if profile:
        review_count = session.exec(
            select(func.count(BusinessReview.id)).where(BusinessReview.profile_id == profile.id)
        ).one()
    unread_a = session.exec(
        select(func.coalesce(func.sum(Conversation.unread_a), 0)).where(
            Conversation.tenant_a_id == tenant_id
        )
    ).one()
    unread_b = session.exec(
        select(func.coalesce(func.sum(Conversation.unread_b), 0)).where(
            Conversation.tenant_b_id == tenant_id
        )
    ).one()
    unread_count = int(unread_a) + int(unread_b)
    return _templates().TemplateResponse("panel_red.html", {
        "request": request, "user": user, "settings": settings,
        "active_page": "network", "profile": profile,
        "pending_in": pending_in, "pending_in_profiles": pending_in_profiles,
        "accepted": accepted, "acc_profiles": acc_profiles,
        "review_count": review_count, "unread_count": unread_count,
    })


@router.get("/panel/red/perfil", response_class=HTMLResponse)
def panel_red_perfil_form(
    request: Request,
    user: User = Depends(require_auth),
    settings: Settings = Depends(get_settings),
    tenant_id: int = Depends(get_tenant),
    session: Session = Depends(get_session),
):
    profile = session.exec(
        select(BusinessProfile).where(BusinessProfile.tenant_id == tenant_id)
    ).first()
    categories = session.exec(
        select(BusinessCategory).order_by(BusinessCategory.name)
    ).all()
    social_data = {}
    if profile and profile.social_links_json:
        try:
            social_data = json.loads(profile.social_links_json)
        except (json.JSONDecodeError, TypeError):
            pass
    return _templates().TemplateResponse("panel_red_perfil.html", {
        "request": request, "user": user, "settings": settings,
        "active_page": "network", "profile": profile, "categories": categories,
        "social_data": social_data,
    })


@router.post("/panel/red/perfil", response_class=HTMLResponse)
def panel_red_perfil_save(
    request: Request,
    display_name: str = Form(...),
    tagline: str = Form(""),
    description: str = Form(""),
    category_id: str = Form(""),
    city: str = Form(""),
    country: str = Form("AR"),
    website_url: str = Form(""),
    social_instagram: str = Form(""),
    social_linkedin: str = Form(""),
    social_twitter: str = Form(""),
    user: User = Depends(require_auth),
    tenant_id: int = Depends(get_tenant),
    session: Session = Depends(get_session),
):
    profile = session.exec(
        select(BusinessProfile).where(BusinessProfile.tenant_id == tenant_id)
    ).first()
    socials = {}
    if social_instagram:
        socials["instagram"] = social_instagram
    if social_linkedin:
        socials["linkedin"] = social_linkedin
    if social_twitter:
        socials["twitter"] = social_twitter
    social_json = json.dumps(socials) if socials else None
    cat_id = int(category_id) if category_id else None

    if profile:
        profile.display_name = display_name
        profile.tagline = tagline or None
        profile.description = description or None
        profile.category_id = cat_id
        profile.city = city or None
        profile.country = country
        profile.website_url = website_url or None
        profile.social_links_json = social_json
    else:
        profile = BusinessProfile(
            tenant_id=tenant_id,
            display_name=display_name,
            tagline=tagline or None,
            description=description or None,
            category_id=cat_id,
            city=city or None,
            country=country,
            website_url=website_url or None,
            social_links_json=social_json,
        )
    session.add(profile)
    session.commit()
    return RedirectResponse("/panel/red", status_code=302)


@router.post("/panel/red/conectar/{target_tenant_id}")
def panel_red_connect(
    request: Request,
    target_tenant_id: int,
    connection_type: str = Form("partner"),
    message: str = Form(""),
    user: User = Depends(require_auth),
    tenant_id: int = Depends(get_tenant),
    session: Session = Depends(get_session),
):
    if target_tenant_id == tenant_id:
        raise HTTPException(400, "No podés conectarte con vos mismo")
    existing = session.exec(
        select(Connection).where(
            or_(
                and_(Connection.from_tenant_id == tenant_id, Connection.to_tenant_id == target_tenant_id),
                and_(Connection.from_tenant_id == target_tenant_id, Connection.to_tenant_id == tenant_id),
            )
        )
    ).first()
    if existing:
        return RedirectResponse("/panel/red", status_code=302)
    conn = Connection(
        from_tenant_id=tenant_id,
        to_tenant_id=target_tenant_id,
        connection_type=connection_type,
        message=message or None,
    )
    session.add(conn)
    session.commit()
    return RedirectResponse("/panel/red", status_code=302)


@router.post("/panel/red/aceptar/{conn_id}")
def panel_red_accept(
    request: Request,
    conn_id: int,
    user: User = Depends(require_auth),
    tenant_id: int = Depends(get_tenant),
    session: Session = Depends(get_session),
):
    conn = session.exec(
        select(Connection).where(Connection.id == conn_id, Connection.to_tenant_id == tenant_id)
    ).first()
    if not conn:
        raise HTTPException(404)
    conn.status = "accepted"
    conn.accepted_at = _utcnow()
    session.add(conn)
    session.commit()
    return RedirectResponse("/panel/red", status_code=302)


@router.post("/panel/red/rechazar/{conn_id}")
def panel_red_reject(
    request: Request,
    conn_id: int,
    user: User = Depends(require_auth),
    tenant_id: int = Depends(get_tenant),
    session: Session = Depends(get_session),
):
    conn = session.exec(
        select(Connection).where(Connection.id == conn_id, Connection.to_tenant_id == tenant_id)
    ).first()
    if not conn:
        raise HTTPException(404)
    conn.status = "rejected"
    session.add(conn)
    session.commit()
    return RedirectResponse("/panel/red", status_code=302)


@router.get("/panel/red/inbox", response_class=HTMLResponse)
def panel_red_inbox(
    request: Request,
    user: User = Depends(require_auth),
    settings: Settings = Depends(get_settings),
    tenant_id: int = Depends(get_tenant),
    session: Session = Depends(get_session),
):
    convos = session.exec(
        select(Conversation).where(
            or_(Conversation.tenant_a_id == tenant_id, Conversation.tenant_b_id == tenant_id)
        ).order_by(Conversation.last_message_at.desc())
    ).all()
    convo_data = []
    for c in convos:
        other_tid = c.tenant_b_id if c.tenant_a_id == tenant_id else c.tenant_a_id
        other_prof = session.exec(
            select(BusinessProfile).where(BusinessProfile.tenant_id == other_tid)
        ).first()
        unread = c.unread_a if c.tenant_a_id == tenant_id else c.unread_b
        last_msg = session.exec(
            select(NetMessage).where(NetMessage.conversation_id == c.id)
            .order_by(NetMessage.created_at.desc()).limit(1)
        ).first()
        convo_data.append({
            "convo": c, "other_profile": other_prof,
            "unread": unread, "last_msg": last_msg,
        })
    return _templates().TemplateResponse("panel_red_inbox.html", {
        "request": request, "user": user, "settings": settings,
        "active_page": "network", "convo_data": convo_data, "active_convo": None,
        "messages": [], "tenant_id": tenant_id,
    })


@router.get("/panel/red/inbox/{convo_id}", response_class=HTMLResponse)
def panel_red_inbox_thread(
    request: Request,
    convo_id: int,
    user: User = Depends(require_auth),
    settings: Settings = Depends(get_settings),
    tenant_id: int = Depends(get_tenant),
    session: Session = Depends(get_session),
):
    convo = session.exec(
        select(Conversation).where(
            Conversation.id == convo_id,
            or_(Conversation.tenant_a_id == tenant_id, Conversation.tenant_b_id == tenant_id),
        )
    ).first()
    if not convo:
        raise HTTPException(404)
    if convo.tenant_a_id == tenant_id:
        convo.unread_a = 0
    else:
        convo.unread_b = 0
    session.add(convo)
    session.commit()
    msgs = session.exec(
        select(NetMessage).where(NetMessage.conversation_id == convo_id)
        .order_by(NetMessage.created_at.asc())
    ).all()
    other_tid = convo.tenant_b_id if convo.tenant_a_id == tenant_id else convo.tenant_a_id
    other_prof = session.exec(
        select(BusinessProfile).where(BusinessProfile.tenant_id == other_tid)
    ).first()
    convos_all = session.exec(
        select(Conversation).where(
            or_(Conversation.tenant_a_id == tenant_id, Conversation.tenant_b_id == tenant_id)
        ).order_by(Conversation.last_message_at.desc())
    ).all()
    convo_data = []
    for c in convos_all:
        ot = c.tenant_b_id if c.tenant_a_id == tenant_id else c.tenant_a_id
        op = session.exec(select(BusinessProfile).where(BusinessProfile.tenant_id == ot)).first()
        ur = c.unread_a if c.tenant_a_id == tenant_id else c.unread_b
        lm = session.exec(
            select(NetMessage).where(NetMessage.conversation_id == c.id)
            .order_by(NetMessage.created_at.desc()).limit(1)
        ).first()
        convo_data.append({"convo": c, "other_profile": op, "unread": ur, "last_msg": lm})
    return _templates().TemplateResponse("panel_red_inbox.html", {
        "request": request, "user": user, "settings": settings,
        "active_page": "network", "convo_data": convo_data,
        "active_convo": convo, "messages": msgs,
        "other_profile": other_prof, "tenant_id": tenant_id,
    })


@router.post("/panel/red/inbox/{convo_id}/enviar")
def panel_red_send_message(
    request: Request,
    convo_id: int,
    body: str = Form(...),
    user: User = Depends(require_auth),
    tenant_id: int = Depends(get_tenant),
    session: Session = Depends(get_session),
):
    convo = session.exec(
        select(Conversation).where(
            Conversation.id == convo_id,
            or_(Conversation.tenant_a_id == tenant_id, Conversation.tenant_b_id == tenant_id),
        )
    ).first()
    if not convo:
        raise HTTPException(404)
    msg = NetMessage(
        conversation_id=convo_id,
        sender_tenant_id=tenant_id,
        body=body.strip(),
    )
    session.add(msg)
    convo.last_message_at = _utcnow()
    if convo.tenant_a_id == tenant_id:
        convo.unread_b += 1
    else:
        convo.unread_a += 1
    session.add(convo)
    session.commit()
    return RedirectResponse(f"/panel/red/inbox/{convo_id}", status_code=302)


@router.post("/panel/red/mensaje/{target_tenant_id}")
def panel_red_start_convo(
    request: Request,
    target_tenant_id: int,
    body: str = Form(...),
    user: User = Depends(require_auth),
    tenant_id: int = Depends(get_tenant),
    session: Session = Depends(get_session),
):
    a, b = sorted([tenant_id, target_tenant_id])
    convo = session.exec(
        select(Conversation).where(
            Conversation.tenant_a_id == a, Conversation.tenant_b_id == b
        )
    ).first()
    if not convo:
        convo = Conversation(tenant_a_id=a, tenant_b_id=b, last_message_at=_utcnow())
        session.add(convo)
        session.commit()
        session.refresh(convo)
    msg = NetMessage(conversation_id=convo.id, sender_tenant_id=tenant_id, body=body.strip())
    session.add(msg)
    convo.last_message_at = _utcnow()
    if convo.tenant_a_id == tenant_id:
        convo.unread_b += 1
    else:
        convo.unread_a += 1
    session.add(convo)
    session.commit()
    return RedirectResponse(f"/panel/red/inbox/{convo.id}", status_code=302)


@router.get("/panel/red/inbox/unread")
def panel_red_unread_count(
    request: Request,
    user: User = Depends(require_auth),
    tenant_id: int = Depends(get_tenant),
    session: Session = Depends(get_session),
):
    total = 0
    convos = session.exec(
        select(Conversation).where(
            or_(Conversation.tenant_a_id == tenant_id, Conversation.tenant_b_id == tenant_id)
        )
    ).all()
    for c in convos:
        total += c.unread_a if c.tenant_a_id == tenant_id else c.unread_b
    return JSONResponse({"unread": total})


@router.post("/panel/red/publicar")
def panel_red_post(
    request: Request,
    title: str = Form(...),
    body: str = Form(""),
    post_type: str = Form("article"),
    user: User = Depends(require_auth),
    tenant_id: int = Depends(get_tenant),
    session: Session = Depends(get_session),
):
    post = FeedPost(
        tenant_id=tenant_id,
        post_type=post_type,
        title=title,
        body=body or None,
    )
    session.add(post)
    session.commit()
    return RedirectResponse("/panel/red", status_code=302)


@router.post("/panel/red/review/{profile_id}")
def panel_red_review(
    request: Request,
    profile_id: int,
    rating: int = Form(...),
    title: str = Form(""),
    comment: str = Form(""),
    user: User = Depends(require_auth),
    tenant_id: int = Depends(get_tenant),
    session: Session = Depends(get_session),
):
    profile = session.get(BusinessProfile, profile_id)
    if not profile:
        raise HTTPException(404)
    if profile.tenant_id == tenant_id:
        raise HTTPException(400, "No podés reseñarte a vos mismo")
    is_connected = session.exec(
        select(Connection).where(
            Connection.status == "accepted",
            or_(
                and_(Connection.from_tenant_id == tenant_id, Connection.to_tenant_id == profile.tenant_id),
                and_(Connection.from_tenant_id == profile.tenant_id, Connection.to_tenant_id == tenant_id),
            ),
        )
    ).first()
    from services.trust_service import check_verified_purchase
    is_verified_buyer = check_verified_purchase(session, tenant_id, profile.tenant_id)
    review = BusinessReview(
        profile_id=profile_id,
        reviewer_tenant_id=tenant_id,
        rating=max(1, min(5, rating)),
        title=title or None,
        comment=comment or None,
        is_verified_connection=bool(is_connected),
        is_verified_purchase=is_verified_buyer,
    )
    session.add(review)
    session.commit()
    avg = session.exec(
        select(func.avg(BusinessReview.rating)).where(BusinessReview.profile_id == profile_id)
    ).one()
    if avg is not None:
        from decimal import Decimal
        profile.avg_rating = Decimal(str(round(float(avg), 2)))
        session.add(profile)
        session.commit()
    return RedirectResponse(f"/red/perfil/{profile_id}", status_code=302)
