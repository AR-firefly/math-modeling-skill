"""数值校验：防论文幻觉的三层技术强制。

职责：
1. verify_paper_numbers —— 递归提取 results 全部数值，检查论文文本出现对应数字
   （不一致返回 issues；空列表仅代表数字匹配，非语义通过）
2. write_run_manifest —— 生成复现清单（seed + 输入 SHA-256 + 命令 + 依赖版本 + 退出码）
3. build_provenance —— 数值归因表（论文数字 ↔ results 字段 ↔ 代码出处）

用法（run_pipeline 强制顺序）：
    求解完成 → 验证脚本 → 通过才冻结结果
    论文生成 → build_paper_content 经 _r() 只从 results 取数
    落盘前   → verify_paper_numbers(..., paper_to_text(paper)) 有 issues 阻断
"""
import math
import warnings
import hashlib
import json
import re
from pathlib import Path


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


_NUM_RE = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
# 跳过键：下划线开头（_algo/_param_ranges 等元键）与复现/输入参数（seed 在 run_manifest 不在论文）
_SKIP_KEYS = ("seed",)


def _all_numbers(results, prefix="", include_skipped=False):
    """递归提取 results 全部数值字段，返回 [(字段路径, 值)]。默认跳过元键与复现键。

    注意：`paper_generator.py` 另有一份同名实现，**不要合并**——那份不跳元键
    （调用方要拿全量再按 Q 号正则分组）且只处理 dict；本份支持 list/tuple，
    并可用 include_skipped=True 取回元键。
    """
    out = []
    if isinstance(results, dict):
        for k, value in results.items():
            if (str(k).startswith("_") or k in _SKIP_KEYS) and not include_skipped:
                continue
            path = f"{prefix}.{k}" if prefix else str(k)
            out.extend(_all_numbers(value, path, include_skipped))
    elif isinstance(results, (list, tuple)):
        for i, value in enumerate(results):
            out.extend(_all_numbers(value, f"{prefix}[{i}]", include_skipped))
    elif isinstance(results, (int, float)) and not isinstance(results, bool):
        out.append((prefix, float(results)))
    return out



def verify_paper_numbers(results_path, paper_text, tol=1e-2, reverse=False, *, claims=None, non_result_numbers=None):
    """数值校验（双向）。

    正向（防漏报）：results 里每个数值必须在论文文本出现，否则进 issues。
    反向（防错报）：reverse=True 时，论文里出现的数值若在 results 无出处，进 unmatched
        （防论文编造数字；不阻断，由调用方列入人工审核）。

    tol 默认 1e-2（1%）：容忍摘要四舍五入展示；数量级捏造（1.0 vs 99.9）仍被拦。
    返回 (issues, unmatched)。旧模式仅检查数字出现；不能据此判定语义通过。
    claims 模式检查明确声明映射，仍须独立语义审查。
    reverse=True 返回未被局部声明覆盖的数字候选（包括年份、编号等）。
    non_result_numbers=[{text: 单数字原文, kind: year/index/constant/citation/unit/input,
                         reason: 分类依据}] 可记录非结果数字例外，分类仍需独立审核。
    """
    if not isinstance(tol, (int, float)) or isinstance(tol, bool) or not math.isfinite(tol) or tol < 0:
        raise ValueError("tol must be a finite nonnegative number")
    if claims is not None and not isinstance(claims, list):
        raise ValueError("claims must be a list of explicit result mappings")
    if non_result_numbers is not None and not isinstance(non_result_numbers, list):
        raise ValueError("non_result_numbers must be a list")
    res = load_json(results_path)
    if claims is not None:
        issues = verify_result_claims(res, paper_text, claims, tol=tol)
        unmatched = []
        if reverse:
            residue = paper_text
            for claim in claims:
                if not isinstance(claim, dict):
                    continue
                for match in _claim_bindings(claim, claim.get("text", ""), tol):
                    residue = residue.replace(match.group(0), " ")
            for entry in non_result_numbers or []:
                if (not isinstance(entry, dict) or entry.get("kind") not in
                    {"year", "index", "constant", "citation", "unit", "input"}
                    or not isinstance(entry.get("text"), str) or not entry["text"]
                    or not entry.get("reason") or entry["text"] not in paper_text
                    or len(re.findall(_NUM_RE, entry["text"])) != 1):
                    issues.append("非结果数字分类缺少单一数字原文、合法类别或解释")
                    continue
                residue = residue.replace(entry["text"], " ")
            unmatched = list(dict.fromkeys(f"{float(t):g}" for t in re.findall(_NUM_RE, residue)))
        return issues, unmatched
    warnings.warn("仅完成数字出现检查；指标、单位及结论语义尚未核验", UserWarning, stacklevel=2)
    tokens = [float(t) for t in re.findall(_NUM_RE, paper_text)]
    issues = []
    for path, val in _all_numbers(res):
        if not any(abs(t - val) <= tol * max(1.0, abs(val)) for t in tokens):
            issues.append(f"结果字段 {path}={val} 未在论文中找到对应数字")

    unmatched = []
    if reverse:
        # 反向出处：纳入 seed 等跳过键的值（论文里出现 seed=42 不算编造，只是显示被跳过键）
        res_vals = [v for _, v in _all_numbers(res, include_skipped=True)]
        for t in tokens:
            # 只跳过"小整数"（1/2/3 等序号、单位），非整数小数（R²/比率/p 值/率等建模关键数）不跳过
            if t == int(t) and abs(t) < 5:
                continue
            if not any(abs(t - v) <= tol * max(1.0, abs(v)) for v in res_vals):
                unmatched.append(f"{t:g}")
    return issues, unmatched


def _claim_bindings(claim, text, tol):
    """Return local label-value-unit matches; never borrow another metric's number."""
    if not isinstance(claim, dict) or not isinstance(text, str):
        return []
    label, unit = claim.get("label"), claim.get("unit")
    if not isinstance(label, str) or not label or not isinstance(unit, str):
        return []
    number = claim.get("value_text")
    if number is not None and (not isinstance(number, str) or not re.fullmatch(_NUM_RE, number)):
        return []
    pattern = (re.escape(label) + r"\s*(?:(?:为|是|等于|为：|为:|[:：=])\s*)?"
               + "(?P<value>" + (re.escape(number) if number is not None else _NUM_RE)
               + r")(?![\d.eE])\s*" + re.escape(unit))
    try:
        value = float(claim["value"])
        return [match for match in re.finditer(pattern, text)
                if math.isfinite(value) and abs(float(match.group("value")) - value)
                <= tol * max(1, abs(value))]
    except (ValueError, TypeError, KeyError):
        return []


def verify_result_claims(results, paper_text, claims, tol=1e-2):
    """Check explicit publication claims, not general natural-language correctness.

    Each claim: path (flattened result key, arrays use [i]), text (exact excerpt),
    label, value, unit and expected_unit (empty string for dimensionless).
    Optional value_text is the exact displayed numeric token. Label, number and
    unit must be locally adjacent (optional 为/是/等于/:/=); arbitrary prose requires
    an explicit publication cell or local label-value phrase, never a broad paragraph.
    Optional scale/offset explicitly document unit conversion. A derived result
    must be materialized in results and supply derivation={inputs:[paths],
    code:..., validation:...}; this checks trace completeness, NOT proof validity.
    Every numeric result needs a claim. Independent semantic review remains required.
    """
    values = dict(_all_numbers(results))
    issues, covered = [], set()
    for claim in claims:
        if not isinstance(claim, dict):
            issues.append("结果声明必须是映射")
            continue
        path = claim.get("path", "")
        required = {"path", "text", "label", "value", "unit", "expected_unit"}
        if not required.issubset(claim):
            issues.append(f"{path}: 结果声明缺少必要字段")
            continue
        if not isinstance(path, str) or path not in values:
            issues.append(f"{path}: 无对应结果字段")
            continue
        covered.add(path)
        excerpt, label = claim["text"], claim["label"]
        if not isinstance(excerpt, str) or not excerpt or excerpt not in paper_text:
            issues.append(f"{path}: 声明原文未出现在论文中")
            continue
        if not isinstance(label, str) or not label or label not in excerpt:
            issues.append(f"{path}: 声明未包含指标名称")
        if claim["unit"] != claim["expected_unit"]:
            issues.append(f"{path}: 单位不一致")
        if claim["unit"] and str(claim["unit"]) not in excerpt:
            issues.append(f"{path}: 声明缺少单位")
        try:
            value = float(claim["value"])
            expected = values[path] * float(claim.get("scale", 1)) + float(claim.get("offset", 0))
            if not math.isfinite(value) or not math.isfinite(expected) or abs(value-expected) > tol * max(1, abs(expected)):
                issues.append(f"{path}: 声明数值与结果不一致")
            if not _claim_bindings(claim, excerpt, tol):
                issues.append(f"{path}: 数值未与指标及单位在局部声明中绑定；请提供单指标原文及value_text")
        except (TypeError, ValueError):
            issues.append(f"{path}: 非法数值或单位换算")
        if "derivation" in claim:
            derivation = claim["derivation"]
            if not isinstance(derivation, dict) or not derivation.get("inputs") or not derivation.get("code") or not derivation.get("validation"):
                issues.append(f"{path}: 派生结果证据不完整")
            elif any(key not in values for key in derivation["inputs"]):
                issues.append(f"{path}: 派生结果输入不存在")
    issues.extend(f"{path}: 缺少结果声明映射" for path in values if path not in covered)
    return issues


def write_run_manifest(out_dir, seed, command, input_files, deps=None, exit_code=0):
    """写 run_manifest.json：seed + 输入文件 SHA-256 + 命令 + 依赖版本 + 退出码。"""
    manifest = {
        "seed": seed,
        "command": command,
        "exit_code": exit_code,
        "deps": deps or {},
        "inputs": [
            {"path": str(p), "sha256": hashlib.sha256(Path(p).read_bytes()).hexdigest()}
            for p in input_files
        ],
    }
    out = Path(out_dir) / "run_manifest.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def build_provenance(results_path, paper_text, code_map, tol=1e-2):
    """数值归因表：论文数字 → results 字段 → 代码出处。

    code_map: {results 字段路径: "算法 .md 文件"}（solve_question 落盘时登记）。
    逐值判断：只有该数值确实出现在论文文本（容差内）才录入归因表。
    """
    res = load_json(results_path)
    tokens = [float(t) for t in re.findall(_NUM_RE, paper_text)]
    rows = []
    for path, val in _all_numbers(res):
        if any(abs(t - val) <= tol * max(1.0, abs(val)) for t in tokens):
            rows.append({"数字": val, "results字段": path,
                         "代码出处": code_map.get(path, "见 run_manifest.json")})
    return rows


def _body_text(paper):
    """正文文本（不含图 caption）——图契约检查的"正文引用"基准。

    图题 caption 自带"图N"（图契约登记的内容），若纳入则图题自证被引用、检查恒绿（A3）；
    正文引用必须来自章节正文（标题/paras/公式/表格），不含 images。
    """
    lines = list(paper.get("abstract", []))
    for s in paper.get("sections", []):
        lines.append(s.get("title", ""))
        lines.extend(s.get("paras", []))
        lines.extend(s.get("formulas", []))
        for t in s.get("tables", []):
            lines.extend(t.get("rows", []))
    lines.extend(paper.get("references", []))
    return "\n".join(str(x) for x in lines)


def normalize_figure_path(value):
    """manifest 内路径一律正斜杠（作图契约 §二）；反斜杠值在此归一化。

    兼容既有 Windows 反斜杠登记值（A14），非 Windows 侧不再解析失败。
    """
    return value.replace("\\", "/").strip() if isinstance(value, str) else value


def resolve_figure_entry(fig_dir, value, default_name, subdir=None, root_relative=True):
    """双布局解析（C5）：**先分层 → 再扁平 → 两处都不存在 = None**。

    fig_dir: 项目的 figures/ 目录。subdir: 分层子目录名（script→scripts、data_entrypoint→data）。
    `root_relative=True`（`script`/`data_entrypoint` 语义：相对项目根）时候选依次为：
    相对项目根的登记值 → 相对 figures/ 的登记值 → figures/<subdir>/<name> → figures/<name>。
    `root_relative=False`（`file` 语义：相对 figures/）时**只看 figures/ 下**——否则项目根
    偶然同名的文件会把"放错目录"判成通过（假绿）。
    返回 None 即"放错目录"（脚本/数据不在 figures/ 契约位置），调用方必须报 issue，不得当作通过。
    """
    norm = normalize_figure_path(value) or default_name
    basename = str(norm).rsplit("/", 1)[-1]
    candidates = [fig_dir.parent / norm, fig_dir / norm] if root_relative else []
    if subdir:
        candidates.append(fig_dir / subdir / basename)
    candidates.append(fig_dir / basename)
    for candidate in dict.fromkeys(candidates):
        if candidate.is_file():
            return candidate
    return None


def verify_figure_references(paper, figures_dir="figures", manifest_name="figures_manifest.json"):
    """图号引用交叉检查（图契约清单 ↔ 正文引用 ↔ 图文件 ↔ 脚本/数据入口）。空列表 = 通过。

    对应国赛"图题在图下、编号与正文一一对应"（格式 15%）：
    1. figures/figures_manifest.json 存在且图号连续（1,2,3... 无跳号）
    2. 正文引用的每个图号都登记在图契约清单里（防"提到图 3 却没有图 3"）
    2b 反向：登记的图要么被正文引用，要么被嵌入论文某节（图分丢失检测）
    3. 每张图的 PNG 文件存在（防"有编号没图"）
    4. 每张图的 `script` / `data_entrypoint` 按双布局能解析到（防"脚本放错目录/根本不存在"）

    **路径语义（作图契约 §二，写死）**：
    - `file`            —— 相对 `figures/`（如 `fig03_sensitivity_paramA.png`，不带 figures/ 前缀）
    - `script`          —— 相对项目根（如 `figures/scripts/fig03_sensitivity_paramA.py`）
    - `data_entrypoint` —— 相对项目根（如 `figures/data/fig03_sensitivity_paramA.json`）
    三者一律正斜杠；解析时反斜杠值先归一化（`normalize_figure_path`），
    再走 `resolve_figure_entry` 的双布局（分层 → 扁平 → 两处都不存在即 FAIL）。

    由 run_pipeline 渲染论文后调用；issues 列入人工审核方向，不阻断（demo 无图属正常）。
    """
    issues = []
    fig_dir = Path(figures_dir)
    manifest_path = fig_dir / manifest_name
    if not manifest_path.exists():
        return [f"图契约清单缺失：{manifest_path} 未生成（图契约要求每张图登记结论+数据出处，见 references/图契约.md）"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"图契约清单解析失败（需 UTF-8，见 Visualizer.save_manifest）：{exc}"]

    def _no_num(m):
        m_no = re.search(r"(\d+)", str(m.get("no", "")))
        return int(m_no.group(1)) if m_no else None

    numbers = [n for n in (_no_num(m) for m in manifest) if n is not None]
    if not numbers:
        return ["图契约清单图号格式不规范：no 字段应含数字编号（fig1/1）"]

    # 1 图号连续
    if numbers != list(range(1, len(numbers) + 1)):
        issues.append(f"图号不连续：{numbers}（应为 1..{len(numbers)}）")

    # 2 正文引用的图号都登记在契约里（用 _body_text，排除图题 caption 自证，A3）
    cited = sorted({int(n) for n in re.findall(r"图\s*(\d+)", _body_text(paper))})
    known = set(numbers)
    for n in cited:
        if n not in known:
            issues.append(f"正文引用图 {n} 但图契约清单无此图")
    # 2b 反向（F1-01）：契约登记的图要么被正文文字引用，要么被嵌入论文某节（图分丢失检测）。
    # 嵌入节（sections[].images 的 path 对应契约 file）即"图进了论文"；
    # 不要求正文逐字写"图N"（v2.4 A：曾用自动灌引用伪造正文引用，已撤销）。
    embedded = {Path(img.get("path", "")).name
                for s in paper.get("sections", []) for img in s.get("images", [])}
    for m in manifest:
        n = _no_num(m)
        if n is None:
            continue
        fname = normalize_figure_path(m.get("file")) or f"{m.get('no')}.png"
        if n not in cited and Path(fname).name not in embedded:
            issues.append(f"图契约登记图 {n} 未被正文引用也未嵌入论文（图分丢失风险）")

    # 3 每张图 PNG 存在（file 相对 figures/）
    for m in manifest:
        fname = normalize_figure_path(m.get("file")) or f"{m.get('no')}.png"
        if not (fig_dir / fname).is_file() and resolve_figure_entry(
                fig_dir, fname, f"{m.get('no')}.png", root_relative=False) is None:
            issues.append(f"图 {m.get('no')} 文件缺失：figures/{fname}")

    # 4 脚本/数据入口按双布局解析（C5：分层 → 扁平 → 两处都不存在 = FAIL，放错目录必须抓到）
    for m in manifest:
        for key, default, subdir, label in (("script", f"{m.get('no')}.py", "scripts", "绘图脚本"),
                                            ("data_entrypoint", f"{m.get('no')}.json", "data", "数据入口")):
            value = normalize_figure_path(m.get(key)) or default
            if resolve_figure_entry(fig_dir, m.get(key), default, subdir) is None:
                issues.append(
                    f"图 {m.get('no')} {label}放错目录或缺失：{value}"
                    f"（应相对项目根，如 figures/{subdir}/{Path(value).name}；分层与扁平两处都不存在）")
    return issues


def _cited_numbers(text):
    """从正文提取引用编号集合，支持 [1-3] / [1,2] / [1] 合并写法。"""
    nums = set()
    for m in re.finditer(r"\[([0-9\-–,\s]+)\]", text or ""):
        for part in re.split(r"[,\s]+", m.group(1).strip()):
            if not part:
                continue
            if "-" in part or "–" in part:
                try:
                    lo, hi = re.split(r"[-–]", part)[:2]
                    nums.update(range(int(lo), int(hi) + 1))
                except ValueError:
                    pass
            else:
                try:
                    nums.add(int(part))
                except ValueError:
                    pass
    return nums


def verify_citations(paper_text, refs):
    """引用编号对应检查：正文 [N] ↔ 参考文献列表一一对应（WARN 级，返回问题列表，不阻断）。

    借鉴 Lupynow math-modeling-paper 参考文献红线（引了要列、列了要引）：
    1. 正文引用编号超出列表条数 → 列表有缺
    2. 列表条目在正文未被引用 → 列了要引
    正文无 [N] 引用（可能用上标/作者-年）不强查。
    """
    warns = []
    cited = sorted(_cited_numbers(paper_text))
    if not cited:
        return []
    n_refs = len(refs)
    over = [n for n in cited if n > n_refs]
    if over:
        warns.append(f"正文引用编号 {over} 超出参考文献列表（仅 {n_refs} 条），列表有缺")
    unused = [i for i in range(1, n_refs + 1) if i not in cited]
    if unused:
        warns.append(f"参考文献第 {unused[:6]} 条在正文未被引用（列了要引）")
    return warns
