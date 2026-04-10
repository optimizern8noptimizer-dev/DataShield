"""CLI for DataShield BY 2.0."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click


def setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")


def run_masking_job(config: str, mode: str | None = None, tables: list[str] | tuple[str, ...] = (), verbose: bool = False):
    setup_logging(verbose)
    from .config import load_config, parse_config
    from .cache import create_cache
    from .audit import AuditLog
    from .etl import ETLPipeline

    raw = load_config(config)
    if mode:
        raw.setdefault("session", {})["mode"] = mode
    cfg = parse_config(raw)
    if tables:
        names = {t.lower() for t in tables}
        cfg.tables = [t for t in cfg.tables if t.name.lower() in names]
    cache = create_cache(cfg.cache_config)
    strict_key = raw.get("audit", {}).get("strict_key", False)
    audit = AuditLog(raw.get("audit", {}).get("log_path", "datashield_audit.jsonl"), strict_key=strict_key)
    pipeline = ETLPipeline(cfg, cache, audit)
    stats = pipeline.run(progress_callback=None)
    total_rows = sum(s.rows_processed for s in stats)
    return {
        "tables": [s.to_dict() for s in stats],
        "total_rows": total_rows,
        "mode": cfg.mode,
        "config": str(config),
    }


@click.group()
@click.version_option("2.0.0", prog_name="DataShield BY")
def main():
    """DataShield BY 2.0 - banking dataset anonymization."""


@main.command("mask")
@click.option("--service", "service", "-s", required=True)
@click.option("--value", "value", "-v", required=True)
@click.option("--mode", "mode", "-m", default="deterministic", type=click.Choice(["deterministic", "randomized"]))
@click.option("--params", "params", "-p", default="{}")
def mask_cmd(service, value, mode, params):
    from .maskers import get_masker
    extra = json.loads(params)
    masker = get_masker(service, mode=mode)
    result = masker.mask(value, **extra)
    if isinstance(result, dict):
        click.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        click.echo(str(result))


@main.command("services")
def services_cmd():
    from .maskers import list_services
    for s in list_services():
        click.echo(s)


@main.command("run")
@click.option("--config", "config", "-c", required=True, type=click.Path(exists=True))
@click.option("--mode", "mode", "-m", type=click.Choice(["copy", "in_place", "dry_run"]))
@click.option("--table", "tables", "-t", multiple=True)
@click.option("--verbose", "verbose", "-v", is_flag=True)
def run_cmd(config, mode, tables, verbose):
    try:
        result = run_masking_job(config=config, mode=mode, tables=list(tables), verbose=verbose)
        click.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    except Exception as e:
        click.echo(f"ERROR: {e}", err=True)
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@main.command("discover")
@click.option("--db", required=True)
@click.option("--schema", default=None)
@click.option("--output", "output", "-o", default=None)
def discover_cmd(db, schema, output):
    from sqlalchemy import create_engine, inspect
    import yaml

    engine = create_engine(db)
    inspector = inspect(engine)
    tables = inspector.get_table_names(schema=schema)
    patterns = {
        "fio": ["фио", "fullname", "full_name", "name"],
        "birthdate": ["birth", "birth_date", "dob"],
        "phone": ["phone", "mobile", "тел"],
        "email": ["email", "почта"],
        "bankCard": ["card", "card_number"],
        "bankAccount": ["account", "account_number", "iban", "счет"],
        "passport": ["passport", "document", "id_doc"],
        "cdiAddress": ["address", "addr", "адрес"],
    }
    discovered = {}
    for tname in tables:
        cols = inspector.get_columns(tname, schema=schema)
        mapped = []
        for c in cols:
            cname = c["name"].lower()
            for svc, kws in patterns.items():
                if any(k in cname for k in kws):
                    mapped.append({"name": c["name"], "service": svc})
                    break
        if mapped:
            discovered[tname] = mapped
    click.echo(json.dumps(discovered, ensure_ascii=False, indent=2))
    if output:
        cfg = {"version": "2.0", "session": {"mode": "copy"}, "source": {"url": db}, "tables": [{"name": t, "columns": cols} for t, cols in discovered.items()]}
        Path(output).write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")


@main.command("audit")
@click.option("--log", default="datashield_audit.jsonl")
@click.option("--verify", is_flag=True)
def audit_cmd(log, verify):
    from .audit import AuditLog
    al = AuditLog(log)
    if verify:
        violations = al.verify()
        click.echo(json.dumps(violations, ensure_ascii=False, indent=2))
    else:
        click.echo(json.dumps(al.read_sessions(), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
