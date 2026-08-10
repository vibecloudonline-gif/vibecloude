"""web/pagination.py — Utilidad de paginación para SQLModel"""
from typing import TypeVar, Generic, List, Optional
from pydantic import BaseModel
from sqlmodel import Session, select, func, SQLModel

T = TypeVar("T")

class Page(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    size: int
    pages: int

def paginate(session: Session, query, page: int = 1, size: int = 50) -> Page[T]:
    if page < 1: page = 1
    total = session.exec(select(func.count()).select_from(query.subquery())).one()
    pages = (total + size - 1) // size
    
    items = session.exec(query.offset((page - 1) * size).limit(size)).all()
    
    return Page(
        items=items,
        total=total,
        page=page,
        size=size,
        pages=pages
    )
