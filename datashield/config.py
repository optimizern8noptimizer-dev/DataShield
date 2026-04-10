"""Configuration loader and validator for DataShield BY 2.0."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from .etl.pipeline import PipelineConfig, TableRule, ColumnRule

_SAFE_WHERE_RE = re.compile(
    r"^[A-Za-z0-9_\s\.=><!'\-\(\)]+$"
)
_FORBIDDEN_SQL_TOKENS = [";", "--", "/*", "*/", " union ", " drop ", " delete ", " insert ", " update ", " alter ", " grant ", " revoke "]


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError("Config must be a YAML mapping")
    return data


def _validate_where_clause(where_clause: str | None) -> str | None:
    if not where_clause:
        return where_clause
    value = where_clause.strip()
    if not _SAFE_WHERE_RE.match(value):
        raise ValueError(f"Unsafe where_clause: unsupported characters: {where_clause}")
    lv = f" {value.lower()} "
    if any(token in lv for token in _FORBIDDEN_SQL_TOKENS):
        raise ValueError(f"Unsafe where_clause: forbidden SQL token in: {where_clause}")
    return value


def parse_config(raw: dict) -> PipelineConfig:
    source = raw.get("source", {})
    target = raw.get("target", source)
    session = raw.get("session", {})

    if not raw.get("tables"):
        raise ValueError("Config must contain at least one table rule")

    tables: list[TableRule] = []
    for t in raw.get("tables", []):
        cols = []
        for c in t.get("columns", []):
            cols.append(ColumnRule(
                name=c["name"],
                service=c["service"],
                mode=c.get("mode", session.get("mask_mode", "deterministic")),
                params=c.get("params", {}),
                linked_columns=c.get("linked_columns", []),
                fk_reference=c.get("references"),
            ))
        tables.append(TableRule(
            name=t["name"],
            columns=cols,
            pk_column=t.get("pk_column"),
            fk_columns=t.get("fk_columns", []),
            batch_size=int(t.get("batch_size", session.get("batch_size", 1000))),
            where_clause=_validate_where_clause(t.get("where_clause")),
        ))

    cache_cfg = raw.get("cache") or raw.get("cache_config") or {}

    return PipelineConfig(
        source_url=_build_url(source),
        target_url=_build_url(target) if target != source else None,
        tables=tables,
        mode=session.get("mode", "copy"),
        parallelism=int(session.get("parallelism", 1)),
        snapshot_before=bool(session.get("snapshot_before", True)),
        degraded_mode=session.get("degraded_mode", "char_mask"),
        source_schema=source.get("schema"),
        target_schema=target.get("schema"),
        cache_config=cache_cfg,
    )


def _build_url(db_cfg: dict) -> str:
    if "url" in db_cfg:
        return db_cfg["url"]
    db_type = db_cfg.get("type", "postgresql")
    host = db_cfg.get("host", "localhost")
    port = db_cfg.get("port")
    user = db_cfg.get("user", "")
    password = db_cfg.get("password", "")
    database = db_cfg.get("database", "")

    if db_type in ("postgresql", "postgres"):
        port = port or 5432
        return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{database}"
    if db_type in ("mariadb", "mysql"):
        port = port or 3306
        return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
    if db_type == "oracle":
        port = port or 1521
        sid = db_cfg.get("sid", database)
        return f"oracle+oracledb://{user}:{password}@{host}:{port}/{sid}"
    if db_type == "sqlite":
        return f"sqlite:///{database}"
    raise ValueError(f"Unknown DB type: {db_type}")
