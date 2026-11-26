"""Strict JSON with decimal-preserving input snapshots."""

from decimal import Decimal, InvalidOperation
import json
from pathlib import Path

from .errors import ModelError


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ModelError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def loads(text: str | bytes):
    def numeric(token, convert):
        if len(token) > 80:
            raise ModelError("JSON numeric token is too long.")
        return convert(token)
    try:
        return json.loads(text, parse_float=lambda token: numeric(token, Decimal),
                          parse_int=lambda token: numeric(token, int), object_pairs_hook=_unique,
                          parse_constant=lambda value: (_ for _ in ()).throw(
                              ModelError(f"Non-finite JSON value: {value}")))
    except ModelError:
        raise
    except (ValueError, InvalidOperation, UnicodeDecodeError, RecursionError) as exc:
        raise ModelError("Invalid JSON document.") from exc


def load(path: str | Path):
    return loads(Path(path).read_text(encoding="utf-8"))


def dumps(value) -> str:
    """Encode Decimal as a JSON number without rounding it through binary float."""
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ModelError("Non-finite JSON amount.")
        return str(value)
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ModelError("JSON object keys must be strings.")
        return "{" + ",".join(json.dumps(k, ensure_ascii=False) + ":" + dumps(v)
                              for k, v in value.items()) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(dumps(x) for x in value) + "]"
    return json.dumps(value, allow_nan=False, ensure_ascii=False)
