"""E / 批次 2 —— manifest **状态机**单测（作图契约 §七；出口条件 5）。

状态链：`incomplete → pending_verification → reproduced → verified`
- `incomplete`          作图：缺必需字段即停（`missing_evidence` 非空）
- `pending_verification` 作图：必需字段齐全
- `reproduced`          **脚本自写**：脚本跑通产出 PNG，附 `artifact_hash` 三元组
- `verified`            **只由审查 Agent 写**：reviewer 非空 + 非作图 Agent 本人 +
                        evidence_hashes 逐一 hash + criteria_sha256 绑冻结基线

出口条件 5「artifact_hash 三元组能否防『重跑生成新图』」由本文件 + 变更**审查侧**
记录不符两段共同覆盖：
- 作图侧（本文件）：改脚本 / 改数据 / 重跑生成不同 PNG → 自动退回 pending_verification
- 审查侧（本文件 + `test_redo_audit_edges.py` 既有 3 例）：重跑后 manifest 手工改回去
  → 与审查侧 `docs/log_审查.md` 记录的 artifact_hash 不符 → FAIL

诚实边界
--------
审查 Agent 与作图 Agent 都是 AI 扮演，**「reviewer 非空」本身不构成独立性的证明**。
真独立性来自**证据哈希外部锚**（审查侧独立记录）+ `criteria_sha256` 绑定冻结基线。
哈希能防「手改状态」，**不能防「数据编造」**——若 results 本身就是编的，哈希照样一致；
后者只能靠插桩比对（证明「画进图里的数 = results 里的数」）与人审。
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from math_modeling.visualizer import (  # noqa: E402
    Visualizer, figure_artifact_hash, normalize_manifest_path,
)

STAGES = ("incomplete", "pending_verification", "reproduced", "verified")


def load_audit():
    """审查侧口径：gate_audit.py 的 validate_figure_evidence（与既有测试同范式）。"""
    spec = importlib.util.spec_from_file_location("e_status_audit", ROOT / "scripts/gate_audit.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["e_status_audit"] = module
    spec.loader.exec_module(module)
    return module


# ── 夹具：一张字段齐全、三元组已落盘的图 ───────────────────────────────
def make_visualizer(root, *, with_files=True):
    (root / "figures" / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "figures" / "data").mkdir(parents=True, exist_ok=True)
    script = root / "figures" / "scripts" / "fig1.py"
    data = root / "figures" / "data" / "fig1.json"
    png = root / "figures" / "fig1.png"
    if with_files:
        script.write_text("print(1)\n", encoding="utf-8")
        data.write_text('{"y": 1}', encoding="utf-8")
        png.write_bytes(b"\x89PNG demo" * 50)
    viz = Visualizer(output_dir=str(root / "figures"))
    viz.register_figure(
        "fig1", "基线耗时", "改进后耗时下降",
        "results/q1_results.json:Q1_基线_耗时",
        script="figures/scripts/fig1.py",
        data_entrypoint="figures/data/fig1.json",
        run_command="python figures/scripts/fig1.py",
        dependencies={"matplotlib": "3.7"},
        official_url="https://matplotlib.org/stable/api/_as_gen/matplotlib.pyplot.plot.html",
        official_api="matplotlib.pyplot.plot", adaptation="official_api_composition",
        changes="仅换数据", reason="对比基线",
        data_binding={"results_path": "results/q1_results.json",
                      "bindings": {"y": "Q1_基线_耗时"}})
    return viz, script, data, png


# ── 状态链正向流转 ────────────────────────────────────────────────────
def test_missing_data_binding_stays_incomplete(tmp_path):
    """缺 data_binding（机检新增必填）→ 真跑 register_figure 后停在 incomplete。"""
    (tmp_path / "figures").mkdir(parents=True, exist_ok=True)
    viz = Visualizer(output_dir=str(tmp_path / "figures"))
    viz.register_figure("fig1", "t", "c", "results/q1_results.json:Q1",
                        script="figures/scripts/fig1.py",
                        data_entrypoint="figures/data/fig1.json",
                        run_command="python figures/scripts/fig1.py", dependencies={},
                        official_url="https://matplotlib.org/stable/api/_as_gen/matplotlib.pyplot.plot.html",
                        official_api="matplotlib.pyplot.plot", adaptation="official_api_composition",
                        changes="c", reason="r")          # 故意不传 data_binding
    record = viz._figures[0]
    assert record["evidence_status"] == "incomplete"
    assert "data_binding" in record["missing_evidence"]
    with pytest.raises(ValueError, match="不得标记 reproduced"):
        viz.mark_reproduced("fig1")


def test_incomplete_figure_cannot_be_marked_reproduced(tmp_path):
    """incomplete → reproduced 的跃迁被拒（状态链不得跳级）。"""
    viz, _, _, _ = make_visualizer(tmp_path)
    viz._figures[0]["evidence_status"] = "incomplete"
    with pytest.raises(ValueError, match="不得标记 reproduced"):
        viz.mark_reproduced("fig1")


def test_complete_fields_land_on_pending_verification(tmp_path):
    """必需字段齐全 → pending_verification（**不是** reproduced）。"""
    viz, _, _, _ = make_visualizer(tmp_path)
    record = viz._figures[0]
    assert record["missing_evidence"] == []
    assert record["evidence_status"] == "pending_verification"


def test_mark_reproduced_writes_triple_hash(tmp_path):
    viz, script, data, png = make_visualizer(tmp_path)
    record = viz.mark_reproduced("fig1")
    assert record["evidence_status"] == "reproduced"
    assert record["artifact_hash"] == figure_artifact_hash(script, png, data)
    assert len(record["artifact_hash"]) == 64


def test_stage_chain_is_strictly_ordered(tmp_path):
    """状态值域与流转顺序与契约 §七 一致（防悄悄加状态/改字面值）。"""
    viz, _, _, _ = make_visualizer(tmp_path)
    assert viz._figures[0]["evidence_status"] == STAGES[1]
    assert viz.mark_reproduced("fig1")["evidence_status"] == STAGES[2]


# ── 出口条件 5：三元组任一变化 → 自动退回 ─────────────────────────────
@pytest.mark.parametrize("mutate", ["script", "data", "png"], ids=["改脚本", "改数据", "重跑生成不同PNG"])
def test_triple_change_demotes_to_pending_verification(tmp_path, mutate):
    viz, script, data, png = make_visualizer(tmp_path)
    viz.mark_reproduced("fig1")
    assert viz._figures[0]["evidence_status"] == "reproduced"
    if mutate == "script":
        script.write_text("print(2)\n", encoding="utf-8")
    elif mutate == "data":
        data.write_text('{"y": 2}', encoding="utf-8")
    else:
        png.write_bytes(b"\x89PNG other" * 50)      # 等价于重跑生成了不同的 PNG
    demoted = viz.refresh_statuses()
    assert demoted == ["fig1"], mutate
    record = viz._figures[0]
    assert record["evidence_status"] == "pending_verification", mutate
    assert "artifact_hash" not in record, "退回必须同时清掉旧哈希，不得留作下次假绿"


def test_verified_also_demotes_on_change(tmp_path):
    """verified 同样退回（只降不升，安全方向）——状态不脱钩不因 verified 而豁免。"""
    viz, script, _, _ = make_visualizer(tmp_path)
    viz._figures[0]["evidence_status"] = "verified"
    viz._figures[0]["artifact_hash"] = figure_artifact_hash(
        script, tmp_path / "figures" / "fig1.png", tmp_path / "figures" / "data" / "fig1.json")
    script.write_text("print(3)\n", encoding="utf-8")
    assert viz.refresh_statuses() == ["fig1"]
    assert viz._figures[0]["evidence_status"] == "pending_verification"


def test_save_manifest_triggers_demotion(tmp_path):
    """save_manifest 会自动跑一次失效检查（防「只改盘不刷新」）。"""
    viz, _, data, _ = make_visualizer(tmp_path)
    viz.mark_reproduced("fig1")
    data.write_text('{"y": 99}', encoding="utf-8")
    path = viz.save_manifest()
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written[0]["evidence_status"] == "pending_verification"
    assert "artifact_hash" not in written[0]


def test_untouched_triple_stays_reproduced(tmp_path):
    """反例的反例：什么都没改 → 不得误退回（防矫枉过正把正常流程判死）。"""
    viz, _, _, _ = make_visualizer(tmp_path)
    viz.mark_reproduced("fig1")
    assert viz.refresh_statuses() == []
    assert viz._figures[0]["evidence_status"] == "reproduced"


def test_missing_file_is_not_a_pass(tmp_path):
    """三元组缺件 ≠ 哈希一致：脚本没落盘时不得标记 reproduced。"""
    viz, script, _, _ = make_visualizer(tmp_path)
    script.unlink()
    with pytest.raises(ValueError, match="落盘"):
        viz.mark_reproduced("fig1")


def test_hash_is_none_when_any_file_missing(tmp_path):
    viz, script, data, png = make_visualizer(tmp_path)
    assert figure_artifact_hash(script, png, data)
    png.unlink()
    assert figure_artifact_hash(script, png, data) is None, "缺件必须返回 None，调用方按缺件处理"


def test_hash_is_order_sensitive(tmp_path):
    """三元组顺序固定（脚本 → 数据入口 → PNG），换序不得同哈希。"""
    viz, script, data, png = make_visualizer(tmp_path)
    assert figure_artifact_hash(script, png, data) != figure_artifact_hash(data, script, png)


# ── 防自证：无置 verified 的公开接口 ──────────────────────────────────
def test_no_public_interface_can_set_verified(tmp_path):
    """verified 只由审查 Agent 写 —— 作图侧不得提供任何置 verified 的入口。"""
    viz, _, _, _ = make_visualizer(tmp_path)
    public = [name for name in dir(viz) if not name.startswith("_")]
    assert "mark_verified" not in public
    assert not any("verified" in name for name in public), public
    viz.mark_reproduced("fig1")
    assert viz._figures[0]["evidence_status"] != "verified"


def test_mark_reproduced_never_raises_state_to_verified(tmp_path):
    """即使调用方手工把状态改成 verified，mark_reproduced 也只写 reproduced。"""
    viz, _, _, _ = make_visualizer(tmp_path)
    viz._figures[0]["evidence_status"] = "verified"
    assert viz.mark_reproduced("fig1")["evidence_status"] == "reproduced"


def test_unknown_figure_number_is_rejected(tmp_path):
    viz, _, _, _ = make_visualizer(tmp_path)
    with pytest.raises(ValueError, match="未登记"):
        viz.mark_reproduced("fig99")


# ── 审查侧口径（gate_audit）交叉确认：哈希外部锚 ───────────────────────
def _audit_project(tmp_path):
    for folder in ("figures/scripts", "figures/data", "references", "docs"):
        (tmp_path / folder).mkdir(parents=True, exist_ok=True)
    (tmp_path / "references" / "终审运行检查表.md").write_text("frozen criteria", encoding="utf-8")
    script = tmp_path / "figures/scripts/fig1.py"
    data = tmp_path / "figures/data/fig1.json"
    png = tmp_path / "figures/fig1.png"
    script.write_text("print(1)\n", encoding="utf-8")
    data.write_text('{"y": 1}', encoding="utf-8")
    png.write_bytes(b"\x89PNG" * 40)
    return script, data, png


def test_rerun_new_png_is_detected_vs_review_side_record(tmp_path):
    """出口条件 5 的审查侧面：重跑生成不同 PNG 后，作图侧单方面改回状态 → 外部锚不符。

    manifest 里的 artifact_hash 复写成新值（模拟作图 Agent 自己重写），
    但审查侧 `docs/log_审查.md` 记的还是旧哈希 → 必须 FAIL。
    """
    audit = load_audit()
    script, data, png = _audit_project(tmp_path)
    old_hash = figure_artifact_hash(script, png, data)
    docs = tmp_path / "docs" / "log_审查.md"
    docs.write_text("fig1 artifact_hash=%s\n" % old_hash, encoding="utf-8")

    # 重跑生成不同 PNG，作图侧把 manifest 的哈希刷成新的（绕过作图侧校验）
    png.write_bytes(b"\x89PNG different" * 40)
    new_hash = figure_artifact_hash(script, png, data)
    assert new_hash != old_hash
    figure = {"no": "fig1", "file": "fig1.png", "script": "figures/scripts/fig1.py",
              "data_entrypoint": "figures/data/fig1.json", "evidence_status": "reproduced",
              "artifact_hash": new_hash}
    assert audit.validate_figure_evidence(tmp_path, figure) == [], "作图侧自洽（这正是要防的假绿）"

    # 升级到 verified 时，外部锚必须拦下
    figure.update(evidence_status="verified", reviewer="independent-reviewer",
                  evidence_hashes={docs.relative_to(tmp_path).as_posix(): audit._sha256(docs)},
                  criteria_sha256=audit._sha256(tmp_path / "references/终审运行检查表.md"))
    issues = audit.validate_figure_evidence(tmp_path, figure, review_log_text=docs.read_text(encoding="utf-8"))
    assert any("外部锚" in issue for issue in issues), issues


def test_artifact_hash_must_match_disk_on_review_side(tmp_path):
    """审查侧再核一遍三元组：盘上变了而 manifest 没更新 → FAIL。"""
    audit = load_audit()
    script, data, png = _audit_project(tmp_path)
    figure = {"no": "fig1", "file": "fig1.png", "script": "figures/scripts/fig1.py",
              "data_entrypoint": "figures/data/fig1.json", "evidence_status": "reproduced",
              "artifact_hash": figure_artifact_hash(script, png, data)}
    assert audit.validate_figure_evidence(tmp_path, figure) == []
    script.write_text("print(2)\n", encoding="utf-8")
    issues = audit.validate_figure_evidence(tmp_path, figure)
    assert any("与磁盘三元组不符" in issue for issue in issues), issues


def test_review_side_unknown_status_is_not_a_pass(tmp_path):
    """缺省从严：未知状态不得当成通过（防「随便写个状态」蒙混）。"""
    audit = load_audit()
    _audit_project(tmp_path)
    figure = {"no": "fig1", "file": "fig1.png", "script": "figures/scripts/fig1.py",
              "data_entrypoint": "figures/data/fig1.json",
              "evidence_status": "looks_fine_to_me"}
    assert any("unknown evidence_status" in issue
               for issue in audit.validate_figure_evidence(tmp_path, figure))


# ── 路径归一化（出口条件 7 的状态机侧） ────────────────────────────────
def test_manifest_path_normalization():
    assert normalize_manifest_path("figures\\scripts\\fig1.py") == "figures/scripts/fig1.py"
    assert normalize_manifest_path("figures/scripts/fig1.py") == "figures/scripts/fig1.py"
    assert normalize_manifest_path(None) is None


def test_backslash_manifest_still_resolves(tmp_path):
    """manifest 写反斜杠（不规范但须可解析）→ 状态核验不误报。"""
    audit = load_audit()
    script, data, png = _audit_project(tmp_path)
    figure = {"no": "fig1", "file": "fig1.png", "script": "figures\\scripts\\fig1.py",
              "data_entrypoint": "figures\\data\\fig1.json", "evidence_status": "reproduced",
              "artifact_hash": figure_artifact_hash(script, png, data)}
    assert audit.validate_figure_evidence(tmp_path, figure) == []


def test_absolute_manifest_path_is_rejected(tmp_path):
    """绝对路径登记值不得被当成合法（哈希核验不得靠绝对路径绕过项目边界）。"""
    audit = load_audit()
    script, data, png = _audit_project(tmp_path)
    figure = {"no": "fig1", "file": "fig1.png", "script": str(script.resolve()),
              "data_entrypoint": "figures/data/fig1.json", "evidence_status": "reproduced",
              "artifact_hash": figure_artifact_hash(script, png, data)}
    issues = audit.validate_figure_evidence(tmp_path, figure)
    assert issues and "缺件" in issues[0], issues


def test_hash_algorithm_matches_explicit_sha256_chain(tmp_path):
    """哈希口径可复算：sha256(脚本) ‖ sha256(数据) ‖ sha256(PNG) 的链式 sha256。"""
    viz, script, data, png = make_visualizer(tmp_path)
    digest = hashlib.sha256()
    for path in (script, data, png):
        digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii"))
    assert figure_artifact_hash(script, png, data) == digest.hexdigest()


def test_schematic_may_omit_data_entrypoint(tmp_path):
    """示意图无数据入口：三元组退化为二元组仍须可算（契约 §一 豁免范围不变）。"""
    viz, script, _, png = make_visualizer(tmp_path)
    assert figure_artifact_hash(script, png, None) is not None
    assert figure_artifact_hash(script, png, None) != figure_artifact_hash(
        script, png, tmp_path / "figures/data/fig1.json")
