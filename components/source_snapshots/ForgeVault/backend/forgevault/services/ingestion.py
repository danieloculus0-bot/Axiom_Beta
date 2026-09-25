import base64
from binascii import Error as Base64Error

from sqlalchemy.orm import Session

from ..models import Dependency, IngestJob, utcnow
from .audit import audit
from .metadata import create_record, ensure_metadata_field_definitions, find_record_by_identity
from .plugins import merge_metadata, run_ingest_plugins
from .versioning import append_version_bytes


def _decode_content(content_base64: str) -> bytes:
    try:
        return base64.b64decode(content_base64, validate=True)
    except (Base64Error, ValueError) as exc:
        raise ValueError("content_base64 must be valid base64") from exc


def ingest_file(
    session: Session,
    *,
    filename: str,
    original_source_path: str,
    content_base64: str,
    customer_part_number: str,
    customer_revision: str,
    internal_revision: str,
    metadata: dict,
    actor: str,
    mime_type: str | None = None,
) -> tuple[IngestJob, object, object]:
    content = _decode_content(content_base64)
    job = IngestJob(
        status="running",
        staging_uri=f"staging://inline/{filename}",
        original_source_path=original_source_path,
        detected_metadata=metadata,
        submitted_by=actor,
    )
    session.add(job)
    session.flush()
    try:
        plugin_result = run_ingest_plugins(
            session,
            filename=filename,
            original_source_path=original_source_path,
            content=content,
            submitted_metadata=metadata,
            entity_type="ingest_jobs",
            entity_id=str(job.id),
        )
        detected_metadata = plugin_result["metadata"]
        derived_identity = plugin_result["derived_identity"]
        resolved_customer_part_number = customer_part_number or derived_identity.get("customer_part_number")
        resolved_customer_revision = customer_revision or derived_identity.get("customer_revision")
        if not resolved_customer_part_number or not resolved_customer_revision or not internal_revision:
            raise ValueError("customer_part_number, customer_revision, and internal_revision are required unless a naming plugin derives customer fields")

        record_metadata = merge_metadata(detected_metadata, {"identity_source": derived_identity or {"mapping_source": "request"}})
        record = find_record_by_identity(
            session,
            customer_part_number=resolved_customer_part_number,
            customer_revision=resolved_customer_revision,
            internal_revision=internal_revision,
        )
        if not record:
            record = create_record(
                session,
                customer_part_number=resolved_customer_part_number,
                customer_revision=resolved_customer_revision,
                internal_revision=internal_revision,
                metadata=record_metadata,
                actor=actor,
            )
        else:
            record.record_metadata = merge_metadata(record.record_metadata, record_metadata)
            ensure_metadata_field_definitions(session, scope="record", metadata=record.record_metadata)

        ensure_metadata_field_definitions(session, scope="file_version", metadata=detected_metadata)
        version = append_version_bytes(
            session,
            record=record,
            filename=filename,
            original_source_path=original_source_path,
            content=content,
            customer_revision=resolved_customer_revision,
            internal_revision=internal_revision,
            metadata=detected_metadata,
            actor=actor,
            mime_type=mime_type or detected_metadata.get("file", {}).get("mime_type_guess"),
        )
        session.flush()
        for dependency_payload in plugin_result["dependencies"]:
            session.add(
                Dependency(
                    source_record_id=record.id,
                    source_file_version_id=version.id,
                    target_record_id=dependency_payload.get("target_record_id"),
                    dependency_type=dependency_payload["dependency_type"],
                    referenced_path=dependency_payload.get("referenced_path"),
                    resolution_status=dependency_payload.get("resolution_status", "unresolved"),
                    confidence=dependency_payload.get("confidence", 100),
                    evidence=dependency_payload.get("evidence", {}),
                )
            )
        job.status = "completed"
        job.record_id = record.id
        job.file_version_id = version.id
        job.detected_metadata = detected_metadata
        job.completed_at = utcnow()
        audit(session, actor=actor, action="ingest.completed", entity_type="ingest_jobs", entity_id=str(job.id), details={"plugin_count": len(detected_metadata.get("plugin_executions", []))})
        return job, record, version
    except Exception as exc:
        job.status = "failed"
        job.error_message = str(exc)
        job.completed_at = utcnow()
        audit(session, actor=actor, action="ingest.failed", entity_type="ingest_jobs", entity_id=str(job.id), details={"error": str(exc)})
        raise
