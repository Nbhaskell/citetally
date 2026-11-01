"""Vendors and categories (docs/TRD.md section 7)."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter

from citetally import repository as repo
from citetally.api.deps import Conn, RequestId, State
from citetally.api.errors import ApiError
from citetally.api.schemas import (
    AliasCreate,
    CategoryOut,
    VendorCreate,
    VendorMerge,
    VendorOut,
    VendorUpdate,
)
from citetally.checks import run_checks
from citetally.db import transaction
from citetally.matching import normalize_name
from citetally.models import DocumentStatus as S
from citetally.models import Vendor

router = APIRouter(prefix="/api", tags=["vendors"])


def vendor_out(
    conn: sqlite3.Connection,
    vendor: Vendor,
    usage: dict[int, tuple[int, int, str | None]] | None = None,
) -> VendorOut:
    category = (
        repo.get_category(conn, vendor.default_category_id) if vendor.default_category_id else None
    )
    entries, waiting, last_date = (usage or repo.vendor_usage(conn)).get(vendor.id, (0, 0, None))
    return VendorOut(
        id=vendor.id,
        name=vendor.name,
        default_category=category.code if category else None,
        default_currency=vendor.default_currency,
        is_active=vendor.is_active,
        aliases=[a.alias for a in repo.list_vendor_aliases(conn, vendor.id)],
        entry_count=entries,
        waiting_count=waiting,
        last_entry_date=last_date,
    )


def _name_taken(
    conn: sqlite3.Connection, text: str, *, allow_vendor: int | None = None
) -> Vendor | None:
    """The vendor that already answers to this name; refuses if it is not `allow_vendor`."""
    known = repo.find_vendor_by_normalized(conn, normalize_name(text))
    if known is not None and known.id != allow_vendor:
        raise ApiError(
            409,
            "vendor_exists",
            "A vendor or alias with that name already exists.",
            {"vendor_id": known.id},
        )
    return known


@router.get("/vendors", response_model=list[VendorOut])
def list_vendors(conn: Conn, include_inactive: bool = False) -> list[VendorOut]:
    usage = repo.vendor_usage(conn)
    return [
        vendor_out(conn, vendor, usage)
        for vendor in repo.list_vendors(conn, active_only=not include_inactive)
    ]


@router.post("/vendors", response_model=VendorOut, status_code=201)
def create_vendor(body: VendorCreate, conn: Conn, state: State) -> VendorOut:
    _name_taken(conn, body.name)
    category = (
        repo.get_category_by_code(conn, body.default_category) if body.default_category else None
    )
    vendor = repo.create_vendor(
        conn,
        body.name,
        normalize_name(body.name),
        default_category_id=category.id if category else None,
        default_currency=body.default_currency,
        is_synthetic=state.settings.synthetic_data,
    )
    return vendor_out(conn, vendor)


@router.patch("/vendors/{vendor_id}", response_model=VendorOut)
def update_vendor(vendor_id: int, body: VendorUpdate, conn: Conn) -> VendorOut:
    vendor = repo.get_vendor(conn, vendor_id)
    if "default_category" in body.model_fields_set:
        category = (
            repo.get_category_by_code(conn, body.default_category)
            if body.default_category
            else None
        )
        repo.set_vendor_category(conn, vendor_id, category.id if category else None)
        vendor = repo.get_vendor(conn, vendor_id)
    return vendor_out(conn, vendor)


@router.post("/vendors/{vendor_id}/aliases", response_model=VendorOut, status_code=201)
def add_alias(vendor_id: int, body: AliasCreate, conn: Conn) -> VendorOut:
    vendor = repo.get_vendor(conn, vendor_id)
    if _name_taken(conn, body.alias, allow_vendor=vendor_id) is None:  # else it already answers
        repo.add_alias(conn, vendor_id, body.alias, normalize_name(body.alias))
    return vendor_out(conn, vendor)


@router.post("/vendors/{vendor_id}/merge", response_model=VendorOut)
def merge_vendor(
    vendor_id: int, body: VendorMerge, conn: Conn, state: State, request_id: RequestId
) -> VendorOut:
    """Fold this vendor into another. Documents still waiting for review are checked again."""
    with transaction(conn):
        moved = repo.merge_vendors(conn, vendor_id, body.into)
        for document_id in moved:
            if repo.get_document(conn, document_id).status is S.NEEDS_REVIEW:
                run_checks(conn, document_id, settings=state.settings, request_id=request_id)
    return vendor_out(conn, repo.get_vendor(conn, body.into))


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(conn: Conn) -> list[CategoryOut]:
    return [CategoryOut.model_validate(c) for c in repo.list_categories(conn)]
