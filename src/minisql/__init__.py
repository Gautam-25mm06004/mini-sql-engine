"""A small SQL engine: lexer, recursive-descent parser, rule-based optimiser (predicate pushdown, hash joins) and an
iterator-model executor with SQL NULL semantics."""
from .engine import Database
from .parser import parse

__all__ = ["Database", "parse"]
