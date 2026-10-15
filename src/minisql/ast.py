"""AST nodes for expressions and statements."""
from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass(frozen=True)
class Col:
    table: Optional[str]
    name: str


@dataclass(frozen=True)
class Lit:
    value: Any


@dataclass(frozen=True)
class BinOp:
    op: str
    left: Any
    right: Any


@dataclass(frozen=True)
class Not:
    expr: Any


@dataclass(frozen=True)
class IsNull:
    expr: Any
    negate: bool


@dataclass(frozen=True)
class Agg:
    func: str          # COUNT SUM AVG MIN MAX
    arg: Any           # None for COUNT(*)
    distinct: bool = False


@dataclass(frozen=True)
class Star:
    pass


@dataclass
class SelectItem:
    expr: Any
    alias: Optional[str]


@dataclass
class TableRef:
    name: str
    alias: str


@dataclass
class Join:
    kind: str          # INNER / LEFT
    table: TableRef
    on: Any


@dataclass
class Select:
    items: List[SelectItem]
    base: TableRef
    joins: List[Join] = field(default_factory=list)
    where: Any = None
    group_by: List[Any] = field(default_factory=list)
    having: Any = None
    order_by: List[Any] = field(default_factory=list)   # (expr, desc)
    limit: Optional[int] = None
    distinct: bool = False


@dataclass
class CreateTable:
    name: str
    columns: List[str]


@dataclass
class Insert:
    table: str
    rows: List[List[Any]]
