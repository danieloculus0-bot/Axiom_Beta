import base64
from pathlib import PurePath

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Checkout, FileObject, FileVersion, utcnow
from ..storage import LocalVaultStorage
from .audit import audit


def ensure_file_object(session: Session, *, content: bytes, mime_type: str | None) -> FileObject:
    storage = LocalVaultStorage(settings.local_vault_root)
    sha256, storage_uri, byte_size = storage.put(content)
    file_object = session.scalar(select(FileObject).where(FileObject.sha256 == sha256))
    if file_object:
        return file_object
    file_object = FileObject(
        sha256=sha256,
        byte_size=byte_size,
        mime_type=mime_type,
        storage_adapter=storage.adapter_name,
        storage_uri=storage_uri,
    )
    session.add(file_object)
    session.flush()
    return file_object


def next_version_number(session: Session, record_id) -> int:
    latest = session.scalar(select(func.max(FileVersion.version_number)).where(FileVersion.record_id == record_id))
    return (latest or 0) + 1


def latest_version(session: Session, record_id) -> FileVersion | None:
    return session.scalar(select(FileVersion).where(FileVersion.record_id == record_id).order_by(FileVersion.version_number.desc()).limit(1))


def active_checkout(session: Session, record_id) -> Checkout | None:
    return session.scalar(select(Checkout).where(Checkout.record_id == record_id, Checkout.released_at.is_(None)))


def check_out(session: Session, *, record_id, actor: str, reason: str | None = None) -> Checkout:
    active = active_checkout(session, record_id)
    if active:
        raise ValueError(f"record is already checked out by {active.checked_out_by}")
    checkout = Checkout(record_id=record_id, checked_out_by=actor, reason=reason)
    session.add(checkout)
    session.flush()
    audit(session, actor=actor, action="checkout.created", entity_type="checkouts", entity_id=str(checkout.id), details={"reason": reason})
    return checkout


def assert_can_check_in(session: Session, *, record_id, actor: str) -> None:
    checkout = active_checkout(session, record_id)
    if checkout and checkout.checked_out_by != actor:
        raise ValueError(f"record is checked out by {checkout.checked_out_by}; {actor} cannot check in a new version")


def release_checkout(session: Session, *, record_id, actor: str) -> Checkout | None:
    checkout = active_checkout(session, record_id)
    if checkout:
        checkout.released_at = utcnow()
        audit(session, actor=actor, action="checkout.released", entity_type="checkouts", entity_id=str(checkout.id))
    return checkout


def cancel_checkout(session: Session, *, record_id, actor: str, reason: str | None = None, force: bool = False) -> Checkout:
    checkout = active_checkout(session, record_id)
    if not checkout:
        raise ValueError("record is not currently checked out")
    if checkout.checked_out_by != actor and not force:
        raise ValueError(f"record is checked out by {checkout.checked_out_by}; {actor} cannot cancel this checkout")
    checkout.released_at = utcnow()
    audit(
        session,
        actor=actor,
        action="checkout.cancelled",
        entity_type="checkouts",
        entity_id=str(checkout.id),
        details={"reason": reason, "force": force, "checked_out_by": checkout.checked_out_by},
    )
    return checkout


def append_version_bytes(
    session: Session,
    *,
    record,
    filename: str,
    original_source_path: str,
    content: bytes,
    customer_revision: str,
    internal_revision: str,
    metadata: dict,
    actor: str,
    mime_type: str | None = None,
) -> FileVersion:
    assert_can_check_in(session, record_id=record.id, actor=actor)
    file_object = ensure_file_object(session, content=content, mime_type=mime_type)
    previous = latest_version(session, record.id)
    version = FileVersion(
        record_id=record.id,
        file_object_id=file_object.id,
        previous_version_id=previous.id if previous else None,
        version_number=next_version_number(session, record.id),
        filename=filename or PurePath(original_source_path).name,
        original_source_path=original_source_path,
        customer_revision=customer_revision,
        internal_revision=internal_revision,
        version_metadata=metadata,
        created_by=actor,
    )
    session.add(version)
    record.customer_revision = customer_revision
    record.internal_revision = internal_revision
    audit(
        session,
        actor=actor,
        action="file_version.created",
        entity_type="file_versions",
        entity_id=str(version.id),
        details={"sha256": file_object.sha256, "original_source_path": original_source_path},
    )
    release_checkout(session, record_id=record.id, actor=actor)
    return version


def append_version(
    session: Session,
    *,
    record,
    filename: str,
    original_source_path: str,
    content_base64: str,
    customer_revision: str,
    internal_revision: str,
    metadata: dict,
    actor: str,
    mime_type: str | None = None,
) -> FileVersion:
    content = base64.b64decode(content_base64)
    return append_version_bytes(
        session,
        record=record,
        filename=filename,
        original_source_path=original_source_path,
        content=content,
        customer_revision=customer_revision,
        internal_revision=internal_revision,
        metadata=metadata,
        actor=actor,
        mime_type=mime_type,
    )
