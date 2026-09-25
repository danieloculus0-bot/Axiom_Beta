import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import Dependency, FileVersion, PluginExecution, ReleasePackage, ReleasePackageItem
from ..plugins import default_registry
from .audit import audit
from .metadata import ensure_lifecycle_states

ALLOWED_TRANSITIONS = {
    "In Work": {"Review", "Obsolete"},
    "Review": {"In Work", "Released", "Obsolete"},
    "Released": {"Obsolete"},
    "Obsolete": set(),
}


def get_state(session: Session, name: str):
    from ..models import LifecycleState

    ensure_lifecycle_states(session)
    state = session.scalar(select(LifecycleState).where(LifecycleState.name == name))
    if state is None:
        raise ValueError(f"unknown lifecycle state: {name}")
    return state


def unresolved_dependencies(session: Session, record_id) -> list[Dependency]:
    return session.scalars(
        select(Dependency).where(Dependency.source_record_id == record_id, Dependency.resolution_status == "unresolved")
    ).all()


def transition_record(session: Session, *, record, to_state_name: str, actor: str, reason: str | None = None) -> ReleasePackage | None:
    from_state = record.lifecycle_state.name if record.lifecycle_state else "In Work"
    if to_state_name not in ALLOWED_TRANSITIONS.get(from_state, set()):
        raise ValueError(f"invalid lifecycle transition from {from_state} to {to_state_name}")
    to_state = get_state(session, to_state_name)
    if to_state.is_release_state:
        blockers = unresolved_dependencies(session, record.id)
        if blockers:
            raise ValueError(f"release blocked by {len(blockers)} unresolved dependencies")
    record.lifecycle_state_id = to_state.id
    audit(
        session,
        actor=actor,
        action="lifecycle.transitioned",
        entity_type="records",
        entity_id=record.internal_record_id,
        details={"from": from_state, "to": to_state_name, "reason": reason},
    )
    if to_state.is_release_state:
        return create_release_package(session, record=record, actor=actor)
    return None


def create_release_package(session: Session, *, record, actor: str, generator_name: str | None = None) -> ReleasePackage:
    versions = session.scalars(
        select(FileVersion)
        .options(selectinload(FileVersion.file_object))
        .where(FileVersion.record_id == record.id)
        .order_by(FileVersion.version_number)
    ).all()
    if not versions:
        raise ValueError("release requires at least one file version")
    dependencies = session.scalars(select(Dependency).where(Dependency.source_record_id == record.id)).all()
    generator = default_registry.release_generator(generator_name)
    generated = generator.build(record=record, versions=versions, dependencies=dependencies)
    release_package = ReleasePackage(
        package_number=f"RPK-{uuid.uuid4().hex[:12].upper()}",
        record_id=record.id,
        internal_revision=record.internal_revision,
        customer_revision=record.customer_revision,
        manifest=generated.manifest,
        created_by=actor,
    )
    session.add(release_package)
    session.flush()
    version_by_id = {str(version.id): version for version in versions}
    for item in generated.items:
        file_version = version_by_id[item["file_version_id"]]
        session.add(ReleasePackageItem(release_package_id=release_package.id, file_version_id=file_version.id, item_role=item.get("item_role", "primary")))
    session.add(
        PluginExecution(
            plugin_name=generated.plugin_name,
            plugin_kind="release_generator",
            entity_type="release_packages",
            entity_id=str(release_package.id),
            input_summary={"record_id": str(record.id), "version_count": len(versions), "dependency_count": len(dependencies)},
            output=generated.manifest,
        )
    )
    audit(session, actor=actor, action="release_package.created", entity_type="release_packages", entity_id=release_package.package_number, details=generated.manifest)
    return release_package
