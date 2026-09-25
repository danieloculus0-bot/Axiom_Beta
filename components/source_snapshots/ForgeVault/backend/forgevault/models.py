import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


JsonType = JSON().with_variant(JSONB, "postgresql")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(320), unique=True, nullable=True)
    display_name: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    roles: Mapped[list["UserRole"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    user: Mapped[User] = relationship(back_populates="roles")
    role: Mapped[Role] = relationship()


class LifecycleState(Base):
    __tablename__ = "lifecycle_states"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    is_release_state: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_terminal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Record(Base):
    __tablename__ = "records"
    __table_args__ = (
        Index("ix_records_customer_lookup", "customer_part_number", "customer_revision", "internal_revision"),
        Index("ix_records_metadata", "record_metadata", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    internal_record_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    customer_part_number: Mapped[str] = mapped_column(String(255), index=True)
    customer_revision: Mapped[str] = mapped_column(String(64), index=True)
    internal_revision: Mapped[str] = mapped_column(String(64), index=True)
    lifecycle_state_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("lifecycle_states.id"), nullable=True, index=True)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    record_metadata: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    lifecycle_state: Mapped[LifecycleState | None] = relationship()
    customer_mappings: Mapped[list["CustomerIdentityMapping"]] = relationship(back_populates="record", cascade="all, delete-orphan")
    versions: Mapped[list["FileVersion"]] = relationship(back_populates="record")


class CustomerIdentityMapping(Base):
    __tablename__ = "customer_identity_mappings"
    __table_args__ = (
        UniqueConstraint("record_id", "customer_part_number", "customer_revision", "internal_revision", name="uq_customer_identity_mapping"),
        Index("ix_customer_identity_lookup", "customer_part_number", "customer_revision"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("records.id", ondelete="CASCADE"), index=True)
    customer_part_number: Mapped[str] = mapped_column(String(255))
    customer_revision: Mapped[str] = mapped_column(String(64))
    internal_revision: Mapped[str] = mapped_column(String(64))
    mapping_source: Mapped[str] = mapped_column(String(64), default="ingestion", nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    record: Mapped[Record] = relationship(back_populates="customer_mappings")


class MetadataFieldDefinition(Base):
    __tablename__ = "metadata_field_definitions"
    __table_args__ = (UniqueConstraint("scope", "field_key", name="uq_metadata_field_scope_key"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    field_key: Mapped[str] = mapped_column(String(255), nullable=False)
    value_type: Mapped[str] = mapped_column(String(32), default="string", nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_searchable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class FileObject(Base):
    __tablename__ = "file_objects"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    storage_adapter: Mapped[str] = mapped_column(String(64), default="local", nullable=False)
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class FileVersion(Base):
    __tablename__ = "file_versions"
    __table_args__ = (
        UniqueConstraint("record_id", "version_number", name="uq_file_versions_record_version"),
        Index("ix_file_versions_source_path", "original_source_path"),
        Index("ix_file_versions_metadata", "version_metadata", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("records.id", ondelete="CASCADE"), index=True)
    file_object_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("file_objects.id"), index=True)
    previous_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("file_versions.id"), nullable=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    filename: Mapped[str] = mapped_column(String(512), index=True)
    original_source_path: Mapped[str] = mapped_column(Text, nullable=False)
    customer_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    internal_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    version_metadata: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    record: Mapped[Record] = relationship(back_populates="versions")
    file_object: Mapped[FileObject] = relationship()


class Checkout(Base):
    __tablename__ = "checkouts"
    __table_args__ = (Index("ix_checkouts_record_active", "record_id", "released_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("records.id", ondelete="CASCADE"), index=True)
    checked_out_by: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReleasePackage(Base):
    __tablename__ = "release_packages"
    __table_args__ = (UniqueConstraint("record_id", "internal_revision", "customer_revision", name="uq_release_package_revision"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    package_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("records.id", ondelete="RESTRICT"), index=True)
    internal_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    customer_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest: Mapped[dict] = mapped_column(JsonType, nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    items: Mapped[list["ReleasePackageItem"]] = relationship(back_populates="release_package", cascade="all, delete-orphan")


class ReleasePackageItem(Base):
    __tablename__ = "release_package_items"
    __table_args__ = (UniqueConstraint("release_package_id", "file_version_id", name="uq_release_package_item_version"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    release_package_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("release_packages.id", ondelete="CASCADE"), index=True)
    file_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("file_versions.id", ondelete="RESTRICT"), index=True)
    item_role: Mapped[str] = mapped_column(String(64), default="primary", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    release_package: Mapped[ReleasePackage] = relationship(back_populates="items")
    file_version: Mapped[FileVersion] = relationship()


class Dependency(Base):
    __tablename__ = "dependencies"
    __table_args__ = (
        Index("ix_dependencies_source", "source_record_id"),
        Index("ix_dependencies_target", "target_record_id"),
        Index("ix_dependencies_status", "resolution_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("records.id", ondelete="CASCADE"), index=True)
    target_record_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("records.id", ondelete="SET NULL"), nullable=True, index=True)
    source_file_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("file_versions.id", ondelete="CASCADE"), nullable=True)
    dependency_type: Mapped[str] = mapped_column(String(64), nullable=False)
    referenced_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_status: Mapped[str] = mapped_column(String(32), default="unresolved", nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    evidence: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class PluginExecution(Base):
    __tablename__ = "plugin_executions"
    __table_args__ = (
        Index("ix_plugin_executions_name", "plugin_name"),
        Index("ix_plugin_executions_entity", "entity_type", "entity_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plugin_name: Mapped[str] = mapped_column(String(128), nullable=False)
    plugin_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="completed", nullable=False)
    input_summary: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    output: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class IntegrationEvent(Base):
    __tablename__ = "integration_events"
    __table_args__ = (
        Index("ix_integration_events_system_status", "external_system", "status"),
        Index("ix_integration_events_entity", "entity_type", "entity_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_system: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    payload: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    response: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_entity", "entity_type", "entity_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    details: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class IngestJob(Base):
    __tablename__ = "ingest_jobs"
    __table_args__ = (Index("ix_ingest_jobs_status", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    staging_uri: Mapped[str] = mapped_column(Text, nullable=False)
    original_source_path: Mapped[str] = mapped_column(Text, nullable=False)
    detected_metadata: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    record_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("records.id", ondelete="SET NULL"), nullable=True, index=True)
    file_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("file_versions.id", ondelete="SET NULL"), nullable=True, index=True)
    submitted_by: Mapped[str] = mapped_column(String(128), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
