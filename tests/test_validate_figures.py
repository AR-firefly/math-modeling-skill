"""validate_figures.py 静态预检测试（补 pytest 覆盖）。

回归点：
- good 样例全 PASS / bad 样例（rainbow + dpi<300）FAIL
- clabel 等值线标注 fontsize=8 是图内标注，不应触发 FONT-SIZE FAIL
- 中文字体集中配置在 import 的本地模块（examples/utils.py 模式）不误报 CN-FONT
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from validate_figures import (  # noqa: E402
    check_cn_font, validate_source,
)


def _levels(source, path=None):
    return {f.check_id: f.level for f in validate_source(source, path)}


def test_good_source_all_pass():
    good = '''
import matplotlib as mpl
mpl.rcParams.update({"font.sans-serif": ["SimHei"], "font.size": 11})
import matplotlib.pyplot as plt
fig, ax = plt.subplots()
ax.plot([1, 2, 3])
fig.savefig("figures/fig1.png", dpi=300)
'''
    lv = _levels(good)
    assert lv["CN-FONT"] == "PASS"
    assert lv["FONT-SIZE"] == "PASS"
    assert lv["RASTER-DPI"] == "PASS"
    assert lv["COLOR-MAP"] == "PASS"


def test_bad_colormap_and_dpi_fail():
    bad = '''
import numpy as np
import matplotlib.pyplot as plt
fig, ax = plt.subplots()
ax.imshow(np.zeros((3, 3)), cmap="jet")
fig.savefig("figures/fig1.png", dpi=72)
'''
    lv = _levels(bad)
    assert lv["COLOR-MAP"] == "FAIL"
    assert lv["RASTER-DPI"] == "FAIL"


def test_clabel_fontsize_not_fail():
    """回归：clabel 等值线标注 fontsize=8 是图内标注，不应触发 FONT-SIZE FAIL。"""
    src = '''
import matplotlib as mpl
mpl.rcParams.update({"font.sans-serif": ["SimHei"], "font.size": 11})
import matplotlib.pyplot as plt
fig, ax = plt.subplots()
cf = ax.contour([[0, 1], [1, 0]])
ax.clabel(cf, inline=True, fontsize=8)
fig.savefig("figures/fig1.png", dpi=300)
'''
    lv = _levels(src)
    assert lv["FONT-SIZE"] == "PASS"
    assert lv["CN-FONT"] == "PASS"


def test_cn_font_in_imported_module(tmp_path):
    """回归：字体集中配置在 import 的本地模块 → 单文件不误报 CN-FONT。"""
    src_path = tmp_path / "plot_demo.py"
    src_path.write_text('import utils\nfig.savefig("figures/fig1.png", dpi=300)\n',
                        encoding="utf-8")
    (tmp_path / "utils.py").write_text(
        'import matplotlib as mpl\nmpl.rcParams["font.sans-serif"] = ["SimHei"]\n',
        encoding="utf-8")
    assert check_cn_font(src_path.read_text(encoding="utf-8"), src_path).level == "PASS"
