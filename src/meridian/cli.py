"""`meridian` command line. Run `uv run meridian --help`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import structlog
import typer
from sqlalchemy import create_engine, func, select, text

from meridian.aws import ensure_bucket, s3_client, upload_directory
from meridian.config import get_settings
from meridian.ingest import pipeline, sources, store
from meridian.logging import setup_logging

app = typer.Typer(help="Meridian Retail platform tools.", no_args_is_help=True)

LogFormat = Annotated[
    str, typer.Option("--log-format", help="Log format: json or text", envvar="MERIDIAN_LOG_FORMAT")
]
LogLevel = Annotated[
    str, typer.Option("--log-level", help="Log level", envvar="MERIDIAN_LOG_LEVEL")
]


@app.callback()
def _main(log_format: LogFormat = "json", log_level: LogLevel = "INFO") -> None:
    setup_logging(json=log_format == "json", level=log_level)


@app.command("init-db")
def init_db() -> None:
    """Create the landing tables (safe to run repeatedly)."""
    store.create_tables(create_engine(get_settings().db_url))
    typer.echo("landing tables ready")


@app.command()
def upload(
    folder: Annotated[Path, typer.Option(help="Folder of CSVs")] = Path("data/landing"),
    prefix: Annotated[str, typer.Option(help="S3 prefix, e.g. the delivery date")] = "2026-09-18",
) -> None:
    """Upload a delivery to the landing bucket in Floci (local S3)."""
    s = get_settings()
    client = s3_client(s)
    ensure_bucket(client, s.landing_bucket)
    for key in upload_directory(client, s.landing_bucket, prefix, folder):
        typer.echo(f"s3://{s.landing_bucket}/{key}")


@app.command()
def ingest(
    source: Annotated[
        str, typer.Option(help="Local folder or s3://bucket/prefix")
    ] = "data/landing",
) -> None:
    """Validate a delivery and publish / review / reject every row."""
    log = structlog.get_logger()
    s = get_settings()
    log.info("ingest.start", source=source)

    if source.startswith("s3://"):
        bucket, _, prefix = source.removeprefix("s3://").partition("/")
        batch = sources.from_s3(s3_client(s), bucket, prefix)
    else:
        batch = sources.from_directory(Path(source))

    result = pipeline.evaluate(batch, s.run_at, s.freshness_hours)
    engine = create_engine(s.db_url)
    store.create_tables(engine)
    run_id, result = store.persist(engine, batch, result, s.run_at)

    structlog.contextvars.bind_contextvars(run_id=run_id)
    log.info("ingest.done", status=result.status.value, **result.summary())
    structlog.contextvars.unbind_contextvars("run_id")

    typer.echo(json.dumps({"run_id": run_id, **result.summary()}, indent=2))
    if result.status.value == "PAUSED":
        raise typer.Exit(code=2)


@app.command()
def generate(
    num_orders: Annotated[int, typer.Option(help="Number of orders to generate")] = 100,
    error_rate: Annotated[float, typer.Option(help="Fraction of rows with injected errors")] = 0.08,
    seed: Annotated[int, typer.Option(help="Random seed for reproducibility")] = 42,
    output: Annotated[Path, typer.Option(help="Output directory")] = Path("data/generated"),
) -> None:
    """Generate synthetic CSV deliveries for testing."""
    from meridian.generate import generate_delivery, write_csvs

    s = get_settings()
    data = generate_delivery(num_orders, error_rate, seed, s.run_at, s.freshness_hours)
    paths = write_csvs(data, output)
    total = sum(len(rows) for rows in data.values())
    for p in paths:
        typer.echo(p)
    typer.echo(f"{total} rows across {len(paths)} files")


@app.command()
def runs(limit: int = 10) -> None:
    """Show the most recent ingestion runs."""
    engine = create_engine(get_settings().db_url)
    q = select(store.ingest_runs).order_by(store.ingest_runs.c.finished_at.desc()).limit(limit)
    with engine.connect() as conn:
        for row in conn.execute(q):
            typer.echo(f"{row.finished_at}  {row.status:<10} {row.run_id}  {row.source}")


@app.command("trusted-check")
def trusted_check() -> None:
    """Confirm the trusted course database was seeded (expects 20,000 orders)."""
    engine = create_engine(get_settings().trusted_db_url)
    with engine.connect() as conn:
        for table in ("orders", "support_cases", "issue_records", "human_reviews"):
            n = conn.execute(select(func.count()).select_from(text(table))).scalar_one()
            typer.echo(f"{table:<16} {n:>7,}")


if __name__ == "__main__":
    app()
