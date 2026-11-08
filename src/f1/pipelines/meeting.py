"""Pipeline de meeting: datasets de sessão de um fim de semana de GP."""

import logging
from collections.abc import Sequence

from f1.domain.endpoints import SESSION_ENDPOINTS, Endpoint
from f1.domain.models import Filter, MeetingRef, Partition, Record, SessionRef
from f1.domain.ports import OpenF1Source
from f1.pipelines.common import LakeStores, RunContext, load_dataset
from f1.utils.metrics import PipelineMetrics

logger = logging.getLogger(__name__)


class MeetingNotFoundError(LookupError):
    """O ``meeting_key`` informado não existe na OpenF1."""


def fetch_meeting(source: OpenF1Source, meeting_key: int) -> MeetingRef:
    records = source.fetch(Endpoint.MEETINGS, [Filter("meeting_key", meeting_key)])
    if not records:
        raise MeetingNotFoundError(f"meeting_key {meeting_key} not found")
    return MeetingRef.from_record(records[0])


def fetch_sessions(source: OpenF1Source, meeting_key: int) -> list[SessionRef]:
    records = source.fetch(Endpoint.SESSIONS, [Filter("meeting_key", meeting_key)])
    sessions = [SessionRef.from_record(r) for r in records]
    return [s for s in sessions if not s.is_cancelled]


def run_meeting(
    source: OpenF1Source,
    stores: LakeStores,
    ctx: RunContext,
    meeting: MeetingRef,
    endpoints: Sequence[Endpoint] = SESSION_ENDPOINTS,
) -> list[PipelineMetrics]:
    """Carrega os datasets de sessão de um meeting (overwrite por partição).

    Bronze recebe um arquivo por sessão; silver, um arquivo por meeting.
    """
    invalid = [e for e in endpoints if e not in SESSION_ENDPOINTS]
    if invalid:
        raise ValueError(f"not session-level datasets: {invalid}")
    sessions = fetch_sessions(source, meeting.meeting_key)
    partition = Partition(season=meeting.year, meeting_key=meeting.meeting_key)
    logger.info(
        "meeting_started",
        extra={
            "run_id": ctx.run_id,
            "meeting_key": meeting.meeting_key,
            "sessions": [s.session_key for s in sessions],
        },
    )
    return [
        load_dataset(
            endpoint,
            _fetch_sessions_data(source, stores, endpoint, sessions, partition),
            partition,
            stores,
            ctx,
        )
        for endpoint in endpoints
    ]


def _fetch_sessions_data(
    source: OpenF1Source,
    stores: LakeStores,
    endpoint: Endpoint,
    sessions: Sequence[SessionRef],
    partition: Partition,
) -> list[Record]:
    records: list[Record] = []
    for session in sessions:
        batch = source.fetch(endpoint, [Filter("session_key", session.session_key)])
        stores.raw.write(
            endpoint, partition, f"session_key={session.session_key}", batch
        )
        records.extend(batch)
    return records
