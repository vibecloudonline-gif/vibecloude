import os
os.environ["SECRET_KEY"] = "testsecretkey123"
os.environ["VIBECLOUD_API_KEY"] = "I9StON-hofzi783VWEhFYFM1DCXGJc08SBE1olJhDqI="

import pytest
from database.models import (
    BusinessCategory, BusinessProfile, Connection, Conversation,
    NetMessage, BusinessReview, FeedPost,
)


def test_business_category_fields():
    c = BusinessCategory(name="Tech", slug="tech", icon="💻")
    assert c.name == "Tech"
    assert c.slug == "tech"
    assert c.icon == "💻"
    assert c.parent_id is None


def test_business_profile_fields():
    p = BusinessProfile(
        tenant_id=1, display_name="Acme Corp", tagline="We build things",
        city="Buenos Aires", country="AR",
    )
    assert p.display_name == "Acme Corp"
    assert p.tenant_id == 1
    assert p.is_verified is False
    assert p.is_featured is False
    assert p.avg_rating == 0.0


def test_connection_fields():
    c = Connection(
        from_tenant_id=1, to_tenant_id=2,
        connection_type="partner", status="pending",
        message="Let's connect!",
    )
    assert c.status == "pending"
    assert c.connection_type == "partner"
    assert c.accepted_at is None


def test_conversation_defaults():
    c = Conversation(tenant_a_id=1, tenant_b_id=2)
    assert c.unread_a == 0
    assert c.unread_b == 0


def test_net_message_fields():
    m = NetMessage(conversation_id=1, sender_tenant_id=1, body="Hola!")
    assert m.body == "Hola!"
    assert m.read_at is None


def test_business_review_fields():
    r = BusinessReview(
        profile_id=1, reviewer_tenant_id=2,
        rating=4, title="Great service", comment="Would recommend",
    )
    assert r.rating == 4
    assert r.is_verified_connection is False
    assert r.owner_response is None


def test_feed_post_fields():
    f = FeedPost(
        tenant_id=1, post_type="article",
        title="Launch day!", body="We just launched our product.",
    )
    assert f.post_type == "article"
    assert f.likes_count == 0
    assert f.is_pinned is False


def test_feed_endpoint_exists():
    from routers.network import router
    routes = [r.path for r in router.routes]
    assert "/red" in routes


def test_directorio_endpoint_exists():
    from routers.network import router
    routes = [r.path for r in router.routes]
    assert "/red/directorio" in routes


def test_perfil_endpoint_exists():
    from routers.network import router
    routes = [r.path for r in router.routes]
    assert "/red/perfil/{profile_id}" in routes


def test_panel_red_endpoint_exists():
    from routers.network import router
    routes = [r.path for r in router.routes]
    assert "/panel/red" in routes


def test_inbox_endpoint_exists():
    from routers.network import router
    routes = [r.path for r in router.routes]
    assert "/panel/red/inbox" in routes


def test_publicar_endpoint_exists():
    from routers.network import router
    routes = [r.path for r in router.routes]
    assert "/panel/red/publicar" in routes
