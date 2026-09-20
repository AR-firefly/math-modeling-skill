import json
from math_modeling.process_recorder import ProcessRecorder
from math_modeling.verify import verify_paper_numbers


def test_resume_preserves_raw_history(tmp_path):
    path = tmp_path / "process_record.md"
    old = "# 人工原文\r\n无法解析的历史\r\n## 断点\r\n- 当前阶段：第一问 / 下一步：审阅\r\n"
    path.write_bytes(old.encode())
    rec = ProcessRecorder(tmp_path)
    assert rec.resume() == "第一问"
    rec.log("算法取舍", "新决定").save()
    assert path.read_bytes().startswith(old.encode())
    rec.save()
    assert path.read_text(encoding="utf-8").count("新决定") == 1


def test_checkpoint_persists_and_latest_resumes(tmp_path):
    rec = ProcessRecorder(tmp_path)
    rec.checkpoint("阶段一", "等待")
    assert ProcessRecorder(tmp_path).resume() == "阶段一"
    rec.checkpoint("阶段二", "完成")
    assert ProcessRecorder(tmp_path).resume() == "阶段二"


def test_arrays_are_checked(tmp_path):
    p = tmp_path / "results.json"
    p.write_text(json.dumps({"route": [17, 29, 41]}))
    issues, _ = verify_paper_numbers(p, "没有路线")
    assert len(issues) == 3


def test_explicit_claim_rejects_metric_swap_and_unit(tmp_path):
    p = tmp_path / "results.json"
    p.write_text(json.dumps({"Q1": {"cost": 100, "time": 200}}))
    claims = [{"path": "Q1.cost", "text": "成本200元", "value": 200, "unit": "元", "expected_unit": "元", "label": "成本"},
              {"path": "Q1.time", "text": "时间100秒", "value": 100, "unit": "秒", "expected_unit": "分钟", "label": "时间"}]
    issues, _ = verify_paper_numbers(p, "成本200元，时间100秒", claims=claims)
    assert any("Q1.cost" in x for x in issues)
    assert any("单位" in x for x in issues)


def test_explicit_claim_checks_context_and_completeness(tmp_path):
    p = tmp_path / "results.json"
    p.write_text(json.dumps({"cost": 100, "time": 200}))
    claims = [{"path": "cost", "text": "成本100元", "value": 100, "unit": "元", "expected_unit": "元", "label": "成本"}]
    issues, _ = verify_paper_numbers(p, "成本100元，时间200分钟", claims=claims)
    assert any("time" in x for x in issues)


def test_concurrent_edit_is_not_overwritten(tmp_path):
    import pytest
    rec = ProcessRecorder(tmp_path)
    rec.save()
    path = tmp_path / "process_record.md"
    path.write_text("human edit", encoding="utf-8")
    with pytest.raises(RuntimeError):
        rec.log("算法取舍", "new").save()
    assert path.read_text() == "human edit"


def test_derived_claim_requires_trace(tmp_path):
    p = tmp_path / "results.json"
    p.write_text(json.dumps({"gain": 10}))
    claim = {"path": "gain", "text": "gain 10%", "label": "gain", "value": 10,
             "unit": "%", "expected_unit": "%", "derivation": {}}
    issues, _ = verify_paper_numbers(p, claim["text"], claims=[claim])
    assert any("派生" in x for x in issues)


def test_claim_array_path_and_context(tmp_path):
    p = tmp_path / "results.json"
    p.write_text(json.dumps({"route": [17]}))
    claim = {"path": "route[0]", "text": "first stop 17", "label": "first stop",
             "value": 17, "unit": "", "expected_unit": ""}
    assert verify_paper_numbers(p, claim["text"], claims=[claim]) == ([], [])
    assert verify_paper_numbers(p, "unrelated 17", claims=[claim])[0]


def test_broad_excerpt_cannot_swap_metric_values(tmp_path):
    p = tmp_path / "results.json"
    p.write_text(json.dumps({"cost": 100, "time": 200}))
    text = "成本200元，时间100秒"
    claims = [{"path": "cost", "text": text, "label": "成本", "value": 100, "unit": "元", "expected_unit": "元"},
              {"path": "time", "text": text, "label": "时间", "value": 200, "unit": "秒", "expected_unit": "秒"}]
    issues, _ = verify_paper_numbers(p, text, claims=claims)
    assert len(issues) >= 2


def test_claims_reverse_reports_outside_numbers_and_accepts_classification(tmp_path):
    p = tmp_path / "results.json"
    p.write_text(json.dumps({"cost": 100}))
    text = "成本100元。2026年实验。额外收益900元。"
    claim = {"path": "cost", "text": "成本100元", "label": "成本", "value": 100, "unit": "元", "expected_unit": "元"}
    issues, unmatched = verify_paper_numbers(p, text, claims=[claim], reverse=True)
    assert not issues
    assert "2026" in unmatched and "900" in unmatched
    issues, unmatched = verify_paper_numbers(p, text, claims=[claim], reverse=True,
        non_result_numbers=[{"text": "2026年", "kind": "year", "reason": "实验年份"}])
    assert not issues and "2026" not in unmatched and "900" in unmatched


def test_explicit_value_text_must_bind_to_label(tmp_path):
    p = tmp_path / "results.json"
    p.write_text(json.dumps({"cost": 100}))
    claim = {"path": "cost", "text": "成本为100.0元", "label": "成本", "value": 100,
             "value_text": "100.0", "unit": "元", "expected_unit": "元"}
    assert verify_paper_numbers(p, claim["text"], claims=[claim], reverse=True) == ([], [])
    claim["value_text"] = "999"
    assert verify_paper_numbers(p, claim["text"], claims=[claim])[0]


def test_custom_save_keeps_existing_file_and_repeated_save_is_idempotent(tmp_path):
    path=tmp_path/"custom.md"
    path.write_bytes(b"# Original custom history\r\n")
    rec=ProcessRecorder(tmp_path/"output")
    rec.log("算法取舍","new decision").save(path)
    rec.save(path)
    assert path.read_bytes().startswith(b"# Original custom history\r\n")
    assert path.read_text(encoding="utf-8").count("new decision") == 1


def test_claim_fractional_format_and_malformed_mapping(tmp_path):
    p=tmp_path/"results.json"
    p.write_text('{"rate":0.5}',encoding="utf-8")
    claim={"path":"rate","text":"rate .5","label":"rate","value":0.5,"value_text":".5","unit":"","expected_unit":""}
    assert verify_paper_numbers(p,claim["text"],claims=[claim],reverse=True) == ([],[])
    import pytest
    with pytest.raises(ValueError):
        verify_paper_numbers(p,"rate 0.5",claims={})


def test_claim_rejects_nonfinite_tolerance(tmp_path):
    p=tmp_path/"results.json"
    p.write_text('{"rate":0.5}',encoding="utf-8")
    claim={"path":"rate","text":"rate 900","label":"rate","value":900,"unit":"","expected_unit":""}
    import pytest
    with pytest.raises(ValueError):
        verify_paper_numbers(p,"rate 900",claims=[claim],tol=float("inf"))
