"""Automatic tenant isolation filter for all ORM queries.

Registers a SQLAlchemy `do_orm_execute` event that injects
`WHERE tenant_id = :tenant_id` on every SELECT for models that carry
a `tenant_id` column.  The tenant_id is read from `session.info["tenant_id"]`,
set by the FastAPI dependency that resolves the tenant.

Bypass: `stmt.execution_options(ignore_tenant=True)` — logged every time.

Once `session.info["tenant_id"]` is set, every subsequent SELECT on a
tenant-aware model is filtered.  Before it's set (during tenant resolution),
queries pass through freely.  UPDATE and DELETE on ORM-loaded objects are
safe because the object was loaded through the filtered SELECT.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import with_loader_criteria
from sqlmodel import Session, SQLModel

logger = logging.getLogger("security.tenant_filter")

TENANT_MODELS: list[type] = []


def _discover_tenant_models() -> list[type]:
    """Introspect database.models and collect every table class with tenant_id."""
    from database import models as db_models

    found: list[type] = []
    for name in dir(db_models):
        cls = getattr(db_models, name)
        if (
            isinstance(cls, type)
            and issubclass(cls, SQLModel)
            and getattr(cls, "__tablename__", None)
            and hasattr(cls, "tenant_id")
        ):
            found.append(cls)
    return found


def _tenant_filter_handler(orm_execute_state: Any) -> None:
    if not orm_execute_state.is_select:
        return

    if orm_execute_state.execution_options.get("ignore_tenant"):
        logger.debug("Tenant filter BYPASS (ignore_tenant=True)")
        return

    session_info: dict = orm_execute_state.session.info
    tenant_id = session_info.get("tenant_id")

    if tenant_id is None:
        return

    for model_cls in TENANT_MODELS:
        orm_execute_state.statement = orm_execute_state.statement.options(
            with_loader_criteria(
                model_cls,
                model_cls.tenant_id == tenant_id,
                include_aliases=True,
            )
        )


def register_tenant_filter() -> None:
    """Call once at app startup to wire the filter into every Session."""
    global TENANT_MODELS
    TENANT_MODELS = _discover_tenant_models()
    event.listen(Session, "do_orm_execute", _tenant_filter_handler)
    logger.info(
        "Tenant filter registered — %d models protected: %s",
        len(TENANT_MODELS),
        ", ".join(sorted(m.__name__ for m in TENANT_MODELS)),
    )
