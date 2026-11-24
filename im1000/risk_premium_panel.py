#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
三大宽基指数「风险溢价(%)」图 —— 中证1000 / 沪深300 / 中证500
================================================================

复现截图中三张 Wind 风格图:
    风险溢价(%) = 1 / 市盈率(TTM, %) - 中国10年国债收益率(%)
    (危险值 / 中位数 / 机会值 = 全样本 20% / 50% / 80% 分位数)

数据源 (免费、无需 token)
-------------------------
  指数收盘点位 + 滚动市盈率(TTM):
      中证指数官网 https://www.csindex.com.cn/csindex-home/perf/index-perf
      2017-01-01 起日频, 字段 peg = 滚动市盈率 (历史全量, 一次约 800KB)
  中国10年国债收益率:
      中国债券信息网 https://yield.chinabond.com.cn/cbweb-pbc-web/pbc/historyQuery
      按年抓「中债国债收益率曲线」的 10 年期, 落盘缓存 bond_10y.csv

口径说明
--------
  * 风险溢价 = 100 / PE(TTM) - 中债10年期国债到期收益率, 单位 %.
  * 分位点 = 全样本中 <= 当前值的样本占比; 危险/中位/机会 = 20/50/80 分位数.
  * 标准差(+1/-1) = 均值 ± 1 倍样本标准差; z 分数 = (当前值 - 均值) / 标准差.
  * 中证指数官网的滚动市盈率剔除亏损样本, 与 Wind「整体法(含亏损)」口径不同,
    因此绝对数值会与截图略有差异, 但走势/分位高度一致.
    若需贴近截图当前值, 可用 --wind-scale 启用按截图校准的盈利收益率系数.

快速开始
--------
  pip install pandas numpy matplotlib requests lxml
  python risk_premium_panel.py            # 全量抓数 + 计算 + 出图 (首次)
  python risk_premium_panel.py --update   # 增量: 只刷新当年国债收益率
  python risk_premium_panel.py --plot     # 断网重画 (读本地 CSV)
  python risk_premium_panel.py --wind-scale   # 用截图校准系数

产物 (输出到本脚本所在目录)
---------------------------
  bond_10y.csv                    10年期国债收益率缓存
  rp_daily_000852.csv             中证1000 风险溢价日度序列
  rp_daily_000300.csv             沪深300
  rp_daily_000905.csv             中证500
  plot_rp_000852.png              中证1000 风险溢价图
  plot_rp_000300.png              沪深300 风险溢价图
  plot_rp_000905.png              中证500 风险溢价图
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd
import requests

# ============================================================ 配置
BASE_DIR = Path(__file__).resolve().parent
START_DATE = "20170101"  # 截图横轴从 2017-01 开始
CSINDEX_URL = "https://www.csindex.com.cn/csindex-home/perf/index-perf"
CHINABOND_URL = "https://yield.chinabond.com.cn/cbweb-pbc-web/pbc/historyQuery"
HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
MAX_RETRY = 3

INDICES = {
    "000852": {"name": "中证1000", "suffix": "000852.SH"},
    "000300": {"name": "沪深300", "suffix": "000300.SH"},
    "000905": {"name": "中证500", "suffix": "000905.SH"},
}

# 按截图 2026-11-20 的「1/市盈率(%)」校准的系数 (仅 --wind-scale 时启用)
WIND_EY_SCALE = {"000852": 0.643, "000300": 0.971, "000905": 0.762}

Q_DANGER, Q_MEDIAN, Q_OPPORTUNITY = 0.20, 0.50, 0.80


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def retry(fn, *args, **kwargs):
    last = None
    for i in range(MAX_RETRY):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.0 * (i + 1))
    raise RuntimeError(f"重试 {MAX_RETRY} 次仍失败: {last}")


# ============================================================ 取数
def fetch_index(code: str, start: str, end: str) -> pd.DataFrame:
    """中证指数官网: 日频收盘点位 + 滚动市盈率(peg)。"""
    params = {"indexCode": code, "startDate": start, "endDate": end}
    resp = retry(requests.get, CSINDEX_URL, params=params,
                 headers=HTTP_HEADERS, timeout=60)
    payload = resp.json()
    if str(payload.get("code")) != "200" or not payload.get("data"):
        raise RuntimeError(f"中证指数接口返回异常: {str(payload)[:200]}")
    df = pd.DataFrame(payload["data"])
    df = df.rename(columns={
        "tradeDate": "date", "close": "close", "peg": "pe", "changePct": "chg_pct",
    })
    keep = [c for c in ("date", "close", "pe", "chg_pct") if c in df.columns]
    df = df[keep].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for c in ("close", "pe", "chg_pct"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return (df.dropna(subset=["date", "close"])
              .query("pe > 0")
              .drop_duplicates("date")
              .sort_values("date")
              .reset_index(drop=True))


def fetch_bond_year(year: int) -> pd.DataFrame:
    """中国债券信息网: 某一年「中债国债收益率曲线」10 年期到期收益率。"""
    params = {
        "startDate": f"{year}-01-01", "endDate": f"{year}-12-31",
        "gjqx": "0", "qxId": "ycqx", "locale": "cn_ZH",
    }
    resp = retry(requests.get, CHINABOND_URL, params=params,
                 headers=HTTP_HEADERS, timeout=60)
    text = resp.text.replace("&nbsp", "")
    tables = pd.read_html(StringIO(text), header=None)
    # 页面首表是查询表单(也含"曲线名称"), 数据表行数远多于表单, 取最大的一张
    candidates = []
    for t in tables:
        flat = t.astype(str).apply(lambda col: col.str.contains("曲线名称", na=False).any()).any()
        if flat and len(t) > 5:
            candidates.append(t)
    if not candidates:
        raise RuntimeError(f"{year} 年中债页面未找到收益率表")
    tab = max(candidates, key=len)
    hdr = tab.index[tab[0].astype(str).str.strip() == "曲线名称"]
    if len(hdr) == 0:
        raise RuntimeError(f"{year} 年中债表头解析失败")
    tab = tab.loc[hdr[0]:].copy()
    tab.columns = [str(c).strip() for c in tab.iloc[0]]
    tab = tab.iloc[1:]
    tab = tab[tab["曲线名称"].astype(str).str.strip() == "中债国债收益率曲线"]
    date_col = next((c for c in tab.columns if "日期" in str(c)), None)
    yield_col = next((c for c in tab.columns if str(c).strip() in ("10年", "10年期")), None)
    if date_col is None or yield_col is None:
        raise RuntimeError(f"{year} 年中债表缺少日期/10年列: {list(tab.columns)}")
    out = pd.DataFrame({
        "date": pd.to_datetime(tab[date_col], errors="coerce"),
        "bond10": pd.to_numeric(tab[yield_col], errors="coerce"),
    })
    return out.dropna().drop_duplicates("date").sort_values("date")


def load_bond_cache() -> pd.DataFrame:
    path = BASE_DIR / "bond_10y.csv"
    if not path.exists():
        return pd.DataFrame(columns=["date", "bond10"])
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["bond10"] = pd.to_numeric(df["bond10"], errors="coerce")
    return df.dropna().sort_values("date")


def update_bond_cache(first_run: bool) -> pd.DataFrame:
    cache = load_bond_cache()
    this_year = datetime.now().year
    start_year = int(START_DATE[:4]) if first_run or cache.empty else max(
        int(START_DATE[:4]), int(cache["date"].max().year) - 1)
    years = list(range(start_year, this_year + 1))
    frames = []
    for y in years:
        try:
            part = fetch_bond_year(y)
            frames.append(part)
            log(f"  中债 10Y {y}: {len(part)} 行")
        except Exception as exc:  # noqa: BLE001
            log(f"  中债 10Y {y} 抓取失败: {exc}; 使用本地缓存")
    if frames:
        cache = pd.concat([cache] + frames, ignore_index=True)
        cache = (cache.drop_duplicates("date", keep="last")
                       .sort_values("date").reset_index(drop=True))
        cache.to_csv(BASE_DIR / "bond_10y.csv", index=False, encoding="utf-8-sig")
    return cache


# ============================================================ 计算
def build_panel(code: str, idx: pd.DataFrame, bond: pd.DataFrame,
                ey_scale: float = 1.0) -> pd.DataFrame:
    """按交易日对齐指数与国债收益率，计算风险溢价。国债用前向填充。"""
    df = pd.merge_asof(
        idx.sort_values("date"), bond.sort_values("date"),
        on="date", direction="backward",
    )
    df = df.dropna(subset=["bond10", "pe"]).copy()
    df["ey"] = 100.0 / df["pe"] * ey_scale
    df["rp"] = df["ey"] - df["bond10"]
    return df.reset_index(drop=True)


def risk_stats(s: pd.Series) -> dict:
    s = pd.Series(s).dropna()
    if len(s) < 30:
        raise ValueError("有效样本不足 30 个, 无法计算分位统计")
    current = float(s.iloc[-1])
    q = s.quantile([Q_DANGER, Q_MEDIAN, Q_OPPORTUNITY])
    mean, std = float(s.mean()), float(s.std(ddof=1))
    return {
        "current": current,
        "pct": float((s <= current).mean() * 100.0),
        "danger": float(q[Q_DANGER]),
        "median": float(q[Q_MEDIAN]),
        "opportunity": float(q[Q_OPPORTUNITY]),
        "maximum": float(s.max()),
        "mean": mean,
        "minimum": float(s.min()),
        "std_up": mean + std,
        "std_dn": mean - std,
        "z": (current - mean) / std if std > 0 else float("nan"),
        "std": std,
        "n": len(s),
    }


# ============================================================ 画图
def setup_chinese_font() -> None:
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei",
                                       "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.facecolor"] = "white"
    plt.rcParams["axes.facecolor"] = "white"


def info_text(ax, x: float, y: float, text: str, **kwargs):
    """左侧信息面板文字：统一使用 axes 归一化坐标。"""
    kwargs.setdefault("transform", ax.transAxes)
    return ax.text(x, y, text, **kwargs)


def plot_risk_premium(code: str, df: pd.DataFrame) -> Path:
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    from matplotlib.ticker import FuncFormatter

    setup_chinese_font()
    st = risk_stats(df["rp"])
    s = df.dropna(subset=["rp"]).copy()
    x = s["date"]
    y = s["rp"].to_numpy()
    meta = INDICES[code]
    last = s.iloc[-1]
    chg = float(last["chg_pct"]) if pd.notna(last.get("chg_pct")) else float(
        (last["close"] / s.iloc[-2]["close"] - 1) * 100)

    fig = plt.figure(figsize=(14.2, 5.9), dpi=130)
    gs = fig.add_gridspec(1, 2, width_ratios=[1.8, 8.4],
                          left=0.045, right=0.975, top=0.90,
                          bottom=0.165, wspace=0.04)
    ax_info = fig.add_subplot(gs[0, 0])
    ax_info.axis("off")
    ax = fig.add_subplot(gs[0, 1])
    ax2 = ax.twinx()

    # ---- 顶部标题栏
    up_color = "#c62828" if chg >= 0 else "#2e7d32"
    fig.text(0.045, 0.958, f"{meta['name']}  {meta['suffix']}",
             fontsize=13.5, fontweight="bold", color="#222")
    fig.text(0.205, 0.960, f"{last['close']:,.2f}", fontsize=13,
             fontweight="bold", color="#333")
    fig.text(0.283, 0.960, f"{chg:+.2f}%", fontsize=12.5,
             fontweight="bold", color=up_color)
    fig.text(0.355, 0.960, "历史PE/PB", fontsize=11.5, color="#444")

    # ---- 左侧统计面板
    info_text(ax_info,0, 1.00, "风险溢价(%)", fontsize=11, fontweight="bold",
                 color="#176b7a", va="top",
                 bbox=dict(boxstyle="round,pad=0.28", fc="#e7f5f7", ec="#7fb8c4"))
    info_text(ax_info,0, 0.935, "计算式:", fontsize=9.5, color="#444", va="top")
    info_text(ax_info,0, 0.893, "1/市盈率(%) - 中国10年国债收益率",
                 fontsize=8.3, color="#4b5563", va="top")

    row_y = 0.835
    gap = 0.055
    panel1 = [
        ("当前值", f"{st['current']:.2f}"),
        ("1/市盈率(%)", f"{last['ey']:.2f}"),
        ("中国10年国债收益率", f"{last['bond10']:.2f}"),
        ("分位点", f"{st['pct']:.1f}%"),
        ("危险值", f"{st['danger']:.2f}"),
        ("中位数", f"{st['median']:.2f}"),
        ("机会值", f"{st['opportunity']:.2f}"),
        ("指数点位", f"{last['close']:,.2f}"),
    ]
    for label, value in panel1:
        info_text(ax_info,0, row_y, label, fontsize=8.8, color="#374151", va="top")
        info_text(ax_info,1.0, row_y, value, fontsize=8.8, color="#111827",
                     va="top", ha="right", fontweight="bold")
        row_y -= gap
    ax_info.plot([0, 1], [row_y + 0.012, row_y + 0.012],
                 color="#d7dbe0", lw=0.8, transform=ax_info.transAxes)
    row_y -= 0.035
    panel2 = [
        ("最大值", f"{st['maximum']:.2f}"),
        ("平均值", f"{st['mean']:.2f}"),
        ("最小值", f"{st['minimum']:.2f}"),
        ("标准差(+1)", f"{st['std_up']:.2f}"),
        ("标准差(-1)", f"{st['std_dn']:.2f}"),
        ("z 分数", f"{st['z']:.2f}"),
    ]
    for label, value in panel2:
        info_text(ax_info,0, row_y, label, fontsize=8.8, color="#374151", va="top")
        info_text(ax_info,1.0, row_y, value, fontsize=8.8, color="#111827",
                     va="top", ha="right", fontweight="bold")
        row_y -= gap

    # ---- 主图: 风险溢价面积 + 三条分位线
    lo = min(float(np.nanmin(y)), st["danger"], st["std_dn"]) - 0.30
    hi = max(float(np.nanmax(y)), st["opportunity"], st["std_up"]) + 0.30
    if hi - lo < 1.0:
        lo, hi = lo - 0.5, hi + 0.5
    ax.set_ylim(lo, hi)
    ax.fill_between(x, lo, y, color="#a9d8df", alpha=0.72, linewidth=0, zorder=1)
    ax.plot(x, y, color="#69b9c4", lw=0.7, alpha=0.7, zorder=2)
    for value, color in ((st["opportunity"], "#2fa173"),
                         (st["median"], "#6b7280"),
                         (st["danger"], "#d04545")):
        ax.axhline(value, color=color, ls="--", lw=1.15, alpha=0.9, zorder=3)
    ax.set_ylabel("风险溢价(%)", fontsize=9.5, color="#333")
    ax.grid(axis="y", color="#9ca3af", alpha=0.16, lw=0.7)
    ax.tick_params(axis="y", labelsize=8.5, colors="#555")
    ax.tick_params(axis="x", labelsize=8.5, colors="#555")
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%y-01-01"))
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    # ---- 右轴: 指数点位 (浅色细线)
    close = s["close"].astype(float)
    ax2.plot(x, close, color="#94a3b8", lw=0.9, alpha=0.55, zorder=0)
    cmin, cmax = float(close.min()), float(close.max())
    pad = max((cmax - cmin) * 0.06, 1.0)
    ax2.set_ylim(cmin - pad, cmax + pad)
    ax2.set_ylabel("指数点位", fontsize=9.5, color="#7b8794")
    ax2.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax2.tick_params(axis="y", labelsize=8.5, colors="#7b8794")
    ax2.grid(False)
    ax2.spines["top"].set_visible(False)

    handles = [
        Patch(facecolor="#a9d8df", edgecolor="#a9d8df", label="风险溢价(%)"),
        Line2D([0], [0], color="#94a3b8", lw=1, label="指数点位"),
        Line2D([0], [0], marker="^", ls="", markerfacecolor="none",
               markeredgecolor="#8b929b", label="调仓标志"),
        Line2D([0], [0], marker="o", ls="", markerfacecolor="#b6bdc7",
               markeredgecolor="none", label="分位点"),
        Line2D([0], [0], color="#d04545", ls="--", lw=1.1, label="危险值"),
        Line2D([0], [0], color="#6b7280", ls="--", lw=1.1, label="中位数"),
        Line2D([0], [0], color="#2fa173", ls="--", lw=1.1, label="机会值"),
        Line2D([0], [0], color="#b9c0ca", ls="--", lw=1.0, label="平均值"),
        Line2D([0], [0], color="#b9c0ca", ls=":", lw=1.0, label="标准差(-1)"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=9,
               bbox_to_anchor=(0.5, 0.012), frameon=False, fontsize=8.2)

    path = BASE_DIR / f"plot_rp_{code}.png"
    fig.savefig(path)
    plt.close(fig)
    return path


# ============================================================ 主流程
def main() -> None:
    ap = argparse.ArgumentParser(description="三大宽基指数风险溢价图 (中证1000/沪深300/中证500)")
    ap.add_argument("--all", action="store_true", help="全量抓数 (默认)")
    ap.add_argument("--update", action="store_true", help="增量更新 (国债只刷近两年)")
    ap.add_argument("--plot", action="store_true", help="只用本地 CSV 重画图")
    ap.add_argument("--start", default=START_DATE, help="起始日 YYYYMMDD")
    ap.add_argument("--end", default=datetime.now().strftime("%Y%m%d"), help="结束日")
    ap.add_argument("--wind-scale", action="store_true",
                    help="用截图校准的盈利收益率系数, 使当前值与截图接近")
    args = ap.parse_args()
    if not (args.all or args.update or args.plot):
        args.all = True

    bond = load_bond_cache()
    if args.all or args.update:
        log("更新中债10年期国债收益率缓存 ...")
        bond = update_bond_cache(first_run=bool(args.all) or bond.empty)
        if bond.empty:
            sys.exit("国债收益率缓存为空, 请检查网络。")

    outputs = []
    for code, meta in INDICES.items():
        csv_path = BASE_DIR / f"rp_daily_{code}.csv"
        if args.plot:
            if not csv_path.exists():
                log(f"  跳过 {meta['name']}: 缺少 {csv_path.name}")
                continue
            panel = pd.read_csv(csv_path, parse_dates=["date"])
        else:
            log(f"抓取 {meta['name']} ({code}) 指数估值 ...")
            idx = fetch_index(code, args.start, args.end)
            scale = WIND_EY_SCALE[code] if args.wind_scale else 1.0
            panel = build_panel(code, idx, bond, scale)
            panel.to_csv(csv_path, index=False, encoding="utf-8-sig")
            log(f"  落盘 {len(panel)} 行, 最新 {panel['date'].iloc[-1]:%Y-%m-%d}")
        if panel.empty:
            continue
        st = risk_stats(panel["rp"])
        log(f"  {meta['name']} 风险溢价 {st['current']:.2f}%  分位 {st['pct']:.1f}%  "
            f"危险/中位/机会 {st['danger']:.2f}/{st['median']:.2f}/{st['opportunity']:.2f}")
        outputs.append(plot_risk_premium(code, panel))
    if outputs:
        log("图片输出: " + ", ".join(p.name for p in outputs))
    log("完成。")


if __name__ == "__main__":
    main()
