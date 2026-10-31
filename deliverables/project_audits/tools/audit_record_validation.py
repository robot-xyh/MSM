"""Validate administrative record tables without changing or scoring records."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path


def read_strict_json(path: Path):
    def reject_constant(value):
        raise ValueError(f"Nonstandard JSON number: {value}")

    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"JSON number exceeds finite float range: {value}")
        return number

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON member: {key!r}")
            result[key] = value
        return result

    try:
        return json.loads(path.read_text(encoding="utf-8-sig"),
                          parse_constant=reject_constant, parse_float=finite_float,
                          object_pairs_hook=unique_object)
    except ValueError as exc:
        raise ValueError(f"{path}: {exc}") from exc


def read_strict_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, strict=True)
        try:
            headers = next(reader, None)
            if not headers or any(not name.strip() for name in headers):
                raise ValueError("Missing or empty CSV header")
            if len(headers) != len(set(headers)):
                raise ValueError("Duplicate CSV header")
            rows = []
            for index, values in enumerate(reader, 1):
                if len(values) != len(headers):
                    raise ValueError(f"CSV data row {index}: expected {len(headers)} cells, got {len(values)}")
                rows.append(dict(zip(headers, values)))
            return rows
        except (ValueError, csv.Error) as exc:
            raise ValueError(f"{path}: {exc}") from exc


def _fields(config: dict, name: str, *, required: bool = False) -> list[str]:
    value = config.get(name, [])
    if (not isinstance(value, list) or (required and not value)
            or any(not isinstance(field, str) or not field.strip() for field in value)
            or len(value) != len(set(value))):
        raise ValueError(f"{name} must be a list of distinct, nonempty field names")
    return value


def _lookup(row: dict, field: str):
    value = row
    for part in field.split("."):
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def validate_records(rows: list[dict], config: dict) -> dict:
    """Check an explicitly supplied key and report missingness, not averages."""
    allowed = {"unique_key", "group_by", "seed_field", "numeric_fields", "nullable_fields"}
    if not isinstance(config, dict) or set(config) - allowed:
        raise ValueError("Invalid record_contract or unknown options")
    keys = _fields(config, "unique_key", required=True)
    groups = _fields(config, "group_by")
    numeric = _fields(config, "numeric_fields")
    nullable = _fields(config, "nullable_fields")
    seed = config.get("seed_field")
    if "seed_field" in config and (not isinstance(seed, str) or not seed.strip()):
        raise ValueError("seed_field must be a nonempty field name")
    if not set(nullable) <= set(numeric):
        raise ValueError("nullable_fields must be a subset of numeric_fields")
    if not set(groups) <= set(keys) or (seed is not None and seed not in keys):
        raise ValueError("group_by and seed_field must be included in unique_key")
    if "group_by" in config and seed is None:
        raise ValueError("group_by requires seed_field")

    seen, key_types, grouped = {}, {}, {}
    counts = {field: {"valid_count": 0, "missing_count": 0} for field in numeric}
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(f"Record {index} is not an object")
        key_values = {}
        for field in keys:
            try:
                value = _lookup(row, field)
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                raise ValueError(f"Record {index}: missing key field {field!r}") from exc
            if type(value) not in (str, int) or (isinstance(value, str) and not value.strip()):
                raise ValueError(f"Record {index}: key field {field!r} must be a nonempty string or integer")
            previous_type = key_types.setdefault(field, type(value))
            if type(value) is not previous_type:
                raise ValueError(f"Record {index}: inconsistent key type for {field!r}")
            key_values[field] = value
        key = tuple(key_values[field] for field in keys)
        if key in seen:
            raise ValueError(f"Duplicate record key {key!r}: records {seen[key]} and {index}")
        seen[key] = index

        for field in numeric:
            try:
                value = _lookup(row, field)
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                raise ValueError(f"Record {index}: missing numeric field {field!r}") from exc
            if value is None or (isinstance(value, str) and not value.strip()):
                if field not in nullable:
                    raise ValueError(f"Record {index}: null is not allowed for {field!r}")
                counts[field]["missing_count"] += 1
                continue
            try:
                valid = type(value) in (str, int, float) and math.isfinite(float(value))
            except (ValueError, OverflowError):
                valid = False
            if not valid:
                raise ValueError(f"Record {index}: {field!r} must contain a finite number")
            counts[field]["valid_count"] += 1

        if seed is not None:
            group_key = tuple(key_values[field] for field in groups)
            entry = grouped.setdefault(group_key, {"group": {field: key_values[field] for field in groups},
                                                   "record_count": 0, "seeds": set()})
            entry["record_count"] += 1
            entry["seeds"].add(key_values[seed])

    return {"status": "passed", "record_count": len(rows), "unique_key": keys,
            "numeric_fields": {field: {**count, "all_missing": bool(rows) and count["valid_count"] == 0}
                               for field, count in counts.items()},
            "groups": [{"group": item["group"], "record_count": item["record_count"],
                        "distinct_seed_count": len(item["seeds"])} for item in grouped.values()],
            "scope": "Record structure only; no deduplication, imputation, metric calculation or independence claim."}
