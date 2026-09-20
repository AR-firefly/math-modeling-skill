"""论文结构化内容层（v3.0：TeX 单渲染）。

本模块只负责「从 results 构造论文内容层」，不涉及任何渲染后端：
    PAPER_STRUCT          : 论文骨架结构定义
    build_paper_content   : 由 results.json + meta 构造 paper.json 内容层
    find_paper_placeholders / plagiarism_risk_review / render_risk_points
    validate_references   : 参考文献校验

渲染由 tex_renderer.render_tex 消费本层产出。
v2.0 的 Word 渲染链路（PaperConfig / PaperGenerator）及其依赖已于 v3.0 移除，
备份见 `_deleted_backup/2026-09-10/`。
"""
import json


# ═══════════════════════════════════════
# 结构化内容层：PAPER_STRUCT + build_paper_content（tex_renderer 消费）
# ═══════════════════════════════════════

PAPER_STRUCT = {
    "meta": {"title": str, "school": str},
    "abstract": [str],                     # 摘要逐问分述，数字从 results 取
    "sections": [{"title": str, "paras": [str], "formulas": ["$..$"],
                  "tables": [{"caption", "headers", "rows"}],
                  "images": [{"path", "caption"}]}],
    "references": [str],
}


def _load_results(results_json):
    """读 results.json → dict。"""
    import json
    with open(results_json, "r", encoding="utf-8") as f:
        return json.load(f)


def _all_numbers(results, prefix=""):
    """递归提取 results 全部数值 → [(字段路径, 值)]。"""
    out = []
    for k, v in results.items():
        p = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out += _all_numbers(v, p)
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            out.append((p, float(v)))
    return out


def build_paper_content(results_json, meta, clean_reason=None, ref_dir=None,
                        images=None):
    """
    结构化论文内容层：所有数字从 results/ 读取（缺失输出占位符并登记）。
    深度参考 ref_dir 下对应题型优秀论文写初稿（AI 写论文时按题型检索 ref_dir）。
    返回 PAPER_STRUCT dict，供 tex_renderer 单渲染消费。
    参考文献标准（skill 自定，非国赛强制）：绝大部分近五年（2021-2026）、经典著作可例外；
    总数 ≤ 10 篇（上限非固定）；标准格式 + DOI/URL；文献必须真实，禁止编造。

    ref_dir: 共享语料目录。**None 时由 shared_corpus 定位**（SHARED_PAPERS_DIR /
    环境变量 MM_SHARED_PAPERS），不在此硬编码本机路径（C7）。

    images: 可选 dict {问号(数字): [{"path": "figures/figN.png", "caption": "图N ..."}]}，
    图契约登记的图嵌入对应"问题N求解"节（F1-01 打通图嵌入链路，对应 图表规范.md §四）。
    """
    if ref_dir is None:
        from .shared_corpus import resolve_shared_papers_dir
        ref_dir = str(resolve_shared_papers_dir())
    results = _load_results(results_json)
    numbers = _all_numbers(results)
    placeholder_issues = []

    def _r(path, fmt=None):
        """从 results 取数（点分路径），缺失记占位并返回 None。"""
        node = results
        for part in path.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                placeholder_issues.append(path)
                return None
        if fmt is None:
            return node
        try:
            return f"{node:{fmt}}"
        except (ValueError, TypeError):
            return node

    title = meta.get("title", "{{论文标题}}")
    school = meta.get("school", "")

    # 阅读证据由实际全文审阅提供，不能用首段摘录伪装阅读完成。
    ref_tip = ""

    abstract = [
        f"本文针对{title}，建立<题型>模型，采用<算法>求解。"
        "（AI 依据赛题与优秀论文参考生成，数字从 results/ 读取）",
    ]
    abstract = meta.get("abstract") or abstract
    sections = []
    # 一、问题重述
    sections.append({"title": "一、问题重述", "paras": [f"{title}问题背景与要求。"], "formulas": [], "tables": [], "images": []})
    # 二、问题分析（meta.analysis 提供，否则占位提示 AI 生成）
    analysis = meta.get("analysis") or [f"{title}问题分析：<AI 依据赛题与优秀论文生成>{ref_tip}"]
    sections.append({"title": "二、问题分析", "paras": analysis, "formulas": [], "tables": [], "images": []})
    # 三、数据处理（清洗理由）
    if clean_reason:
        sections.append({"title": "三、数据处理", "paras": [clean_reason], "formulas": [], "tables": [], "images": []})
    # 四、模型假设（meta.assumptions 提供，否则占位）
    assumptions = meta.get("assumptions") or [f"假设1：<AI 依据赛题生成>{ref_tip}"]
    sections.append({"title": "四、模型假设", "paras": assumptions, "formulas": [], "tables": [], "images": []})
    # 逐问求解：按问题分组（结果键 Q{qi}_ 前缀），每问一节含该问全部数字。
    # 关键：绝不能"每个数字当一问"编号——demo 每问多数字会错乱成问题1~4、且值错位。
    import re as _re
    from collections import OrderedDict
    q_groups = OrderedDict()
    for path, val in numbers:
        # 兼容扁平（Q1_最优值）与嵌套（Q1.最优值）两种 results 形态（v2.4 E）
        m = _re.match(r"^(Q\d+)[_.]", path)
        qkey = m.group(1) if m else None
        q_groups.setdefault(qkey, []).append((path, val))
    CN = "一二三四五六七八九十"
    start = 5 if clean_reason else 4
    q_idx = 0
    extra_results = ""
    for qkey, items in q_groups.items():
        if qkey is None:
            # 非 Q\d+ 前缀字段（配置/检验元数据）不进逐问求解节；并入评价段只显示值，
            # 不带字段路径（防路径里的数字如 p26_n24/x0*1.1 污染反向数值溯源，A6）
            extra_results = "，".join(f"{v:.4g}" for p, v in items)
            continue
        q_idx += 1
        num = CN[min(start + q_idx - 2, len(CN) - 1)]
        desc = "，".join(f"{p}={v:.4g}" for p, v in items)
        # images 用原始问号 key（"Q1"）关联，与 run_all 的 fig_images 一致（A6）
        sec_images = [dict(i) for i in (images or {}).get(qkey, [])]
        # 注意：正文不自动灌"见图N"——那是伪造正文引用骗过图契约检查（v2.4 A 反模式）。
        # 图嵌入本节（images 字段）即"图进了论文"，verify_figure_references 反向检查据此判定。
        para = f"问题{qkey[1:]}：关键结果 {desc}（来源 results 字段）"
        sections.append({
            "title": f"{num}、问题{qkey[1:]}求解",
            "paras": [para],
            "formulas": [], "tables": [], "images": sec_images,
        })
    # 模型评价（meta.evaluation 提供，否则占位提示）；编号 = 最后一个问题后的下一节，避免重复
    evaluation = meta.get("evaluation") or ["<AI 依据五样检验结果生成模型评价：优点/缺点/改进方向>"]
    if extra_results:
        evaluation = [f"全局关键结果（非单问字段）：{extra_results}"] + evaluation
    eval_idx = start + q_idx
    eval_num = CN[eval_idx - 1] if eval_idx <= len(CN) else str(eval_idx)
    sections.append({"title": f"{eval_num}、模型评价", "paras": evaluation, "formulas": [], "tables": [], "images": []})
    # 参考文献标准（skill 自定）：近五年为主、经典可例外；总数 ≤ 10（上限非固定）；标准格式 + DOI/URL；真实（禁止编造）
    references = list(meta.get("references") or [])
    if not references:
        placeholder_issues.append("references: 尚未提供真实参考文献")
    # 附录程序清单（国赛规范：附录含支撑材料文件列表 + 全部可运行源程序；缺程序/跑不通会被取消评奖资格）
    appendix = [
        "支撑材料文件列表：<程序清单>（AI 按求解脚本列出，保证全部可运行）",
        "建模所用全部可运行源程序代码见提交的支撑材料（RAR/ZIP，≤20MB）。",
    ]
    appendix = meta.get("appendix") or appendix
    paper = {
        "meta": {"title": title, "school": school, "keywords": meta.get("keywords", [])},
        "abstract": abstract,
        "sections": meta.get("sections", sections),
        "references": references,
        "appendix": appendix,
        "ai_declaration": "",
        "_human_todos": ["团队填写论文AI使用声明", "团队另行填写AI工具使用详情并逐项核验"],
        "_placeholder_issues": placeholder_issues,
    }
    placeholder_issues.extend(find_paper_placeholders(paper))
    return paper


def find_paper_placeholders(paper):
    """Report known template tokens without treating inequalities as HTML tags."""
    import re
    issues = []
    pattern = re.compile(r"\{\{.*?\}\}|<(?:题型|算法|模型|模型名|参数|标题|TODO|TBD)>|<AI[^>]*>|<程序清单>|待填充|待补充")
    def scan(node, path="paper"):
        if isinstance(node, dict):
            for key, value in node.items():
                if not str(key).startswith("_"):
                    scan(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                scan(value, f"{path}[{index}]")
        elif isinstance(node, str) and pattern.search(node):
            issues.append(path)
    scan(paper)
    return issues


def plagiarism_risk_review(paper_text, ref_papers):
    """
    查重风险点清单：将论文文本逐段与参考论文比对（n-gram 相似度）。
    返回 [{"paragraph", "ref_source", "similarity", "level", "suggestion"}]。
    写 output/risk_points.md（段落/来源/等级/改写建议）。
    诚实边界：AI 仅文本相似近似判断，不保证规避查重；最终以实际查重工具为准，责任在人工。
    """
    import re
    from difflib import SequenceMatcher
    risk_points = []

    def sent_similarity(a, b):
        return SequenceMatcher(None, a, b).ratio()

    def ngram(text, n=3):
        text = re.sub(r"\s+", "", text)
        return {text[i:i + n] for i in range(len(text) - n + 1)} if len(text) >= n else set()

    for para in re.split(r"(?<=[。；])", paper_text):
        para = para.strip()
        if len(para) < 10:
            continue
        for src_name, src_text in ref_papers.items():
            sim = sent_similarity(para, src_text)
            ng_intersect = len(ngram(para) & ngram(src_text))
            ng_union = len(ngram(para) | ngram(src_text)) or 1
            overall = max(sim, ng_intersect / ng_union)
            if overall < 0.35:
                continue
            level = "高" if overall >= 0.6 else ("中" if overall >= 0.45 else "低")
            suggestion = ("改写成自己的表述，调整句式与关键词，避免与参考原文雷同" if level == "高"
                          else "建议改写或用引注标注" if level == "中" else "复核原文表述")
            risk_points.append({
                "paragraph": para[:80],
                "ref_source": src_name,
                "similarity": round(overall, 3),
                "level": level,
                "suggestion": suggestion,
            })
    dedup = {}
    for r in risk_points:
        key = r["paragraph"]
        if key not in dedup or r["similarity"] > dedup[key]["similarity"]:
            dedup[key] = r
    return list(dedup.values())


def render_risk_points(risk_points, out_path="output/risk_points.md"):
    """把风险点清单写成 markdown（段落/来源/等级/改写建议）。"""
    from pathlib import Path
    lines = ["# 查重风险点清单（人工按此清单改写规避）", "",
             "> AI 仅文本相似近似判断，不保证规避查重；最终以实际查重工具为准，责任在参赛队。", ""]
    if not risk_points:
        lines.append("- 未检出高相似段落（如有扫描版参考论文，文本比对受限，请人工复核）")
    for i, r in enumerate(risk_points, 1):
        lines.append(f"## 风险点 {i}（{r['level']}风险，相似度 {r['similarity']:.2f}）")
        lines.append(f"- 段落：{r['paragraph']}")
        lines.append(f"- 参考来源：{r['ref_source']}")
        lines.append(f"- 改写建议：{r['suggestion']}")
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def validate_references(refs, current_year=2026, check_doi=False, timeout=5, source_evidence=None):
    """参考文献合规校验（skill 自定标准，非国赛强制）。

    标准：总数 ≤ 10（上限，非固定）；每条含年份（绝大部分近五年 2021-2026，经典著作可例外）；
    每条含 DOI 或 URL 或标准格式。返回 issues 列表（空 = 通过）。

    v2.1 增强（借鉴 nature-ref-verifier Step 2.0，Apache-2.0，见 NOTICE.md）：
    check_doi=True 时对每条 DOI 请求 Crossref `works/<DOI>`——404 = 疑似错号（issue），
    200 仅表示可解析；网络错误返回待核验问题。格式检查不证明真实性。
    source_evidence 按引用顺序提供 status/publisher/original_url/purpose/original_source/verification_note；
    真实交付必须提供证据，空列表不会被视为已核验。
    """
    import re
    issues = []
    from urllib.parse import urlparse
    excluded = ("csdn.net", "baidu.com", "xiaohongshu.com", "zhihu.com")
    if not refs:
        issues.append("参考文献为空，待核验")
    for index, ref in enumerate(refs):
        for url in re.findall(r"https?://[^\s]+", ref):
            host = (urlparse(url).hostname or "").lower()
            if any(host == d or host.endswith("." + d) for d in excluded):
                issues.append(f"第 {index + 1} 条属于不允许的来源")
        if source_evidence is not None:
            ev = source_evidence[index] if index < len(source_evidence) else {}
            required = ("publisher", "original_url", "purpose", "verification_note")
            if ev.get("status") != "verified" or ev.get("original_source") is not True or any(not ev.get(k) for k in required):
                issues.append(f"第 {index + 1} 条原始来源及用途待核验")
    if len(refs) > 10:
        issues.append(f"参考文献 {len(refs)} 篇 > 10 上限（skill 标准，非国赛强制）")
    for i, ref in enumerate(refs, 1):
        if "待填充" in ref or "{{" in ref:
            issues.append(f"第 {i} 条是占位符，未替换为真实文献：{ref[:40]}")
            continue
        if not re.search(r"(?:19|20)\d{2}", ref):
            issues.append(f"第 {i} 条无年份：{ref[:40]}")
        if not re.search(r"DOI|doi|https?://", ref):
            issues.append(f"第 {i} 条无 DOI/URL/标准格式：{ref[:40]}")
    if check_doi:
        import urllib.request
        import urllib.error

        for i, ref in enumerate(refs, 1):
            m = re.search(r"(10\.\d{4,9}/[^\s,;\[\]()]+)", ref)
            if not m:
                continue  # 无 DOI 的条目不查（有 URL 也算合格）
            doi = m.group(1).rstrip(".,")
            url = f"https://api.crossref.org/works/{doi}"
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": "math-modeling-skill/2.1"})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    if resp.status != 200:
                        issues.append(f"第 {i} 条 DOI 不可解析（HTTP {resp.status}）：{doi}")
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    issues.append(f"第 {i} 条 DOI 疑似错号（Crossref 404）：{doi}")
                else:
                    issues.append(f"第 {i} 条 DOI 待核验（HTTP {e.code}）：{doi}")
            except Exception as exc:
                issues.append(f"第 {i} 条 DOI 待核验（{type(exc).__name__}）：{doi}")
    return issues


# ===== 独立使用入口 =====
