"""
ETL Pipeline — основной движок маскирования.
Читает из источника, маскирует, пишет в приёмник.
FK-Safe: топосортировка + маппинг PK.
"""
from __future__ import annotations
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Iterator

try:
    from sqlalchemy import create_engine, text, MetaData, Table, inspect
    from sqlalchemy.engine import Engine
except ImportError:
    create_engine = text = MetaData = Table = inspect = Engine = None

from .fk_graph import FKGraph, discover_fk_graph
from ..maskers import get_masker
from ..cache import BaseCache
from ..audit import AuditLog

logger = logging.getLogger("datashield.pipeline")


@dataclass
class ColumnRule:
    name: str
    service: str
    mode: str = "deterministic"
    params: dict = field(default_factory=dict)
    linked_columns: list[str] = field(default_factory=list)
    fk_reference: str | None = None  # "table.column"


@dataclass
class TableRule:
    name: str
    columns: list[ColumnRule] = field(default_factory=list)
    pk_column: str | None = None
    fk_columns: list[dict] = field(default_factory=list)  # {name, references}
    batch_size: int = 1000
    where_clause: str | None = None


@dataclass
class PipelineConfig:
    source_url: str
    target_url: str | None
    tables: list[TableRule]
    mode: str = "copy"             # copy | in_place | dry_run | dump
    parallelism: int = 1
    snapshot_before: bool = True
    degraded_mode: str = "char_mask"
    source_schema: str | None = None
    target_schema: str | None = None
    cache_config: dict = field(default_factory=dict)


@dataclass
class MaskingStats:
    table: str
    rows_processed: int = 0
    rows_masked: int = 0
    errors: int = 0
    duration_sec: float = 0.0
    started_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "table": self.table,
            "rows_processed": self.rows_processed,
            "rows_masked": self.rows_masked,
            "errors": self.errors,
            "duration_sec": round(self.duration_sec, 2),
            "rows_per_sec": round(self.rows_processed / self.duration_sec, 0) if self.duration_sec > 0 else 0,
            "started_at": self.started_at.isoformat(),
        }


class MaskingSession:
    """Сессия маскирования: хранит маппинг PK→masked_PK между таблицами."""

    def __init__(self, session_id: str, cache: BaseCache):
        self._id = session_id
        self._cache = cache
        self._pk_mappings: dict[str, dict] = {}  # table -> {old_pk: new_pk}

    def register_pk_mapping(self, table: str, old_pk: Any, new_pk: Any):
        if table not in self._pk_mappings:
            self._pk_mappings[table] = {}
        self._pk_mappings[table][str(old_pk)] = new_pk

    def get_mapped_pk(self, table: str, old_pk: Any) -> Any | None:
        return self._pk_mappings.get(table, {}).get(str(old_pk))

    def get_fk_value(self, ref_table: str, old_fk_value: Any) -> Any:
        """Получить замаскированное значение FK из маппинга родительской таблицы."""
        mapped = self.get_mapped_pk(ref_table, old_fk_value)
        return mapped if mapped is not None else old_fk_value


class ETLPipeline:
    """FK-Safe ETL Pipeline."""

    def __init__(self, config: PipelineConfig, cache: BaseCache, audit: AuditLog | None = None):
        self.config = config
        self.cache = cache
        self.audit = audit
        self._source_engine: Engine | None = None
        self._target_engine: Engine | None = None
        self._session: MaskingSession | None = None
        self._fk_graph: FKGraph | None = None
        self._maskers: dict[str, Any] = {}

    def _get_masker(self, service: str, mode: str = "deterministic"):
        key = f"{service}:{mode}"
        if key not in self._maskers:
            self._maskers[key] = get_masker(service, cache=self.cache, mode=mode)
        return self._maskers[key]

    def _connect(self):
        self._source_engine = create_engine(self.config.source_url, echo=False)
        if self.config.target_url:
            self._target_engine = create_engine(self.config.target_url, echo=False)
        else:
            self._target_engine = self._source_engine

    def _get_table_rules_map(self) -> dict[str, TableRule]:
        return {t.name.lower(): t for t in self.config.tables}

    def _build_fk_graph(self) -> FKGraph:
        """Построить FK-граф: сначала из конфига, затем автодобавить из INFORMATION_SCHEMA."""
        graph = FKGraph()
        rules = self._get_table_rules_map()
        for tname, rule in rules.items():
            graph.add_table(tname)

        # Добавить FK из конфига
        for rule in self.config.tables:
            for fk_col in rule.fk_columns:
                ref = fk_col.get("references", "")
                if "." in ref:
                    ref_table, ref_col = ref.rsplit(".", 1)
                    graph.add_fk(rule.name.lower(), fk_col["name"], ref_table.lower(), ref_col)

        # Автообнаружение FK из БД
        try:
            with self._source_engine.connect() as conn:
                db_graph = discover_fk_graph(conn, self.config.source_schema)
                for tname, node in db_graph.nodes.items():
                    if tname not in graph.nodes:
                        graph.add_table(tname)
                    for rel in node.fk_relations:
                        graph.add_fk(rel.from_table, rel.from_column, rel.to_table, rel.to_column)
        except Exception as e:
            logger.warning(f"Автообнаружение FK не удалось: {e}")

        return graph

    def _fetch_rows(self, conn, table: str, rule: TableRule, batch_size: int) -> Iterator[tuple[int, list[dict]]]:
        """Read table rows in batches and yield (total_rows, rows)."""
        where = f" WHERE {rule.where_clause}" if rule.where_clause else ""
        try:
            count_result = conn.execute(text(f"SELECT COUNT(*) FROM {table}{where}"))
            total = count_result.scalar() or 0
        except Exception:
            total = 0

        offset = 0
        while True:
            try:
                dialect = conn.dialect.name
                if dialect in ("postgresql",):
                    sql = f"SELECT * FROM {table}{where} LIMIT {batch_size} OFFSET {offset}"
                elif dialect in ("mysql", "mariadb"):
                    sql = f"SELECT * FROM {table}{where} LIMIT {batch_size} OFFSET {offset}"
                elif dialect == "oracle":
                    sql = f"SELECT * FROM (SELECT a.*, ROWNUM rn FROM {table} a{where} WHERE ROWNUM <= {offset + batch_size}) WHERE rn > {offset}"
                else:
                    sql = f"SELECT * FROM {table}{where} LIMIT {batch_size} OFFSET {offset}"

                result = conn.execute(text(sql))
                rows = [dict(row._mapping) for row in result]
                if not rows:
                    break
                yield total, rows
                offset += len(rows)
                if len(rows) < batch_size:
                    break
            except Exception as e:
                logger.error(f"Ошибка чтения {table} offset={offset}: {e}")
                break

    def _mask_row(self, row: dict, rule: TableRule, session: MaskingSession) -> dict:
        """Замаскировать строку согласно правилам."""
        masked = dict(row)

        # Сначала применить FK-маппинг
        for fk_col in rule.fk_columns:
            col_name = fk_col["name"].lower()
            ref = fk_col.get("references", "")
            if "." in ref and col_name in masked:
                ref_table = ref.rsplit(".", 1)[0].lower()
                old_val = masked[col_name]
                if old_val is not None:
                    mapped = session.get_fk_value(ref_table, old_val)
                    masked[col_name] = mapped

        # Применить правила маскирования
        for col_rule in rule.columns:
            col_name = col_rule.name.lower()
            if col_name not in {k.lower() for k in masked.keys()}:
                continue
            # Найти реальный ключ (с учётом регистра)
            real_key = next((k for k in masked.keys() if k.lower() == col_name), col_name)
            original_val = masked[real_key]
            if original_val is None:
                continue
            try:
                masker = self._get_masker(col_rule.service, col_rule.mode)
                params = dict(col_rule.params or {})
                if params.get("contact_type_from_column"):
                    source_col = params.pop("contact_type_from_column")
                    source_key = next((k for k in row.keys() if k.lower() == str(source_col).lower()), None)
                    if source_key:
                        params["contact_type"] = row.get(source_key)
                if params.get("source_columns"):
                    source_columns = params.pop("source_columns") or {}
                    for target_name, source_col in source_columns.items():
                        source_key = next((k for k in row.keys() if k.lower() == str(source_col).lower()), None)
                        if source_key:
                            params[target_name] = row.get(source_key)
                params.setdefault("row", row)
                masked_val = masker.mask(original_val, **params)
                # Для словарных результатов (fio, passport и т.д.)
                if isinstance(masked_val, dict):
                    # Проверить связанные колонки
                    handled = set()
                    for linked in col_rule.linked_columns:
                        linked_key = next((k for k in masked.keys() if k.lower() == linked.lower()), None)
                        if linked_key and linked in masked_val:
                            masked[linked_key] = masked_val[linked]
                            handled.add(linked.lower())
                    for mk, mv in masked_val.items():
                        mk_key = next((k for k in masked.keys() if k.lower() == mk.lower()), None)
                        if mk_key and mk.lower() not in handled and mk.lower() != real_key.lower():
                            masked[mk_key] = mv
                    # Основная колонка: вернуть full или первое строковое значение
                    if "full" in masked_val:
                        masked[real_key] = masked_val["full"]
                    elif col_rule.service == "bankCard" and "number" in masked_val:
                        masked[real_key] = masked_val["number"]
                    else:
                        primary = next((v for v in masked_val.values() if isinstance(v, str)), None)
                        if primary:
                            masked[real_key] = primary
                else:
                    masked[real_key] = masked_val
            except Exception as e:
                logger.debug(f"Ошибка маскирования {real_key} ({col_rule.service}): {e}")

        # Зарегистрировать маппинг PK
        if rule.pk_column:
            old_pk = row.get(rule.pk_column)
            new_pk = masked.get(rule.pk_column)
            if old_pk is not None:
                session.register_pk_mapping(rule.name.lower(), old_pk, new_pk or old_pk)

        return masked

    def _write_rows_copy(self, conn, table: str, rows: list[dict]):
        """INSERT в целевую таблицу."""
        if not rows:
            return
        keys = list(rows[0].keys())
        placeholders = ", ".join(f":{k}" for k in keys)
        cols = ", ".join(keys)
        sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
        try:
            conn.execute(text(sql), rows)
        except Exception as e:
            logger.error(f"Ошибка записи в {table}: {e}")
            # Попытка построчно для изоляции ошибок
            for row in rows:
                try:
                    conn.execute(text(sql), [row])
                except Exception as re:
                    logger.error(f"  Строка пропущена: {re}")

    def _write_rows_inplace(self, conn, table: str, original_rows: list[dict], masked_rows: list[dict], rule: TableRule):
        """UPDATE в той же таблице."""
        if not original_rows or not rule.pk_column:
            logger.warning(f"In-place для {table}: нет pk_column, пропущено")
            return
        pk = rule.pk_column
        mask_cols = {c.name.lower() for c in rule.columns}
        for orig, masked in zip(original_rows, masked_rows):
            pk_val = orig.get(pk)
            if pk_val is None:
                continue
            updates = {k: v for k, v in masked.items() if k.lower() in mask_cols}
            if not updates:
                continue
            set_clause = ", ".join(f"{k} = :{k}" for k in updates.keys())
            params = dict(updates)
            params["__pk__"] = pk_val
            try:
                conn.execute(text(f"UPDATE {table} SET {set_clause} WHERE {pk} = :__pk__"), [params])
            except Exception as e:
                logger.error(f"UPDATE {table} pk={pk_val}: {e}")

    def run(self, progress_callback: Callable[[str, int, int], None] | None = None) -> list[MaskingStats]:
        """Запустить маскирование."""
        session_id = f"session_{int(time.time())}"
        self._connect()
        self._fk_graph = self._build_fk_graph()
        self._session = MaskingSession(session_id, self.cache)

        # Топологическая сортировка
        ordered_tables = self._fk_graph.topological_sort()
        rules_map = self._get_table_rules_map()

        # Добавить таблицы из конфига в том же порядке
        final_order = [t for t in ordered_tables if t in rules_map]
        # Добавить таблицы из конфига, которых нет в FK-графе
        for rule in self.config.tables:
            if rule.name.lower() not in final_order:
                final_order.append(rule.name.lower())

        logger.info(f"Порядок обработки таблиц (FK-safe): {final_order}")

        all_stats = []
        for tname in final_order:
            rule = rules_map.get(tname)
            if not rule:
                continue
            stats = self._process_table(rule, self._session, progress_callback)
            all_stats.append(stats)

        if self.audit:
            self.audit.log_session(session_id, all_stats)

        self.cache.set(f"session:{session_id}:stats", [s.to_dict() for s in all_stats])
        return all_stats

    def _process_table(self, rule: TableRule, session: MaskingSession,
                       progress_callback: Callable | None) -> MaskingStats:
        stats = MaskingStats(table=rule.name)
        t0 = time.time()
        logger.info(f"Обработка таблицы: {rule.name}")

        if self.config.mode == "dry_run":
            # Прочитать и замаскировать без записи
            with self._source_engine.connect() as src_conn:
                for total, batch in self._fetch_rows(src_conn, rule.name, rule, rule.batch_size):
                    for row in batch:
                        self._mask_row(row, rule, session)
                        stats.rows_processed += 1
                        stats.rows_masked += 1
            logger.info(f"  [dry-run] {stats.rows_processed} строк")
        elif self.config.mode == "copy":
            with self._source_engine.connect() as src_conn:
                with self._target_engine.connect() as tgt_conn:
                    for total, batch in self._fetch_rows(src_conn, rule.name, rule, rule.batch_size):
                        masked_batch = [self._mask_row(row, rule, session) for row in batch]
                        if self.config.mode != "dry_run":
                            self._write_rows_copy(tgt_conn, rule.name, masked_batch)
                        stats.rows_processed += len(batch)
                        stats.rows_masked += len(masked_batch)
                        if progress_callback:
                            progress_callback(rule.name, stats.rows_processed, total)
                    tgt_conn.commit()
        elif self.config.mode == "in_place":
            with self._source_engine.connect() as conn:
                for total, batch in self._fetch_rows(conn, rule.name, rule, rule.batch_size):
                    masked_batch = [self._mask_row(row, rule, session) for row in batch]
                    self._write_rows_inplace(conn, rule.name, batch, masked_batch, rule)
                    stats.rows_processed += len(batch)
                    stats.rows_masked += len(masked_batch)
                    if progress_callback:
                        progress_callback(rule.name, stats.rows_processed, total)
                conn.commit()

        stats.duration_sec = time.time() - t0
        logger.info(f"  ✓ {stats.rows_processed} строк за {stats.duration_sec:.1f}с")
        return stats
