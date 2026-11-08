"""CLI: ``python -m f1 {calendar,meeting,season} ...``.

A composição das dependências concretas acontece somente aqui.
"""

import argparse
import logging
from collections.abc import Sequence

from f1.config.settings import Settings, get_settings
from f1.domain.endpoints import SESSION_ENDPOINTS, Endpoint, parse_endpoints
from f1.ingestion.openf1_client import OpenF1Client
from f1.pipelines.calendar import run_calendar
from f1.pipelines.common import LakeStores, RunContext
from f1.pipelines.meeting import fetch_meeting, run_meeting
from f1.pipelines.season import run_season
from f1.storage.bronze import JsonRawStore
from f1.storage.parquet_writer import ParquetDatasetStore
from f1.storage.paths import BRONZE, QUARANTINE, SILVER, layer_path
from f1.storage.quarantine import QuarantineStore
from f1.utils.logging import configure_logging
from f1.utils.metrics import new_run_id

logger = logging.getLogger("f1.cli")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="f1", description="Ingestão OpenF1 → data lake local"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    calendar = commands.add_parser("calendar", help="meetings e sessions de um ano")
    calendar.add_argument("--year", type=int, required=True)

    meeting = commands.add_parser("meeting", help="datasets de sessão de um meeting")
    meeting.add_argument("--meeting-key", type=int, required=True)
    _add_datasets_argument(meeting)

    season = commands.add_parser("season", help="calendário + meetings encerrados")
    season.add_argument("--year", type=int, required=True)
    _add_datasets_argument(season)
    return parser


def _add_datasets_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--datasets",
        type=_datasets,
        default=SESSION_ENDPOINTS,
        help="lista separada por vírgula (ex.: laps,stints); padrão: todos",
    )


def _datasets(value: str) -> tuple[Endpoint, ...]:
    try:
        return parse_endpoints(v for v in value.split(",") if v.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def build_stores(settings: Settings) -> LakeStores:
    return LakeStores(
        raw=JsonRawStore(layer_path(settings.data_dir, BRONZE)),
        silver=ParquetDatasetStore(layer_path(settings.data_dir, SILVER)),
        quarantine=QuarantineStore(layer_path(settings.data_dir, QUARANTINE)),
    )


def main(argv: Sequence[str] | None = None, settings: Settings | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    ctx = RunContext(
        run_id=new_run_id(), max_rejection_rate=settings.max_rejection_rate
    )
    stores = build_stores(settings)
    logger.info("run_started", extra={"run_id": ctx.run_id, "command": args.command})
    with OpenF1Client.from_settings(settings) as source:
        if args.command == "calendar":
            run_calendar(source, stores, ctx, args.year)
        elif args.command == "meeting":
            meeting = fetch_meeting(source, args.meeting_key)
            run_meeting(source, stores, ctx, meeting, args.datasets)
        else:
            run_season(source, stores, ctx, args.year, endpoints=args.datasets)
    logger.info("run_finished", extra={"run_id": ctx.run_id, "command": args.command})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
