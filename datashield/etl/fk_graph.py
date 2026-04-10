"""
FK-Safe ETL Pipeline.
Анализ FK-графа, топологическая сортировка, snapshot/rollback.
"""
from __future__ import annotations
import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("datashield.fk_graph")


@dataclass
class FKRelation:
    from_table: str
    from_column: str
    to_table: str
    to_column: str


@dataclass
class TableNode:
    name: str
    pk_columns: list[str] = field(default_factory=list)
    fk_relations: list[FKRelation] = field(default_factory=list)  # исходящие FK (child → parent)
    row_count: int = 0


class FKGraph:
    """Граф зависимостей таблиц через внешние ключи."""

    def __init__(self):
        self.nodes: dict[str, TableNode] = {}
        self._edges: dict[str, set[str]] = defaultdict(set)  # table → {parent_tables}
        self._rev_edges: dict[str, set[str]] = defaultdict(set)  # table → {child_tables}

    def add_table(self, name: str, pk_columns: list[str] = None):
        self.nodes[name] = TableNode(name=name, pk_columns=pk_columns or [])

    def add_fk(self, from_table: str, from_col: str, to_table: str, to_col: str):
        if from_table not in self.nodes:
            self.nodes[from_table] = TableNode(name=from_table)
        if to_table not in self.nodes:
            self.nodes[to_table] = TableNode(name=to_table)
        rel = FKRelation(from_table, from_col, to_table, to_col)
        self.nodes[from_table].fk_relations.append(rel)
        self._edges[from_table].add(to_table)
        self._rev_edges[to_table].add(from_table)

    def topological_sort(self) -> list[str]:
        """
        Алгоритм Кана: таблицы без FK-зависимостей (корни) — первыми.
        Возвращает порядок для маскирования: от родителей к детям.
        Это обратный порядок: сначала маскируем родительские таблицы (у которых нет FK),
        затем дочерние (используя маппинг PK из кэша).
        """
        in_degree = {t: len(self._edges.get(t, set())) for t in self.nodes}
        queue = deque([t for t, d in in_degree.items() if d == 0])
        order = []

        while queue:
            node = queue.popleft()
            order.append(node)
            for child in list(self._rev_edges.get(node, [])):
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)

        # Добавить таблицы не вошедшие (циклические FK)
        remaining = [t for t in self.nodes if t not in order]
        if remaining:
            logger.warning(f"Обнаружены циклические FK: {remaining}. Будут обработаны без FK-маппинга.")
            order.extend(remaining)

        return order

    def get_fk_columns(self, table: str) -> list[FKRelation]:
        """FK-колонки таблицы (ссылки на другие таблицы)."""
        return self.nodes.get(table, TableNode(name=table)).fk_relations

    def get_parent_tables(self, table: str) -> set[str]:
        return self._edges.get(table, set())

    def __repr__(self) -> str:
        lines = [f"FKGraph({len(self.nodes)} таблиц, {sum(len(v) for v in self._edges.values())} FK):"]
        for t in self.topological_sort():
            parents = self._edges.get(t, set())
            if parents:
                lines.append(f"  {t} → {', '.join(parents)}")
            else:
                lines.append(f"  {t} (корень)")
        return "\n".join(lines)


def discover_fk_graph(connection, schema: str = None) -> FKGraph:
    """
    Автоматически построить FK-граф из INFORMATION_SCHEMA.
    Поддерживает PostgreSQL, MariaDB/MySQL, Oracle.
    """
    from sqlalchemy import text
    graph = FKGraph()

    dialect = connection.dialect.name

    # ── Получить таблицы ──────────────────────────────────────────────────────
    if dialect in ("postgresql", "mysql", "mariadb"):
        schema_filter = f"= '{schema}'" if schema else "= current_schema()" if dialect == "postgresql" else "= database()"
        tables_sql = f"""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema {schema_filter}
              AND table_type = 'BASE TABLE'
        """
    elif dialect == "oracle":
        tables_sql = "SELECT table_name FROM user_tables"
    else:
        return graph

    with connection.connect() as conn:
        tables_result = conn.execute(text(tables_sql))
        for row in tables_result:
            table_name = row[0].lower() if dialect != "oracle" else row[0]
            graph.add_table(table_name)

        # ── Получить PK ───────────────────────────────────────────────────────
        if dialect in ("postgresql", "mysql", "mariadb"):
            pk_sql = f"""
                SELECT kcu.table_name, kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                  AND tc.table_schema = kcu.table_schema
                WHERE tc.constraint_type = 'PRIMARY KEY'
                  AND tc.table_schema {schema_filter}
                ORDER BY kcu.ordinal_position
            """
        elif dialect == "oracle":
            pk_sql = """
                SELECT cols.table_name, cols.column_name
                FROM all_constraints cons
                JOIN all_cons_columns cols ON cons.constraint_name = cols.constraint_name
                WHERE cons.constraint_type = 'P' AND cons.owner = USER
                ORDER BY cols.position
            """
        else:
            pk_sql = None

        if pk_sql:
            pk_result = conn.execute(text(pk_sql))
            for row in pk_result:
                tname = row[0].lower() if dialect != "oracle" else row[0]
                col = row[1].lower() if dialect != "oracle" else row[1]
                if tname in graph.nodes:
                    graph.nodes[tname].pk_columns.append(col)

        # ── Получить FK ───────────────────────────────────────────────────────
        if dialect in ("postgresql", "mysql", "mariadb"):
            fk_sql = f"""
                SELECT
                    kcu.table_name,
                    kcu.column_name,
                    kcu.referenced_table_name,
                    kcu.referenced_column_name
                FROM information_schema.key_column_usage kcu
                JOIN information_schema.table_constraints tc
                  ON tc.constraint_name = kcu.constraint_name
                  AND tc.table_schema = kcu.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND kcu.table_schema {schema_filter}
                  AND kcu.referenced_table_name IS NOT NULL
            """
        elif dialect == "oracle":
            fk_sql = """
                SELECT
                    a.table_name,
                    a.column_name,
                    c_pk.table_name r_table_name,
                    b.column_name r_column_name
                FROM all_cons_columns a
                JOIN all_constraints c ON a.owner = c.owner AND a.constraint_name = c.constraint_name
                JOIN all_constraints c_pk ON c.r_owner = c_pk.owner AND c.r_constraint_name = c_pk.constraint_name
                JOIN all_cons_columns b ON c_pk.owner = b.owner AND c_pk.constraint_name = b.constraint_name
                WHERE c.constraint_type = 'R' AND c.owner = USER
            """
        else:
            fk_sql = None

        if fk_sql:
            fk_result = conn.execute(text(fk_sql))
            for row in fk_result:
                ft = row[0].lower() if dialect != "oracle" else row[0]
                fc = row[1].lower() if dialect != "oracle" else row[1]
                tt = row[2].lower() if dialect != "oracle" else row[2]
                tc = row[3].lower() if dialect != "oracle" else row[3]
                graph.add_fk(ft, fc, tt, tc)

    logger.info(f"FK-граф: {len(graph.nodes)} таблиц, {sum(len(v) for v in graph._edges.values())} FK-связей")
    return graph
