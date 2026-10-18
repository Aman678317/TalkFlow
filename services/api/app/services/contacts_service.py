"""Contacts service: phonebook CRUD, CSV import/export, consent ledger.

Canonical phone key is E.164 per organization (uq_contact_org_phone).
Consent rows are append-only evidence; the newest decision wins and the
Contact.do_not_call mirror flag is updated on every new decision.
"""
from __future__ import annotations

import csv
import io
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as M
from app.db.base import utcnow
from app.errors import ConflictError, NotFoundError, ValidationError
from app.services import audit_service
from app.telephony.phone_number_service import PhoneNumberService

log = logging.getLogger("app.services.contacts")

# Header aliases the CSV importer accepts (lower-cased).
_HEADER_ALIASES = {
    "phone": "phone", "phone_number": "phone", "number": "phone",
    "e164": "phone", "msisdn": "phone", "telephone": "phone",
    "name": "name", "display_name": "name", "contact_name": "name", "full_name": "name",
    "language": "language", "lang": "language", "locale": "language",
    "country": "country", "country_code": "country", "default_country": "country",
    "timezone": "timezone", "tz": "timezone",
    "email": "email",
    "notes": "notes", "note": "notes",
    "tags": "tags",
}


@dataclass(frozen=True)
class ContactRow:
    phone: str
    name: str = ""
    language: str = "en"
    country: str = ""
    timezone: str = ""
    email: str | None = None
    notes: str = ""
    tags: list[str] | None = None


@dataclass(frozen=True)
class ImportReport:
    imported: int = 0
    updated: int = 0
    duplicates_in_file: int = 0
    invalid: list[dict] | None = None  # [{"row": n, "phone": raw, "error": msg}]

    def to_dict(self) -> dict:
        return {
            "imported": self.imported,
            "updated": self.updated,
            "duplicates_in_file": self.duplicates_in_file,
            "invalid": self.invalid or [],
        }


class ContactsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # Validation helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def raw_to_row(raw: dict, default_country: str = "") -> tuple["ContactRow" | None, str | None]:
        """Normalize one import row. Returns (ContactRow, None) or (None, error)."""
        phone_raw = str(raw.get("phone") or "").strip()
        if not phone_raw:
            return None, "missing phone number"
        default_country = (str(raw.get("country") or "") or default_country or "US").strip() or "US"
        e164 = PhoneNumberService.normalize_to_e164(phone_raw, default_country=default_country)
        is_valid, err = PhoneNumberService.validate_e164(e164)
        if not is_valid:
            return None, err or "invalid phone number"
        language = (str(raw.get("language") or "").strip() or "en")[:16]
        name = str(raw.get("name") or "").strip()[:200]
        tags_raw = str(raw.get("tags") or "").strip()
        tags = [t.strip() for t in tags_raw.replace(";", ",").split(",") if t.strip()]
        country = (str(raw.get("country") or "").strip().upper() or "")[:8]
        return ContactRow(
            phone=e164,
            name=name,
            language=language,
            country=country,
            timezone=str(raw.get("timezone") or "").strip()[:64],
            email=(str(raw.get("email") or "").strip() or None),
            notes=str(raw.get("notes") or "").strip(),
            tags=tags,
        ), None

    async def _existing_contact(self, org_id: uuid.UUID, e164: str) -> M.Contact | None:
        res = await self.db.execute(
            select(M.Contact).where(M.Contact.org_id == org_id, M.Contact.phone_e164 == e164))
        return res.scalars().first()

    # ------------------------------------------------------------------ #
    # CRUD
    # ------------------------------------------------------------------ #

    async def create_contact(self, *, org_id: uuid.UUID, phone: str, display_name: str = "",
                             language: str = "en", country: str = "", timezone: str = "",
                             email: str | None = None, notes: str = "",
                             tags: list[str] | None = None,
                             default_country: str = "US",
                             actor_id: uuid.UUID | None = None) -> M.Contact:
        e164 = PhoneNumberService.normalize_to_e164(phone, default_country=default_country)
        is_valid, err = PhoneNumberService.validate_e164(e164)
        if not is_valid:
            raise ValidationError(err or "Invalid phone number.")
        if await self._existing_contact(org_id, e164) is not None:
            raise ConflictError(f"Contact with phone {e164} already exists in this organization.")
        contact = M.Contact(
            org_id=org_id,
            phone_e164=e164,
            display_name=display_name[:200],
            language=(language or "en")[:16],
            country=(country or "")[:8].upper(),
            timezone=timezone[:64],
            email=email,
            notes=notes,
            tags_json=list(tags or []),
        )
        self.db.add(contact)
        await self.db.flush()
        await audit_service.record(
            self.db, action="contact.create", org_id=org_id, actor_id=actor_id,
            resource_type="contact", resource_id=str(contact.id))
        return contact

    async def get_contact(self, org_id: uuid.UUID, contact_id: uuid.UUID) -> M.Contact:
        """Org-scoped fetch: a contact from another org is simply NOT FOUND."""
        row = await self.db.get(M.Contact, contact_id)
        if row is None or row.org_id != org_id:
            raise NotFoundError("Contact not found.")
        return row

    async def list_contacts(self, *, org_id: uuid.UUID, include_archived: bool = False,
                            query: str = "", archived: bool | None = None,
                            limit: int = 50, offset: int = 0
                            ) -> tuple[list[M.Contact], int]:
        stmt = select(M.Contact).where(M.Contact.org_id == org_id)
        if archived is not None:
            stmt = stmt.where(M.Contact.archived == archived)
        elif not include_archived:
            stmt = stmt.where(M.Contact.archived == False)  # noqa: E712
        if query:
            stmt = stmt.where(M.Contact.display_name.ilike(f"%{query}%"))
        total_res = await self.db.execute(
            select(func.count()).select_from(stmt.subquery()))
        total = int(total_res.scalar() or 0)
        stmt = stmt.order_by(M.Contact.created_at.desc()).limit(limit).offset(offset)
        res = await self.db.execute(stmt)
        return list(res.scalars().all()), total

    async def update_contact(self, org_id: uuid.UUID, contact_id: uuid.UUID, *,
                             display_name: str | None = None, language: str | None = None,
                             timezone: str | None = None, email: str | None = None,
                             notes: str | None = None, tags: list[str] | None = None
                             ) -> M.Contact:
        contact = await self.get_contact(org_id, contact_id)
        if display_name is not None:
            contact.display_name = display_name[:200]
        if language is not None:
            contact.language = (language or "en")[:16]
        if timezone is not None:
            contact.timezone = timezone[:64]
        if email is not None:
            contact.email = email or None
        if notes is not None:
            contact.notes = notes
        if tags is not None:
            contact.tags_json = list(tags)
        contact.updated_at = utcnow()
        await self.db.flush()
        return contact

    async def archive_contact(self, org_id: uuid.UUID, contact_id: uuid.UUID, *,
                              actor_id: uuid.UUID | None = None) -> M.Contact:
        contact = await self.get_contact(org_id, contact_id)
        contact.archived = True
        contact.updated_at = utcnow()
        await self.db.flush()
        await audit_service.record(
            self.db, action="contact.archive", org_id=org_id, actor_id=actor_id,
            resource_type="contact", resource_id=str(contact.id))
        return contact

    # ------------------------------------------------------------------ #
    # CSV import / export
    # ------------------------------------------------------------------ #

    def parse_csv(self, file_bytes: bytes) -> tuple[list[dict], list[str]]:
        text = file_bytes.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        headers = [h.strip() for h in (reader.fieldnames or [])]
        rows_out: list[dict] = []
        for raw_row in reader:
            row: dict = {}
            for key, value in raw_row.items():
                if key is None:
                    continue
                canonical = _HEADER_ALIASES.get(key.strip().lower())
                if canonical:
                    row[canonical] = value
            rows_out.append(row)
        return rows_out, headers

    async def import_csv(self, *, org_id: uuid.UUID, data: bytes,
                         default_country: str = "US",
                         actor_id: uuid.UUID | None = None,
                         source: str = "imported_csv") -> ImportReport:
        rows, _headers = self.parse_csv(data)
        invalid: list[dict] = []
        seen: dict[str, int] = {}
        parsed: list[tuple[int, ContactRow]] = []
        row_no = 1
        for raw in rows:
            row_no += 1
            parsed_row, err = self.raw_to_row(raw, default_country=default_country)
            if err is not None:
                invalid.append({"row": row_no, "phone": str(raw.get("phone") or ""), "error": err})
                continue
            if parsed_row.phone in seen:
                invalid.append({"row": row_no, "phone": parsed_row.phone,
                                "error": "duplicate row in file"})
                seen[parsed_row.phone] += 1
                continue
            seen[parsed_row.phone] = row_no
            parsed.append((row_no, parsed_row))

        imported = 0
        updated = 0
        duplicates_in_file = 0
        for _row_no, row in parsed:
            existing = await self._existing_contact(org_id, row.phone)
            if existing is None:
                self.db.add(M.Contact(
                    org_id=org_id,
                    phone_e164=row.phone,
                    display_name=row.name,
                    language=row.language,
                    country=row.country,
                    timezone=row.timezone,
                    email=row.email,
                    notes=row.notes,
                    tags_json=list(row.tags or []),
                ))
                imported += 1
            else:
                if existing.archived:
                    existing.archived = False
                if row.name:
                    existing.display_name = row.name
                if row.language and row.language != "en":
                    existing.language = row.language
                if row.country:
                    existing.country = row.country
                if row.timezone:
                    existing.timezone = row.timezone
                if row.email:
                    existing.email = row.email
                if row.notes:
                    existing.notes = row.notes
                if row.tags:
                    merged = list(dict.fromkeys([*(existing.tags_json or []), *row.tags]))
                    existing.tags_json = merged
                existing.updated_at = utcnow()
                updated += 1
        if invalid and len(invalid) == len(rows):
            duplicates_in_file = sum(1 for i in invalid if i["error"] == "duplicate row in file")
        if imported or updated:
            await audit_service.record(
                self.db, action="contacts.import", org_id=org_id, actor_id=actor_id,
                resource_type="contact", resource_id=f"csv:{imported}+{updated}",
                details={"invalid_rows": len(invalid)})
        return ImportReport(imported=imported, updated=updated,
                            duplicates_in_file=duplicates_in_file, invalid=invalid)

    def export_rows(self, contacts: list[M.Contact]) -> bytes:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["phone", "name", "language", "country", "timezone",
                         "email", "notes", "tags", "do_not_call", "archived"])
        for c in contacts:
            writer.writerow([
                c.phone_e164, c.display_name, c.language, c.country, c.timezone,
                c.email or "", c.notes,
                ",".join(c.tags_json or []),
                "1" if c.do_not_call else "0",
                "1" if c.archived else "0",
            ])
        return buf.getvalue().encode("utf-8")

    # ------------------------------------------------------------------ #
    # Consent ledger (append-only)
    # ------------------------------------------------------------------ #

    async def record_consent(self, *, org_id: uuid.UUID, contact_id: uuid.UUID,
                             decision: str, source: str, note: str = "",
                             evidence: dict | None = None,
                             actor_id: uuid.UUID | None = None) -> M.ContactConsent:
        if decision not in ("grant", "revoke", "dnc"):
            raise ValidationError("decision must be one of: grant, revoke, dnc")
        allowed_sources = ("manual_entry", "imported_csv", "call_prompt",
                           "customer_portal", "verbal_note")
        if source not in allowed_sources:
            raise ValidationError(f"source must be one of: {', '.join(allowed_sources)}")
        contact = await self.get_contact(org_id, contact_id)
        row = M.ContactConsent(
            org_id=org_id,
            contact_id=contact_id,
            channel="phone",
            decision=decision,
            source=source,
            evidence_json=dict(evidence or {}),
            note=note,
            recorded_by=actor_id,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(row)
        if decision in ("revoke", "dnc"):
            contact.do_not_call = True
        elif decision == "grant":
            contact.do_not_call = False
        contact.updated_at = utcnow()
        await self.db.flush()
        await audit_service.record(
            self.db, action=f"contact.consent.{decision}", org_id=org_id, actor_id=actor_id,
            resource_type="contact", resource_id=str(contact_id),
            details={"source": source})
        return row

    async def consent_history(self, org_id: uuid.UUID, contact_id: uuid.UUID
                              ) -> list[M.ContactConsent]:
        await self.get_contact(org_id, contact_id)
        res = await self.db.execute(
            select(M.ContactConsent)
            .where(M.ContactConsent.org_id == org_id, M.ContactConsent.contact_id == contact_id)
            .order_by(M.ContactConsent.created_at.desc()))
        return list(res.scalars().all())

    async def effective_consent(self, org_id: uuid.UUID, contact_id: uuid.UUID
                                ) -> bool | None:
        """True/False from the newest ledger row; None when the ledger is empty."""
        rows = await self.consent_history(org_id, contact_id)
        if not rows:
            return None
        return rows[0].decision == "grant"

    # ------------------------------------------------------------------ #
    # Contact <-> document pivot
    # ------------------------------------------------------------------ #

    async def attach_document(self, *, org_id: uuid.UUID, contact_id: uuid.UUID,
                              document_id: uuid.UUID,
                              actor_id: uuid.UUID | None = None) -> M.ContactDocument:
        contact = await self.get_contact(org_id, contact_id)
        doc = await self.db.get(M.Document, document_id)
        if doc is None or doc.org_id != org_id:
            raise NotFoundError("Document not found in this organization.")
        exists = await self.db.execute(
            select(M.ContactDocument).where(
                M.ContactDocument.contact_id == contact_id,
                M.ContactDocument.document_id == document_id))
        if exists.scalars().first() is not None:
            raise ConflictError("Document already attached to this contact.")
        pivot = M.ContactDocument(
            contact_id=contact_id, document_id=document_id, org_id=org_id,
            attached_by=actor_id)
        self.db.add(pivot)
        await self.db.flush()
        await audit_service.record(
            self.db, action="contact.document.attach", org_id=org_id, actor_id=actor_id,
            resource_type="contact", resource_id=str(contact.id),
            details={"document_id": str(document_id)})
        return pivot

    async def list_documents(self, org_id: uuid.UUID, contact_id: uuid.UUID
                             ) -> list[M.Document]:
        await self.get_contact(org_id, contact_id)
        res = await self.db.execute(
            select(M.Document)
            .join(M.ContactDocument, M.ContactDocument.document_id == M.Document.id)
            .where(M.ContactDocument.contact_id == contact_id,
                   M.ContactDocument.org_id == org_id)
            .order_by(M.ContactDocument.created_at.desc()))
        return list(res.scalars().all())
