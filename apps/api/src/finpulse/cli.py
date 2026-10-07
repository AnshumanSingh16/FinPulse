"""Command-line tools: ``finpulse <group> <command>`` (or ``python -m finpulse.cli``).

    finpulse db init [--no-create]       create the database if missing, apply migrations
    finpulse db seed [-s CODE ...]       generate scenarios and load them (idempotent)
    finpulse db reset --yes [--no-seed]  drop every table, re-migrate, re-seed
    finpulse synthetic list              list scenarios
    finpulse synthetic summary CODE      month-by-month roll-up of a scenario
    finpulse synthetic export [CODE] -o DIR   write CSV files + ground_truth.json
    finpulse investigate run [CODE] [--as-of D] [-o FILE] [--events]
                                         run a full investigation on a synthetic scenario
                                         (calls the AI agents: needs ANTHROPIC_API_KEY)
    finpulse investigate run --demo      the same, with the scripted demo agents (no API key;
                                         Sharma Electricals only; see docs/DEMO.md)
    finpulse investigate show FILE [--events]  print a saved investigation
    finpulse demo reset [--api URL]      restore the exact demo state: re-seed every synthetic
                                         entity and clear the running API's investigations

Everything except `investigate run` (without --demo) is deterministic Python and never calls an
LLM.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Callable
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from finpulse.config import Settings, get_settings
from finpulse.core.money import format_inr
from finpulse.observability.logging import configure_logging
from finpulse.persistence.db import create_engine
from finpulse.persistence.seed import seed, table_counts
from finpulse.synthetic import PRIMARY_DEMO, SCENARIOS, generate, get_scenario
from finpulse.synthetic.export import fingerprint, write_csv
from finpulse.synthetic.summary import monthly_summary

API_DIR = Path(__file__).resolve().parents[2]


def _say(message: str = "") -> None:
    sys.stdout.write(message + "\n")


def _alembic_config() -> Config:
    config = Config(str(API_DIR / "alembic.ini"))
    config.attributes["configure_logger"] = False
    return config


def _redacted(settings: Settings) -> str:
    return make_url(settings.database_url).render_as_string(hide_password=True)


# --- db ---------------------------------------------------------------------------------------


async def _create_database_if_missing(settings: Settings) -> bool:
    """Connect to the server's maintenance database and create ours if it doesn't exist.
    Returns True if it was created. Hosted Postgres (e.g. Supabase) already has the database."""
    url = make_url(settings.database_url)
    name = url.database
    if not name:
        raise SystemExit("DATABASE_URL has no database name")
    admin = create_async_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}
            )
            if exists:
                return False
            quoted = name.replace('"', '""')
            await conn.execute(text(f'CREATE DATABASE "{quoted}"'))
            return True
    finally:
        await admin.dispose()


def db_init(args: argparse.Namespace, settings: Settings) -> None:
    _say(f"database: {_redacted(settings)}")
    if not args.no_create:
        try:
            created = asyncio.run(_create_database_if_missing(settings))
            _say("created database" if created else "database exists")
        except Exception as exc:  # e.g. no rights on the maintenance DB; migrations may still work
            _say(f"skipped create-if-missing ({type(exc).__name__}); assuming it exists")
    command.upgrade(_alembic_config(), "head")
    _say("migrations applied (head)")


def db_seed(args: argparse.Namespace, settings: Settings) -> None:
    codes = args.scenario or list(SCENARIOS)
    for code in codes:
        get_scenario(code)  # fail fast on typos

    async def run() -> None:
        engine = create_engine(settings)
        try:
            for r in await seed(engine, codes):
                _say(
                    f"seeded {r.scenario_code:<20} subject={r.subject_id} "
                    f"transactions={r.rows['transactions']:>5} invoices={r.rows['invoices']:>4} "
                    f"bills={r.rows['bills']:>4} fingerprint={r.fingerprint[:12]}"
                )
        finally:
            await engine.dispose()

    asyncio.run(run())


def db_reset(args: argparse.Namespace, settings: Settings) -> None:
    if settings.env == "production":
        raise SystemExit("refusing to reset a production database")
    if not args.yes:
        raise SystemExit(
            f"this drops every FinPulse table in {_redacted(settings)}; re-run with --yes"
        )
    config = _alembic_config()
    command.downgrade(config, "base")
    _say("dropped all tables")
    command.upgrade(config, "head")
    _say("migrations applied (head)")
    if not args.no_seed:
        db_seed(argparse.Namespace(scenario=None), settings)


def db_counts(_: argparse.Namespace, settings: Settings) -> None:
    async def run() -> dict[str, int]:
        engine = create_engine(settings)
        try:
            return await table_counts(engine)
        finally:
            await engine.dispose()

    for table, count in asyncio.run(run()).items():
        _say(f"{table:<26} {count:>7}")


# --- synthetic --------------------------------------------------------------------------------


def synthetic_list(_: argparse.Namespace, __: Settings) -> None:
    for code, spec in SCENARIOS.items():
        marker = "  (primary demo)" if code == PRIMARY_DEMO else ""
        _say(
            f"{code:<20} {spec.archetype:<20} {spec.months:>2} months from {spec.start}  "
            f"{spec.display_name}{marker}"
        )


def synthetic_summary(args: argparse.Namespace, _: Settings) -> None:
    ds = generate(get_scenario(args.code))
    gt = ds.ground_truth
    _say(f"{ds.subject.display_name} — {gt.archetype}, {ds.start_date} to {ds.as_of}")
    _say(f"fingerprint {fingerprint(ds)}")
    if gt.onset_date:
        _say(f"ground truth: deterioration from {gt.onset_date} ({', '.join(gt.mechanisms)})")
    _say()
    cols = (
        "month",
        "sales",
        "inv. receipts",
        "purchases",
        "net cash",
        "closing bal",
        "receivable",
        "payable",
        "debt",
        "bounces",
    )
    _say("  ".join(f"{c:>13}" if i else f"{c:<7}" for i, c in enumerate(cols)))

    def money(minor: int) -> str:
        return f"{format_inr(minor)[:-3]:>13}"  # whole rupees

    for m in monthly_summary(ds):
        _say(
            "  ".join(
                [
                    m.month.strftime("%Y-%m"),
                    money(m.invoiced_minor + m.counter_sales_minor),
                    money(m.collections_minor),
                    money(m.purchases_minor),
                    money(m.net_cash_flow_minor),
                    money(m.closing_balance_minor),
                    money(m.receivables_minor),
                    money(m.payables_minor),
                    money(m.debt_outstanding_minor),
                    f"{m.emi_bounces:>13}",
                ]
            )
        )
    if ds.bureau_events:
        _say("\nsimulated bureau record:")
        for e in ds.bureau_events:
            _say(f"  {e.event_on}  {e.event_type:<15} (reported {e.reported_on})")


def synthetic_export(args: argparse.Namespace, _: Settings) -> None:
    codes = [args.code] if args.code else list(SCENARIOS)
    for code in codes:
        files = write_csv(generate(get_scenario(code)), Path(args.out) / code)
        _say(f"{code}: wrote {len(files)} files to {Path(args.out) / code}")


# --- wiring -----------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="finpulse", description=__doc__.split("\n\n")[0])
    groups = parser.add_subparsers(dest="group", required=True)

    db = groups.add_parser("db", help="database lifecycle").add_subparsers(
        dest="cmd", required=True
    )
    p = db.add_parser("init", help="create the database if missing and apply migrations")
    p.add_argument("--no-create", action="store_true", help="only run migrations")
    p.set_defaults(handler=db_init)
    p = db.add_parser("seed", help="load synthetic scenarios (replaces existing copies)")
    p.add_argument("-s", "--scenario", action="append", choices=sorted(SCENARIOS))
    p.set_defaults(handler=db_seed)
    p = db.add_parser("reset", help="drop all tables, migrate, and seed")
    p.add_argument("--yes", action="store_true", help="confirm dropping all data")
    p.add_argument("--no-seed", action="store_true")
    p.set_defaults(handler=db_reset)
    db.add_parser("counts", help="row count per table").set_defaults(handler=db_counts)

    syn = groups.add_parser("synthetic", help="inspect scenarios without a database")
    syn_cmds = syn.add_subparsers(dest="cmd", required=True)
    syn_cmds.add_parser("list", help="list scenarios").set_defaults(handler=synthetic_list)
    p = syn_cmds.add_parser("summary", help="month-by-month roll-up")
    p.add_argument("code", choices=sorted(SCENARIOS))
    p.set_defaults(handler=synthetic_summary)
    p = syn_cmds.add_parser("export", help="write CSV files")
    p.add_argument("code", nargs="?", choices=sorted(SCENARIOS))
    p.add_argument("-o", "--out", default="synthetic-export")
    p.set_defaults(handler=synthetic_export)

    inv = groups.add_parser("investigate", help="financial investigations (AI agents)")
    inv_cmds = inv.add_subparsers(dest="cmd", required=True)
    p = inv_cmds.add_parser("run", help="investigate a synthetic scenario (needs an API key)")
    p.add_argument("code", nargs="?", default=PRIMARY_DEMO, choices=sorted(SCENARIOS))
    p.add_argument("--as-of", help="YYYY-MM-DD (default: end of the data)")
    p.add_argument("-o", "--out", help="also save the investigation as JSON")
    p.add_argument("--events", action="store_true", help="print the full event log")
    p.add_argument(
        "--demo", action="store_true", help="use the scripted demo agents (no API key needed)"
    )
    p.set_defaults(handler=investigate_run)
    p = inv_cmds.add_parser("show", help="print a saved investigation")
    p.add_argument("file")
    p.add_argument("--events", action="store_true", help="print the full event log")
    p.set_defaults(handler=investigate_show)

    demo = groups.add_parser("demo", help="the deterministic Sharma Electricals demo")
    demo_cmds = demo.add_subparsers(dest="cmd", required=True)
    p = demo_cmds.add_parser("reset", help="re-seed every entity and clear investigations")
    p.add_argument(
        "--api",
        help="running API to clear (default: http://API_HOST:API_PORT from the settings)",
    )
    p.set_defaults(handler=demo_reset)
    return parser


# --- demo ---------------------------------------------------------------------------------------


def demo_reset(args: argparse.Namespace, settings: Settings) -> None:
    """Re-seed the database (works without the API), then ask a running API to forget its
    investigations. The data is regenerated from the scenario specs and seeds, so the result is
    identical every time (the fingerprints printed are pinned by the test suite)."""
    import httpx

    if not settings.demo_allowed:
        raise SystemExit("the demo reset is disabled here (production, or DEMO_ENABLED=false)")
    db_seed(argparse.Namespace(scenario=None), settings)
    api = (args.api or f"http://{settings.api_host}:{settings.api_port}").rstrip("/")
    try:
        response = httpx.post(f"{api}/api/v1/demo/reset", json={"seed": False}, timeout=10)
        response.raise_for_status()
        body = response.json()
        _say(
            f"cleared the API at {api}: {body['investigations_cleared']} investigation(s), "
            f"{body['runs_cleared']} run(s)"
        )
    except httpx.HTTPError as exc:
        _say(f"API at {api} not cleared ({type(exc).__name__}); restart it to clear investigations")
    _say("demo state restored")


# --- investigate --------------------------------------------------------------------------------


def investigate_run(args: argparse.Namespace, settings: Settings) -> None:
    from datetime import date

    from finpulse.agents.llm import AnthropicLLM
    from finpulse.analytics import default_as_of
    from finpulse.core.errors import AppError
    from finpulse.investigation.orchestrator import InvestigationOrchestrator
    from finpulse.investigation.report import render
    from finpulse.synthetic.adapter import to_financial_data

    data = to_financial_data(generate(get_scenario(args.code)))
    as_of = date.fromisoformat(args.as_of) if args.as_of else default_as_of(data)
    if as_of is None:
        _say("The scenario has no data.")
        sys.exit(1)
    from finpulse.agents.llm import LLMClient
    from finpulse.demo import DemoScriptLLM

    llm: LLMClient = DemoScriptLLM(pace_seconds=0) if args.demo else AnthropicLLM(settings)
    try:
        investigation = asyncio.run(InvestigationOrchestrator(llm).investigate(data, as_of))
    except AppError as exc:
        _say(f"Investigation failed: {exc.detail or exc}")
        sys.exit(1)
    if args.out:
        Path(args.out).write_text(investigation.model_dump_json(indent=2), encoding="utf-8")
        _say(f"Saved to {args.out}\n")
    _say(render(investigation, events=args.events))


def investigate_show(args: argparse.Namespace, settings: Settings) -> None:
    from finpulse.investigation.report import render
    from finpulse.investigation.schemas import Investigation

    investigation = Investigation.model_validate_json(Path(args.file).read_text(encoding="utf-8"))
    _say(render(investigation, events=args.events))


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    configure_logging(settings.model_copy(update={"log_format": "console", "log_level": "WARNING"}))
    handler: Callable[[argparse.Namespace, Settings], None] = args.handler
    handler(args, settings)


if __name__ == "__main__":
    main()
