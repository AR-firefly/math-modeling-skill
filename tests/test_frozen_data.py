import json
import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from math_modeling.frozen_data import freeze_dataframe, load_frozen_dataframe


def test_roundtrip_exact_common_types(tmp_path):
    df = pd.DataFrame({"code": ["001", "002", None],
        "float": [np.nextafter(1.0, 2.0), -0.0, float("nan")],
        "category": pd.Categorical(["a", "b", "a"], categories=["b", "a", "c"], ordered=True),
        "time": pd.date_range("2026-01-01", periods=3, tz="Asia/Shanghai"),
        "nullable": pd.array([1, None, 3], dtype="Int64"),
        "text": pd.array(["001", None, "003"], dtype="string"),
        "flag": pd.array([True, None, False], dtype="boolean")})
    df.index = pd.Index(["r1", "r2", "r3"], name="sample")
    df.columns.name = "metric"
    p = tmp_path / "frozen.json"
    freeze_dataframe(df, p)
    restored = load_frozen_dataframe(p)
    assert_frame_equal(df, restored, check_exact=True)
    assert np.signbit(restored["float"].iloc[1])
    assert json.loads(p.read_text(encoding="utf-8"))["schema_version"] == 1


def test_range_index_and_empty_frame(tmp_path):
    for df in [pd.DataFrame({"x": [1,2]}, index=pd.RangeIndex(3,7,2,name="row")), pd.DataFrame()]:
        p = tmp_path / "frozen.json"
        freeze_dataframe(df,p)
        assert_frame_equal(df,load_frozen_dataframe(p),check_exact=True)


def test_unsupported_object_fails_before_writing(tmp_path):
    p = tmp_path / "frozen.json"
    with pytest.raises(ValueError):
        freeze_dataframe(pd.DataFrame({"x": [object()]}),p)
    assert not p.exists()


def test_corrupt_schema_is_rejected(tmp_path):
    p = tmp_path / "frozen.json"
    p.write_text('{"schema_version":999}',encoding="utf-8")
    with pytest.raises(ValueError):
        load_frozen_dataframe(p)


@pytest.mark.parametrize("index", [pd.date_range("2026-01-01", periods=3, freq="2h", tz="UTC", name="time"),
    pd.timedelta_range("1 day", periods=3, freq="2h", name="elapsed"),
    pd.CategoricalIndex(["b", "a", "b"], categories=["a", "b", "c"], ordered=True, name="group")])
def test_special_indexes_and_float32(tmp_path, index):
    df = pd.DataFrame({"x": np.array([1.1, 2.2, 3.3],dtype="float32")},index=index)
    p = tmp_path / "frozen.json"
    freeze_dataframe(df,p)
    assert_frame_equal(df,load_frozen_dataframe(p),check_exact=True)


def test_object_nulls_and_duplicate_columns(tmp_path):
    df = pd.DataFrame({"mixed": pd.Series([None, pd.NA, float("nan"), "001"],dtype=object),
                       "int": [1,2,3,4]})
    df.columns = ["x", "x"]
    p = tmp_path / "frozen.json"
    freeze_dataframe(df,p)
    restored = load_frozen_dataframe(p)
    assert_frame_equal(df,restored,check_exact=True)
    assert restored.iloc[0,0] is None and restored.iloc[1,0] is pd.NA


def test_rejected_frame_preserves_previous_snapshot(tmp_path):
    p = tmp_path / "frozen.json"
    original = pd.DataFrame({"x": [1]})
    freeze_dataframe(original,p)
    before = p.read_bytes()
    with pytest.raises(ValueError):
        freeze_dataframe(pd.DataFrame({"x": [complex(1,2)]}),p)
    assert p.read_bytes() == before
