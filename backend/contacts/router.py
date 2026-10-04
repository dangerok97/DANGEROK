"""Authenticated device address-book bridge."""
from __future__ import annotations

from typing import List, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from deps import get_current_user
from contacts.service import DeviceContactsService

router = APIRouter(prefix="/contacts", tags=["contacts"])


def _svc():
    from deps import db
    return DeviceContactsService(db)


class PhoneIn(BaseModel):
    number: str = Field(min_length=1, max_length=40)


class ContactIn(BaseModel):
    device_contact_id: str = Field(min_length=1, max_length=200)
    name: str = Field(default="", max_length=160)
    organization: str = Field(default="", max_length=160)
    aliases: List[str] = Field(default_factory=list, max_length=6)
    phones: List[PhoneIn | str] = Field(default_factory=list, max_length=4)


class SyncIn(BaseModel):
    permission: Literal["granted", "limited", "denied", "unavailable", "not_requested"]
    contacts: List[ContactIn] = Field(default_factory=list, max_length=2000)


@router.get("/status")
async def status(user=Depends(get_current_user)):
    return await _svc().status(user["user_id"])


@router.post("/device/sync")
async def sync_device_contacts(body: SyncIn, user=Depends(get_current_user)):
    contacts = [
        {
            "device_contact_id": item.device_contact_id,
            "name": item.name,
            "organization": item.organization,
            "aliases": list(item.aliases),
            "phones": [
                phone.model_dump() if isinstance(phone, PhoneIn) else phone
                for phone in item.phones
            ],
        }
        for item in body.contacts
    ]
    return await _svc().sync_snapshot(
        user["user_id"], permission=body.permission, contacts=contacts
    )
