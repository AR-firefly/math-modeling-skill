"""Safe, exact JSON snapshots of common pandas tables; no executable serialization.

Unsupported objects, MultiIndex and metadata fail explicitly. Every write is
validated with assert_frame_equal(check_exact=True) before replacing the file.
Floating point cells use float.hex rather than lossy decimal JSON numbers.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal


def _cell(value):
    if value is pd.NA:
        return {"t": "NA"}
    if value is pd.NaT:
        return {"t": "NaT"}
    if isinstance(value, pd.Timestamp):
        return {"t": "timestamp", "v": value.isoformat()}
    if isinstance(value, pd.Timedelta):
        return {"t": "timedelta", "v": str(value.value)}
    if isinstance(value, np.generic):
        value = value.item()
    if value is None or isinstance(value, (str, bool, int)):
        return {"t": "scalar", "v": value}
    if isinstance(value, float):
        return {"t": "float", "v": value.hex()}
    raise ValueError(f"Unsupported frozen cell type: {type(value).__name__}")


def _uncell(cell):
    tag = cell["t"]
    if tag == "NA": return pd.NA
    if tag == "NaT": return pd.NaT
    if tag == "scalar":
        value = cell["v"]
        if value is not None and not isinstance(value, (str, bool, int)):
            raise ValueError("Invalid scalar cell")
        return value
    if tag == "float": return float.fromhex(cell["v"])
    if tag == "timestamp": return pd.Timestamp(cell["v"])
    if tag == "timedelta": return pd.Timedelta(int(cell["v"]), unit="ns")
    raise ValueError("Unsupported frozen cell tag")


def _dtype(dtype):
    if isinstance(dtype, pd.CategoricalDtype):
        return {"kind": "category", "categories": _axis(dtype.categories), "ordered": dtype.ordered}
    if isinstance(dtype, pd.StringDtype):
        return {"kind": "string", "storage": dtype.storage, "na_value": _cell(dtype.na_value)}
    if isinstance(dtype, (np.dtype, pd.DatetimeTZDtype)) or str(dtype) in {
        "Int8", "Int16", "Int32", "Int64", "UInt8", "UInt16", "UInt32", "UInt64",
        "Float32", "Float64", "boolean"}:
        if getattr(dtype, "kind", "") in {"c", "V"}:
            raise ValueError(f"Unsupported frozen dtype: {dtype}")
        return {"kind": "dtype", "name": str(dtype)}
    raise ValueError(f"Unsupported frozen dtype: {dtype}")


def _undtype(spec):
    kind = spec["kind"]
    if kind == "category":
        return pd.CategoricalDtype(_unaxis(spec["categories"]), ordered=spec["ordered"])
    if kind == "string":
        missing = _uncell(spec["na_value"])
        try:
            return pd.StringDtype(storage=spec["storage"], na_value=missing)
        except TypeError:
            if missing is not pd.NA:
                raise ValueError("This pandas version cannot restore string missing-value semantics")
            return pd.StringDtype(storage=spec["storage"])
    if kind == "dtype": return pd.api.types.pandas_dtype(spec["name"])
    raise ValueError("Unsupported frozen dtype schema")


def _axis(index):
    if isinstance(index, pd.MultiIndex):
        raise ValueError("MultiIndex is not supported by frozen tables")
    result = {"name": _cell(index.name)}
    if isinstance(index, pd.RangeIndex):
        result.update(kind="range", start=index.start, stop=index.stop, step=index.step)
    else:
        result.update(kind="index", dtype=_dtype(index.dtype), values=[_cell(v) for v in index])
        if isinstance(index, (pd.DatetimeIndex, pd.TimedeltaIndex)):
            result["freq"] = index.freqstr
    return result


def _unaxis(spec):
    name = _uncell(spec["name"])
    if spec["kind"] == "range":
        return pd.RangeIndex(spec["start"], spec["stop"], spec["step"], name=name)
    if spec["kind"] != "index":
        raise ValueError("Unsupported frozen index schema")
    index = pd.Index([_uncell(v) for v in spec["values"]], dtype=_undtype(spec["dtype"]), name=name)
    if "freq" in spec:
        index.freq = spec["freq"]
    return index


def _decode(payload):
    if payload.get("schema_version") != 1 or payload.get("format") != "math-modeling-table":
        raise ValueError("Unsupported frozen table schema")
    index, columns = _unaxis(payload["index"]), _unaxis(payload["columns"])
    fields = payload["fields"]
    if len(fields) != len(columns):
        raise ValueError("Frozen table column count mismatch")
    series = []
    for field in fields:
        values = [_uncell(cell) for cell in field["values"]]
        if len(values) != len(index):
            raise ValueError("Frozen table row count mismatch")
        series.append(pd.Series(values, dtype=_undtype(field["dtype"])))
    frame = pd.concat(series, axis=1) if series else pd.DataFrame(index=range(len(index)))
    frame.index, frame.columns = index, columns
    frame.flags.allows_duplicate_labels = payload["allows_duplicate_labels"]
    return frame


def freeze_dataframe(df, path):
    """Atomically write an exactly round-tripped table, or raise ValueError."""
    try:
        if not isinstance(df, pd.DataFrame) or df.attrs:
            raise ValueError("Expected DataFrame without unsupported attrs metadata")
        payload = {"schema_version": 1, "format": "math-modeling-table",
                   "index": _axis(df.index), "columns": _axis(df.columns),
                   "allows_duplicate_labels": df.flags.allows_duplicate_labels,
                   "fields": [{"dtype": _dtype(df.iloc[:, i].dtype),
                               "values": [_cell(v) for v in df.iloc[:, i]]}
                              for i in range(len(df.columns))]}
        serialized = json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2)
        restored = _decode(json.loads(serialized))
        assert_frame_equal(df, restored, check_exact=True)
    except (AssertionError, TypeError, KeyError, OverflowError, ValueError) as exc:
        raise ValueError(f"Cannot preserve this DataFrame exactly: {exc}") from exc
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(serialized, encoding="utf-8")
    temporary.replace(path)


def load_frozen_dataframe(path):
    """Read only known JSON cell/schema types; never deserialize executable objects."""
    try:
        return _decode(json.loads(Path(path).read_text(encoding="utf-8")))
    except (TypeError, KeyError, AttributeError, OverflowError, ValueError) as exc:
        raise ValueError(f"Invalid frozen DataFrame: {exc}") from exc
