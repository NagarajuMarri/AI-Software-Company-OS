from runtime.composition import create_runtime_container
from runtime.persistence import FilePersistenceProvider
from runtime.outbox.models import OutboxStatus
from tests.test_outbox_atomicity import values


def test_runtime_checkpoint_restores_outbox_without_duplicate_event(tmp_path):
    provider = FilePersistenceProvider(tmp_path)
    first = create_runtime_container(
        persistence_enabled=True, persistence_provider=provider,
        runtime_id="outbox-runtime",
    )
    first.outbox_service.create_operation(**values())
    checkpoint = first.persistence_service.save_checkpoint("outbox")
    event_count = len(first.event_store.list_events())
    second = create_runtime_container(
        persistence_enabled=True, persistence_provider=provider,
        runtime_id="outbox-runtime",
    )
    second.persistence_service.restore_runtime(checkpoint)
    assert second.outbox_repository.get_operation(
        "op"
    ).status == OutboxStatus.PENDING
    assert len(second.event_store.list_events()) == event_count
