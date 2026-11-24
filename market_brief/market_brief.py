# -*- coding: utf-8 -*-
"""
市场数据采集 + 钉钉表格推送
===========================
直接运行即可执行一次（无需任何参数）：自动取「最近一个已有完整数据的交易日」——
当天已收盘/已发布则取当天，否则自动落到上一交易日。逐项指标亦按其数据源的
最新可得日期取数（如两融天然为 T-1）。
数据按日期记录到 CSV（同一天重跑覆盖），并推送到钉钉群（markdown 表格形式）。

用法：
  python market_brief.py                   # 默认：立即采集一次 + 推送钉钉
  python market_brief.py --no-send         # 采集但不推送（只写 CSV）
  python market_brief.py --style align     # 换表格渲染风格（html/md/align）
  python market_brief.py --wechat          # 额外推一份到微信（Server酱）
  python market_brief.py --daemon          # 常驻模式，每天 RUN_AT 自动执行
  python market_brief.py --image           # 额外生成本地 PNG 报表（默认不生成）

依赖：pip install akshare requests schedule（钉钉推送只用 requests，无需额外 SDK）
数据源：akshare（上交所/深交所/中证指数/新浪/东方财富）+ 腾讯/新浪备用，见各函数注释；
        黄金 CFTC 非商业持仓（COMEX）：futuresbench（CFTC 官方 COT 整理，最新52周）+ akshare 全历史底座。
"""

import sys
import time
import logging
from datetime import datetime, date, time as dtime
from pathlib import Path

import pandas as pd
import schedule

# dingtalk_utils.py 统一维护在上一级 notice 目录（全工程共用一份）。
# 这里按文件路径加载并注册为 dingtalk_utils，而不是把 notice 目录塞进 sys.path ——
# 后者会让 notice 下的 log.py / stock/ 等本地模块遮蔽同名包，风险更大。
_DINGTALK_FILE = Path(__file__).resolve().parent.parent / "dingtalk_utils.py"
if "dingtalk_utils" not in sys.modules and _DINGTALK_FILE.exists():
    import importlib.util as _ilu

    _spec = _ilu.spec_from_file_location("dingtalk_utils", _DINGTALK_FILE)
    _mod = _ilu.module_from_spec(_spec)
    sys.modules["dingtalk_utils"] = _mod
    _spec.loader.exec_module(_mod)

# ----------------------------- 配置 -----------------------------

# Server酱 SendKey：到 https://sct.ftqq.com/ 微信扫码登录后复制（仅 --wechat 时用到）
SENDKEY = "SCT454506T0Ny5300dN8KWR91sYVeQAqfm"

# CSV 数据文件路径（默认与本脚本同目录）
BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "market_data.csv"

# 每日执行时间（仅 --daemon 常驻模式使用）
RUN_AT = "09:02"

# 钉钉表格渲染风格：html（PC 端真表格，推荐）/ md（标准管道表格）/ align（等宽对齐，最兼容）
DINGTALK_STYLE = "md"

# 拥挤度分位数回看窗口（交易日）
CROWDING_LOOKBACK = 250

# 主要股指 ERP 计算对象：中证官网代码 → 简称（与创新创业板指等无 PE 的指数无关）
ERP_INDEXES = [
    ("000016", "上证50"),
    ("000300", "沪深300"),
    ("000905", "中证500"),
    ("000852", "中证1000"),
]

# 申万宏源偏债混合基金指数（滚动 3 年年化 / 均值回归）
SW_FUND_INDEX = "807330"

# TMT 行业股票清单（ Technology/Media/Telecom ），来自用户分析器
TMT_CSV = r"C:\Users\admin\Documents\MCGA\notice\stock\tmt_industry_stocks.csv"

# Server酱消息标签
SC_TAGS = "市场数据|行情监控"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(BASE_DIR / "market_brief.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("market-brief")

MISSING = None  # 缺失值统一记为空


# --------------------------- 工具函数 ---------------------------

def safe_fetch(name, fn, retries=2, wait=3):
    """带重试的安全采集，失败返回 None 并记录日志。"""
    for i in range(retries + 1):
        try:
            return fn()
        except Exception as e:
            if i < retries:
                time.sleep(wait)
            else:
                log.warning("采集失败 [%s]: %s: %s", name, type(e).__name__, str(e)[:120])
    return None


def fmt(v, nd=2, suffix=""):
    """格式化数值，缺失显示 '--'。"""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "--"
    return f"{v:,.{nd}f}{suffix}"


def sign(v, nd=2, suffix=""):
    """带符号的百分比格式。"""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "--"
    return f"{v:+.{nd}f}{suffix}"


# --------------------------- 数据采集 ---------------------------

def collect_margin():
    """1. 沪深北两融余额（融资+融券，三所合计），单位：亿元

    三个交易所发布日期可能不同，取三所都有数据的最近交易日；
    变动额 = 最新日合计 - 前一交易日均值（同口径）。
    """
    out = {"两融余额_亿": MISSING, "两融余额变动_亿": MISSING, "_note": ""}
    df = safe_fetch("两融-上交所", ak_stock_margin_sse)
    if df is None or df.empty:
        return out
    df = df.sort_values("信用交易日期")
    dates = [str(d) for d in df["信用交易日期"]]
    # 上交所「融资融券余额」单位：元 → 亿元
    sse_map = {str(r["信用交易日期"]): float(r["融资融券余额"]) / 1e8 for _, r in df.iterrows()}

    def other_exchanges(d):
        """深交所（亿元）+ 北交所（万元→亿元）"""
        sz = safe_fetch(f"两融-深交所{d}", lambda: _szse(d), retries=1)
        bj = safe_fetch(f"两融-北交所{d}", lambda: _bse(d), retries=1)
        if sz is None or sz.empty or bj is None or bj.empty:
            return None
        return float(sz.iloc[0]["融资融券余额"]) + float(bj.iloc[0]["融资融券余额"]) / 1e4

    got = {}
    for d in reversed(dates[-8:]):
        v = other_exchanges(d)
        if v is not None:
            got[d] = v
            if len(got) >= 2:
                break

    common = [d for d in dates if d in got]  # 升序
    if not common:
        out["_note"] = "深/北交所两融数据缺失"
        return out
    d_last = common[-1]
    out["两融余额_亿"] = sse_map[d_last] + got[d_last]
    out["_note"] = f"两融日期={d_last}(沪深北)"
    if len(common) >= 2:
        d_prev = common[-2]
        out["两融余额变动_亿"] = out["两融余额_亿"] - (sse_map[d_prev] + got[d_prev])
    return out


def ak_stock_margin_sse():
    """上交所融资融券汇总，取最近 30 个自然日"""
    import akshare as ak

    end = datetime.now().strftime("%Y%m%d")
    start = (pd.Timestamp.now() - pd.Timedelta(days=40)).strftime("%Y%m%d")
    return ak.stock_margin_sse(start_date=start, end_date=end)


def _szse(d):
    import akshare as ak

    return ak.stock_margin_szse(date=d)


def _bse(d):
    """北交所融资融券汇总（万元）。

    akshare < 1.18 无 stock_margin_bse，旧版本直接走北交所官网同源接口兜底。
    """
    import akshare as ak

    fn = getattr(ak, "stock_margin_bse", None)
    if fn is not None:
        return fn(date=d)
    return _bse_direct(d)


def _bse_direct(d):
    """北交所官网融资融券汇总直连（与 akshare stock_margin_bse 同源），单位：万元"""
    import json
    import re
    import requests

    date_str = f"{d[:4]}-{d[4:6]}-{d[6:]}" if "-" not in d else d
    r = requests.get(
        "https://www.bse.cn/rzrqjyyexxController/summaryInfoResult.do",
        params={"callback": "cb", "transDate": date_str, "page": "0"},
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Referer": "https://www.bse.cn/disclosure/rzrq_trans_list.html",
        },
        timeout=30,
    )
    r.raise_for_status()
    # JSONP 形如 cb([[{...}], '2026-10-28'])：外层数组尾部混有单引号日期，
    # 参照 akshare 先把 ", '日期']" 替换为双引号再解析
    m = re.search(r"^[^(]+\((.*)\)\s*$", r.text, re.S)
    if not m:
        raise ValueError(f"北交所返回异常: {r.text[:80]}")
    payload = re.sub(r",\s*'(\d{4}-\d{2}-\d{2})'\s*\]$", r', "\1"]', m.group(1))
    data_list = json.loads(payload)[0]
    if not data_list:
        raise ValueError(f"北交所 {d} 无数据")
    item = data_list[0]
    return pd.DataFrame([{
        "融资买入额": pd.to_numeric(item.get("rzmreRound"), errors="coerce"),
        "融资余额": pd.to_numeric(item.get("rzyeRound"), errors="coerce"),
        "融券余额": pd.to_numeric(item.get("rqyeRound"), errors="coerce"),
        "融资融券余额": pd.to_numeric(item.get("rzrqyeRound"), errors="coerce"),
    }])


def collect_oil_gold():
    """2. 布油/WTI 价格涨跌幅；7. COMEX 黄金/白银及金银比；小型纳指期货连续"""
    out = {"布油_美元": MISSING, "布油涨跌幅%": MISSING,
           "WTI_美元": MISSING, "WTI涨跌幅%": MISSING,
           "COMEX黄金_美元": MISSING, "黄金涨跌幅%": MISSING,
           "COMEX白银_美元": MISSING, "白银涨跌幅%": MISSING,
           "金银比": MISSING,
           "纳指期货_点": MISSING, "纳指期货涨跌幅%": MISSING}
    df = safe_fetch("外盘期货", lambda: _foreign_realtime(["OIL", "CL", "GC", "SI"]))
    if df is not None and not df.empty:
        for _, row in df.iterrows():
            name = str(row["名称"])
            if "布伦特" in name:
                out["布油_美元"] = float(row["最新价"])
                out["布油涨跌幅%"] = float(row["涨跌幅"])
            elif "NYMEX" in name or "原油" in name:
                out["WTI_美元"] = float(row["最新价"])
                out["WTI涨跌幅%"] = float(row["涨跌幅"])
            elif "白银" in name:
                out["COMEX白银_美元"] = float(row["最新价"])
                out["白银涨跌幅%"] = float(row["涨跌幅"])
            elif "黄金" in name:
                out["COMEX黄金_美元"] = float(row["最新价"])
                out["黄金涨跌幅%"] = float(row["涨跌幅"])

    # 金/银任一缺失时，用新浪外盘 hf_GC / hf_SI 补齐（同源报价）
    if out["COMEX黄金_美元"] is MISSING or out["COMEX白银_美元"] is MISSING:
        for sym, k_price, k_chg in [("hf_GC", "COMEX黄金_美元", "黄金涨跌幅%"),
                                    ("hf_SI", "COMEX白银_美元", "白银涨跌幅%")]:
            if out[k_price] is not MISSING:
                continue
            q = safe_fetch(f"外盘-{sym}", lambda s=sym: _sina_hf_quote(s), retries=1)
            if q:
                out[k_price] = q["last"]
                if q["prev_settle"]:
                    out[k_chg] = round((q["last"] / q["prev_settle"] - 1) * 100, 4)

    # 金银比 = COMEX 金价 / COMEX 银价，保留两位小数
    if out["COMEX黄金_美元"] is not MISSING and out["COMEX白银_美元"] is not MISSING:
        if out["COMEX白银_美元"]:
            out["金银比"] = round(out["COMEX黄金_美元"] / out["COMEX白银_美元"], 2)

    # 小型纳指期货（E-mini NQ 连续），新浪 hf_NQ 实时
    hf = safe_fetch("纳指期货", lambda: _sina_hf_quote("hf_NQ"), retries=1)
    if hf is not None:
        out["纳指期货_点"] = hf["last"]
        out["纳指期货涨跌幅%"] = round((hf["last"] / hf["prev_settle"] - 1) * 100, 4)
    return out


def collect_gold_cot():
    """黄金 CFTC 非商业持仓（COMEX，基金/投机盘）：多头 / 空头 / 净多 + 空头全历史百分位。

    CFTC 周报：每周五发布截至上周二的持仓（滞后约 3 天），akshare 金十镜像通常滞后 2-3 周，
    故以 futuresbench.com（CFTC 官方 COT 数据的整理页，内嵌近 52 周序列）补最新一期，
    再用 akshare 全历史序列作底座计算全历史百分位。两源在重叠期口径一致（已交叉验证）。

    返回字段：黄金COT报告日 / 多头 / 空头 / 净多 / 空头全历史分位% / 空头周变化 / 净多周变化。
    任一源失败均有降级：仅 futuresbench → 用 52 周算分位并标注；仅 akshare → 用其最新一期（较旧）。
    """
    import json
    import re

    keys = ["黄金COT报告日", "黄金COT多头", "黄金COT空头", "黄金COT净多",
            "黄金COT空头全历史分位%", "黄金COT空头周变化", "黄金COT净多周变化"]
    out = {k: MISSING for k in keys}
    out["_note"] = ""

    # --- 源1：futuresbench 近 52 周（最新，含报告日）---
    fb = None
    try:
        import requests as _req
        hdr = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120"}
        r = _req.get("https://futuresbench.com/cot/gold", headers=hdr, timeout=25)
        r.raise_for_status()
        html = r.text
        dates = json.loads(re.search(r'"dates":(\[[^\]]+\])', html).group(1))
        longs = json.loads(re.search(r'"long":\{"noncomm":(\[[^\]]+\])', html).group(1))
        nets = json.loads(re.search(r'"net":\{"noncomm":(\[[^\]]+\])', html).group(1))
        if len(dates) == len(longs) == len(nets) and dates:
            # short = long - net（net 为净多 = 多 - 空）
            fb = [{"date": d, "long": longs[i], "short": longs[i] - nets[i], "net": nets[i]}
                  for i, d in enumerate(dates)]
    except Exception as e:
        log.warning("采集失败 [黄金COT-futuresbench]: %s: %s", type(e).__name__, str(e)[:100])
        out["_note"] += "COT最新源失败;"

    # --- 源2：akshare 全历史（底座，算全历史分位）---
    hist = None
    try:
        import akshare as ak
        df = ak.macro_usa_cftc_c_holding()
        df["日期"] = pd.to_datetime(df["日期"]).dt.strftime("%Y-%m-%d")
        df = df.sort_values("日期")
        df["黄金-空头仓位"] = pd.to_numeric(df["黄金-空头仓位"], errors="coerce")
        df["黄金-多头仓位"] = pd.to_numeric(df["黄金-多头仓位"], errors="coerce")
        df["黄金-净仓位"] = pd.to_numeric(df["黄金-净仓位"], errors="coerce")
        df = df.dropna(subset=["黄金-空头仓位"])
        df = df[df["黄金-空头仓位"] > 0]
        hist = [{"date": r["日期"], "long": int(r["黄金-多头仓位"]),
                 "short": int(r["黄金-空头仓位"]), "net": int(r["黄金-净仓位"])}
                for _, r in df.iterrows()]
    except Exception as e:
        log.warning("采集失败 [黄金COT-akshare历史]: %s: %s", type(e).__name__, str(e)[:100])
        out["_note"] += "COT历史底座失败;"

    # --- 合并：底座 + 最新源覆盖/追加（按日期去重）---
    series = None
    if hist and fb:
        m = {x["date"]: x for x in hist}
        for x in fb:
            m[x["date"]] = x
        series = [m[d] for d in sorted(m.keys())]
    elif fb:
        series = fb
        out["_note"] += "COT全历史分位用近52周近似;"
    elif hist:
        series = hist
        out["_note"] += "COT最新数据缺失,用akshare较旧一期;"

    if not series:
        return out

    last = series[-1]
    out["黄金COT报告日"] = last["date"]
    out["黄金COT多头"] = last["long"]
    out["黄金COT空头"] = last["short"]
    out["黄金COT净多"] = last["net"]

    # 空头全历史百分位：当前值在序列中小于其的样本占比
    shorts = [x["short"] for x in series]
    pct = sum(1 for s in shorts if s < last["short"]) / len(series) * 100
    out["黄金COT空头全历史分位%"] = round(pct, 1)

    # 周环比变化
    if len(series) >= 2:
        prev = series[-2]
        out["黄金COT空头周变化"] = last["short"] - prev["short"]
        out["黄金COT净多周变化"] = last["net"] - prev["net"]

    out["_note"] += f"COT报告日={last['date']}(CFTC非商业/COMEX黄金)"
    return out


def _sina_hf_quote(symbol):
    """新浪外盘 hf_ 实时行情：返回 {last, prev_settle, name, date}"""
    import requests

    headers = {"Referer": "https://finance.sina.com.cn"}
    r = requests.get(f"https://hq.sinajs.cn/list={symbol}", headers=headers, timeout=10)
    r.encoding = "gbk"
    fields = r.text.split('"')[1].split(",")
    if len(fields) < 14 or not fields[0]:
        raise ValueError(f"新浪 {symbol} 返回异常")
    return {
        "last": float(fields[0]),        # 最新价
        "prev_settle": float(fields[7]),  # 昨日结算价
        "name": fields[13],
        "date": fields[12],
    }


def _foreign_realtime(symbols):
    import akshare as ak

    return ak.futures_foreign_commodity_realtime(symbol=symbols)


def _daily_chg(df):
    """由日K序列计算最新涨跌幅（%），返回 (最新涨跌幅, 最新收盘, 前收)"""
    if df is None or len(df) < 2:
        return MISSING, MISSING, MISSING
    last, prev = df.iloc[-1], df.iloc[-2]
    c, p = float(last["close"]), float(prev["close"])
    chg = (c / p - 1) * 100 if p else MISSING
    return chg, c, p


def collect_global_indices():
    """3. 美日韩指数涨跌幅

    美股：新浪日线收盘口径（A股早间运行时为隔夜收盘）。
    日经225 / 韩国KOSPI：新浪实时行情 b_NKY / b_KOSPI（当日最新价与涨跌幅），
    失败时回落日线收盘口径。
    """
    out = {"标普500涨跌幅%": MISSING, "纳指涨跌幅%": MISSING, "道指涨跌幅%": MISSING,
           "日经225涨跌幅%": MISSING, "韩国KOSPI涨跌幅%": MISSING,
           "日经225_点": MISSING, "韩国KOSPI_点": MISSING, "_note": ""}

    def us(symbol):
        df = safe_fetch(f"美股指数{symbol}", lambda: _us_hist(symbol), retries=1)
        return _daily_chg(df)[0]

    def sina_global(name):
        df = safe_fetch(f"全球指数{name}", lambda: _global_hist(name), retries=1)
        return _daily_chg(df)[0]

    out["标普500涨跌幅%"] = us(".INX")
    out["纳指涨跌幅%"] = us(".NDX")
    out["道指涨跌幅%"] = us(".DJI")

    # 日经 / KOSPI：优先当日实时（盘中为最新价，收盘后为当日收盘）
    realtime_ok = True
    for sym, key_pt, key_chg, fallback in [
        ("b_NKY", "日经225_点", "日经225涨跌幅%", "日经225指数"),
        ("b_KOSPI", "韩国KOSPI_点", "韩国KOSPI涨跌幅%", "首尔综合指数"),
    ]:
        q = safe_fetch(f"实时-{sym}", lambda s=sym: _sina_b_index(s), retries=1)
        if q:
            out[key_pt] = q["last"]
            out[key_chg] = q["pct"]
        else:
            realtime_ok = False
            out[key_chg] = sina_global(fallback)
    if realtime_ok:
        out["_note"] = "日韩=当日实时"
    return out


def _sina_b_index(symbol):
    """新浪全球指数实时行情 b_ 前缀，返回 {name, last, chg, pct, date, time}"""
    import requests

    r = requests.get(f"https://hq.sinajs.cn/list={symbol}",
                     headers={"Referer": "https://finance.sina.com.cn"}, timeout=10)
    r.encoding = "gbk"
    fields = r.text.split('"')[1].split(",")
    if len(fields) < 8 or not fields[1]:
        raise ValueError(f"新浪 {symbol} 返回异常")
    return {
        "name": fields[0],
        "last": float(fields[1]),
        "chg": float(fields[2]),
        "pct": round(float(fields[3]), 2),
        "time": fields[5],
        "date": fields[6],
    }


def _us_hist(symbol):
    import akshare as ak

    return ak.index_us_stock_sina(symbol=symbol).tail(30)


def _global_hist(name):
    import akshare as ak

    return ak.index_global_hist_sina(symbol=name).tail(30)


def _drop_partial_today(df, col):
    """盘中运行时剔除今天的未完成K线。

    A 股 15:00 收盘，15:05 后视为当日数据已完整：
    - 若数据源已追加当日K线，即为完整收盘数据 → 用当天；
    - 若尚未追加，序列最后一行自然还是上一交易日 → 自动回落。
    """
    now = datetime.now()
    if now.time() >= dtime(15, 5):
        return df
    today_str = now.strftime("%Y-%m-%d")
    s = df[col].astype(str)
    return df[~s.str.startswith(today_str)]


def _target_trade_date():
    """目标交易日 = A 股最近一个已收盘的交易日。

    盘中/盘前运行返回上一交易日；15:05 后返回当天（数据已完整）。
    优先腾讯日 K（收盘后即时追加当日），新浪日 K 兜底（更新有滞后）。
    """
    df = safe_fetch("目标交易日-腾讯", lambda: _tx_index_daily("sh000001"), retries=1)
    if df is None or df.empty:
        df = safe_fetch("目标交易日-新浪", lambda: _sina_index_daily("sh000001"), retries=1)
    if df is None or df.empty:
        return date.today().strftime("%Y-%m-%d")
    df = _drop_partial_today(df, "date")
    if df.empty:
        return date.today().strftime("%Y-%m-%d")
    return str(df.iloc[-1]["date"])


def _tx_index_daily(symbol, count=300):
    """腾讯指数日K（web.ifzq.gtimg.cn），返回 date/open/close/high/low/volume。

    volume 单位为「手」（×100 = 股）。收盘后即时追加当日K线。
    """
    import requests

    r = requests.get(
        "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
        params={"param": f"{symbol},day,,,{count},"},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()["data"][symbol]
    key = next(k for k in data if "day" in k)
    bars = data[key]
    df = pd.DataFrame([b[:6] for b in bars],
                      columns=["date", "open", "close", "high", "low", "volume"])
    for c in ["open", "close", "high", "low", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def collect_a_share(target_date=None):
    """4. A股成交额及主力净流入；9. 两市成交量

    两市口径：上证指数(sh000001，沪市全部) + 深证综指(sz399106，深市全部)。
    target_date：目标交易日，用于成交量对齐（新浪K线滞后时用腾讯K线补）。
    （大盘/TMT 拥挤度在 collect_top5_share，口径见该函数）
    """
    out = {"A股成交额_亿": MISSING, "主力净流入_亿": MISSING,
           "两市成交量_亿股": MISSING, "_备注": ""}

    # --- 成交额：优先东财日K（有 amount，单位元）；成交量固定用新浪（单位股） ---
    # 剔除当日未完成K线：盘前/盘中自动落到上一交易日，收盘后即为当天
    amounts, vols = {}, {}
    for sym in ["sh000001", "sz399106"]:
        t = safe_fetch(f"指数日K-东财{sym}", lambda s=sym: _em_index_daily(s), retries=1)
        if t is not None and not t.empty:
            t = _drop_partial_today(t, "date")
            if not t.empty:
                amounts[sym] = t.set_index("date")["amount"]
        v = safe_fetch(f"指数日K-新浪{sym}", lambda s=sym: _sina_index_daily(s), retries=1)
        if v is not None and not v.empty:
            v = _drop_partial_today(v, "date")
            if not v.empty:
                vols[sym] = v.set_index("date")["volume"]

    # 成交额
    if len(amounts) == 2:
        amt_ser = (amounts["sh000001"] + amounts["sz399106"]).dropna() / 1e8  # 亿元
        amt_ser.index = amt_ser.index.astype(str)
        out["A股成交额_亿"] = round(float(amt_ser.iloc[-1]), 2)
        out["_备注"] += f"A股数据日期={amt_ser.index[-1]}; "
    else:
        # 降级：腾讯指数实时行情的成交额（万元）。盘前=上一交易日全天，
        # 盘中=当日部分，收盘后=当日全天（备注标注）
        tx = safe_fetch("成交额-腾讯实时", _tx_index_amount_yi, retries=1)
        if tx:
            out["A股成交额_亿"] = round(tx, 2)
            t = datetime.now().time()
            if t < dtime(9, 30):
                tag = "上一交易日"
            elif t <= dtime(15, 0):
                tag = "当日盘中(未收盘)"
            else:
                tag = "当日"
            out["_备注"] += f"成交额来源=腾讯实时[{tag}]; "

    # 两市成交量（新浪，单位股 → 亿股）；新浪未更新目标日时用腾讯K线补
    if len(vols) == 2:
        vol_ser = (vols["sh000001"] + vols["sz399106"]).dropna() / 1e8
        vol_ser.index = vol_ser.index.astype(str)
        out["两市成交量_亿股"] = round(float(vol_ser.iloc[-1]), 2)
        if target_date and target_date not in vol_ser.index:
            tx_vols = {}
            for sym in ["sh000001", "sz399106"]:
                t = safe_fetch(f"指数日K-腾讯{sym}",
                               lambda s=sym: _tx_index_daily(s, count=10), retries=1)
                if t is None or t.empty:
                    continue
                t = _drop_partial_today(t, "date")
                hit = t[t["date"].astype(str) == target_date]
                if not hit.empty:
                    tx_vols[sym] = float(hit.iloc[0]["volume"]) * 100  # 手 → 股
            if len(tx_vols) == 2:
                out["两市成交量_亿股"] = round(sum(tx_vols.values()) / 1e8, 2)
                out["_备注"] += "成交量来源=腾讯K线; "

    # --- 主力净流入（东财大盘资金流，上证+深证） ---
    ff = safe_fetch("大盘资金流", lambda: _fund_flow(), retries=1)
    if ff is not None and not ff.empty:
        ff = _drop_partial_today(ff, "日期")
        if not ff.empty:
            last = ff.iloc[-1]
            sh = pd.to_numeric(last.get("上证-主力净流入-净额"), errors="coerce")
            sz = pd.to_numeric(last.get("深证-主力净流入-净额"), errors="coerce")
            if pd.notna(sh) and pd.notna(sz):
                out["主力净流入_亿"] = round((float(sh) + float(sz)) / 1e8, 2)
                out["_备注"] += f"资金流日期={last['日期']}; "
    return out


def _em_index_daily(symbol):
    import akshare as ak

    df = ak.stock_zh_index_daily_em(symbol=symbol)
    return df.tail(CROWDING_LOOKBACK + 30)


def _sina_index_daily(symbol):
    import akshare as ak

    return ak.stock_zh_index_daily(symbol=symbol).tail(CROWDING_LOOKBACK + 30)


def _fund_flow():
    import akshare as ak

    return ak.stock_market_fund_flow()


def _tx_index_amount_yi():
    """腾讯指数实时行情取两市成交额，返回合计（亿元）。

    v_s_sh000001 字段：[3]现价 [5]涨跌幅 [6]成交量(手) [7]成交额(万元)。
    """
    import requests

    r = requests.get("https://qt.gtimg.cn/q=s_sh000001,s_sz399106", timeout=10)
    r.encoding = "gbk"
    total = 0.0
    for line in r.text.split(";"):
        if "=" not in line or "~" not in line:
            continue
        fields = line.split("=", 1)[1].strip().strip('"').split("~")
        if len(fields) > 7 and fields[7]:
            total += float(fields[7])  # 万元
    if total <= 0:
        raise ValueError("腾讯行情无成交额")
    return total / 1e4  # → 亿元


def _spot_sina():
    """新浪全 A 列表分页抓取（东财全 A 快照被墙时的兜底）。

    返回与 _spot_em 兼容的最小列：代码 / 成交额（元）。
    每页 100 只按成交额降序，约 55 页，耗时 10~30 秒。
    """
    import requests

    url = ("https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
           "Market_Center.getHQNodeData")
    headers = {"Referer": "https://finance.sina.com.cn"}
    rows, page = [], 1
    while page <= 80:  # 安全上限
        r = requests.get(url, params={
            "page": str(page), "num": "100", "sort": "amount", "asc": "0",
            "node": "hs_a", "symbol": "", "_s_r_a": "page",
        }, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        if not data:
            break
        rows.extend(data)
        if len(data) < 100:
            break
        page += 1
        time.sleep(0.15)
    if not rows:
        raise ValueError("新浪全A列表为空")
    df = pd.DataFrame(rows)
    return pd.DataFrame({
        "代码": df["code"].astype(str),
        "成交额": pd.to_numeric(df["amount"], errors="coerce"),
    })


def collect_ratio():
    """6. 创业板指 / 中证红利 收盘价比率及变化

    两个数据源（新浪日K / 中证官网日K）收盘价发布时间可能不同，
    按两者共有的最新交易日对齐：当天数据都已发布即用当天，否则自动用上一交易日。
    """
    out = {"创业板指": MISSING, "中证红利": MISSING,
           "创业板红利比": MISSING, "比率较前日%": MISSING, "_note": ""}
    cyb = safe_fetch("创业板指", lambda: _sina_index_daily("sz399006"), retries=1)
    div = safe_fetch("中证红利", lambda: _csindex_daily("000922"), retries=1)
    if cyb is None or div is None or cyb.empty or div.empty:
        return out
    cyb = _drop_partial_today(cyb, "date")
    div = _drop_partial_today(div, "日期")
    if cyb.empty or div.empty:
        return out
    cyb_map = {str(r["date"]): float(r["close"]) for _, r in cyb.iterrows()}
    div_map = {str(r["日期"]): float(r["收盘"]) for _, r in div.iterrows()}
    common = sorted(set(cyb_map) & set(div_map))  # 升序
    if not common:
        out["_note"] = "创业板/红利无共同交易日"
        return out
    d_last = common[-1]
    out["创业板指"] = cyb_map[d_last]
    out["中证红利"] = div_map[d_last]
    out["创业板红利比"] = round(cyb_map[d_last] / div_map[d_last], 4)
    out["_note"] = f"比价日期={d_last}"
    if len(common) >= 2:
        d_prev = common[-2]
        r_prev = cyb_map[d_prev] / div_map[d_prev]
        if r_prev:
            out["比率较前日%"] = round((cyb_map[d_last] / div_map[d_last] / r_prev - 1) * 100, 2)
    return out


def _csindex_daily(symbol, days=30):
    import akshare as ak

    start = (pd.Timestamp.now() - pd.Timedelta(days=days)).strftime("%Y%m%d")
    end = datetime.now().strftime("%Y%m%d")
    return ak.stock_zh_index_hist_csindex(symbol=symbol, start_date=start, end_date=end)


def collect_us_bond():
    """8. 美 2/10/30 年期国债收益率 + 中债 10Y（供股债收益差使用）"""
    out = {"美债2Y%": MISSING, "美债10Y%": MISSING, "美债30Y%": MISSING,
           "中债10Y%": MISSING, "_cn10y": None}
    df = safe_fetch("国债收益率", _bond_rate, retries=1)
    if df is None or df.empty:
        return out
    last = df.iloc[-1]
    out["美债2Y%"] = pd.to_numeric(last["美国国债收益率2年"], errors="coerce")
    out["美债10Y%"] = pd.to_numeric(last["美国国债收益率10年"], errors="coerce")
    out["美债30Y%"] = pd.to_numeric(last["美国国债收益率30年"], errors="coerce")
    cn = pd.to_numeric(last["中国国债收益率10年"], errors="coerce")
    if pd.notna(cn):
        out["中债10Y%"] = float(cn)
        out["_cn10y"] = float(cn)
    return out


def collect_erp(cn10y):
    """10. 沪深300 股债收益差 = 盈利收益率(1/PE) - 10年期国债收益率

    同时记录沪深300近12个月收益率：中金图显示信贷脉冲约领先股指同比 6 个月，
    该字段用于事后对照。
    """
    out = {"沪深300_PE": MISSING, "沪深300盈利收益率%": MISSING, "股债收益差%": MISSING,
           "沪深300近12月%": MISSING, "_note": ""}
    df = safe_fetch("沪深300估值", lambda: _csindex_daily("000300", days=400), retries=1)
    if df is None or df.empty:
        return out
    last = df.iloc[-1]
    pe = pd.to_numeric(last.get("滚动市盈率"), errors="coerce")
    if pd.isna(pe) or not pe:
        return out
    out["沪深300_PE"] = float(pe)
    ey = 100.0 / float(pe)
    out["沪深300盈利收益率%"] = round(ey, 2)
    out["_note"] = f"沪深300估值日期={last['日期']}"
    if cn10y is not None:
        out["股债收益差%"] = round(ey - cn10y, 2)
    # 近 12 个月（约 250 个交易日）涨跌幅
    if len(df) > 250:
        base = pd.to_numeric(df["收盘"], errors="coerce").iloc[-251]
        cur = pd.to_numeric(df["收盘"], errors="coerce").iloc[-1]
        if base:
            out["沪深300近12月%"] = round((cur / base - 1) * 100, 2)
    return out


def _pick_col(df, candidates, label):
    """按候选列名挑出目标列，兼容数据源字段名调整。"""
    for c in candidates:
        if c in df.columns:
            return c
    raise KeyError(f"未找到{label}，候选列 {candidates} 均不存在，实际列为 {list(df.columns)}")


def collect_index_erp(cn10y):
    """新增1. A股主要股指 ERP = 盈利收益率(1/滚动PE) − 10年期国债收益率

    PE 取中证指数官网「滚动市盈率」，覆盖上证50/沪深300/中证500/中证1000。
    与既有「沪深300 股债收益差」同源，此处扩展为多指数横向对比。
    """
    out = {f"{name}_ERP%": MISSING for _, name in ERP_INDEXES}
    out["_note"] = ""
    if cn10y is None:
        out["_note"] = "ERP缺10Y国债基准"
        return out
    dates = []
    for symbol, name in ERP_INDEXES:
        df = safe_fetch(f"{name}估值", lambda s=symbol: _csindex_daily(s, days=400), retries=1)
        if df is None or df.empty:
            continue
        df = _drop_partial_today(df, "日期")
        if df.empty:
            continue
        last = df.iloc[-1]
        pe = pd.to_numeric(last.get("滚动市盈率"), errors="coerce")
        if pd.isna(pe) or not pe or pe <= 0:
            continue
        out[f"{name}_ERP%"] = round(100.0 / float(pe) - float(cn10y), 2)
        dates.append(f"{name}={last['日期']}")
    if dates:
        out["_note"] = "ERP估值日期:" + ",".join(dates)
    return out


def _stock_ebs_lg():
    import akshare as ak

    return ak.stock_ebs_lg()


def collect_ebs_spread():
    """新增2. 股债利差（乐咕乐股口径），含历史分位，用于判断股市贵不贵。"""
    out = {"股债利差%": MISSING, "股债利差分位%": MISSING, "_note": ""}
    df = safe_fetch("股债利差-乐咕", _stock_ebs_lg, retries=1)
    if df is None or df.empty:
        return out
    try:
        col = _pick_col(df, ["股债利差", "股债利差均线"], "股债利差")
    except KeyError as e:
        log.warning("股债利差字段异常：%s", str(e)[:120])
        return out
    s = pd.to_numeric(df[col], errors="coerce").dropna()
    if s.empty:
        return out
    out["股债利差%"] = round(float(s.iloc[-1]) * 100, 2)  # 接口返回小数
    if len(s) > 250:
        out["股债利差分位%"] = round(float((s < s.iloc[-1]).mean() * 100), 1)
    if "日期" in df.columns:
        out["_note"] = f"股债利差日期={df.loc[s.index[-1], '日期']}"
    return out


def _bond_china_yield(days=30):
    import akshare as ak

    start = (pd.Timestamp.now() - pd.Timedelta(days=days)).strftime("%Y%m%d")
    end = datetime.now().strftime("%Y%m%d")
    return ak.bond_china_yield(start_date=start, end_date=end)


def collect_rates_credit():
    """新增3+4. 国债收益率期限结构 + 信用利差（3Y AAA中票 − 3Y 国债）

    中债信息网该接口实际只提供国债 / AAA中票 / AAA商债三条曲线（无国开债），
    故信用利差基准改用同期限国债，口径已写入备注。
    """
    out = {"中债1Y%": MISSING, "中债3Y%": MISSING, "中债5Y%": MISSING,
           "中债10Y%": MISSING, "中债30Y%": MISSING,
           "信用利差_bp": MISSING, "_note": "", "_cn10y_fallback": None}
    df = safe_fetch("中债收益率曲线", _bond_china_yield, retries=1)
    if df is None or df.empty or "曲线名称" not in df.columns:
        return out
    names = df["曲线名称"].astype(str)
    gov = df[names.str.contains("国债", na=False)].sort_values("日期")
    mtn = df[names.str.contains(r"中短期票据.*AAA|AAA.*中短期票据", regex=True, na=False)]
    if gov.empty:
        out["_note"] = f"中债曲线异常:{list(names.unique())[:3]}"
        return out
    last = gov.iloc[-1]

    def num(row, col):
        return pd.to_numeric(row.get(col), errors="coerce")

    for col, key in [("1年", "中债1Y%"), ("3年", "中债3Y%"), ("5年", "中债5Y%"),
                     ("10年", "中债10Y%"), ("30年", "中债30Y%")]:
        v = num(last, col)
        if pd.notna(v):
            out[key] = round(float(v), 4)
    out["_cn10y_fallback"] = out["中债10Y%"]
    out["_note"] = f"国债曲线日期={last['日期']}"

    if not mtn.empty:
        m = mtn.sort_values("日期").iloc[-1]
        m3, g3 = num(m, "3年"), num(last, "3年")
        if pd.notna(m3) and pd.notna(g3):
            out["信用利差_bp"] = round((float(m3) - float(g3)) * 100, 1)
            out["_note"] += (f";信用利差=AAA中票3Y {float(m3):.4f}%−国债3Y {float(g3):.4f}%"
                             "(无国开曲线,用国债替代)")
        else:
            out["_note"] += ";AAA中票3Y缺失,信用利差未算"
    else:
        out["_note"] += ";AAA中票曲线缺失"
    return out


def _bond_cb_jsl():
    import akshare as ak

    return ak.bond_cb_jsl()


def _bond_zh_cov():
    import akshare as ak

    return ak.bond_zh_cov()


def _cb_premium_from_em():
    """东财可转债列表取全市场转股溢价率（主源）。

    仅保留「债现价>0 且溢价率非空」的在用转债；已退市/未上市的记录无有效价格。
    另剔除非正常值（|溢价率|>500%）以防数据源个别脏数据拉偏中位数。
    """
    df = safe_fetch("可转债-东财", _bond_zh_cov, retries=1)
    if df is None or df.empty:
        return None
    prem = pd.to_numeric(df.get("转股溢价率"), errors="coerce")
    px = pd.to_numeric(df.get("债现价"), errors="coerce")
    mask = prem.notna() & px.notna() & (px > 0) & (prem.abs() <= 500)
    s = prem[mask].dropna()
    return s if not s.empty else None


def _cb_premium_from_jsl():
    """集思录兜底。注意：游客态仅返回前 30 条且按溢价率升序，

    即「全市场最低溢价率的那 30 只」，中位数会严重低估，仅供主源失败时应急。
    """
    df = safe_fetch("可转债-集思录", _bond_cb_jsl, retries=1)
    if df is None or df.empty:
        return None, 0
    try:
        col = _pick_col(df, ["转股溢价率", "溢价率"], "转股溢价率")
    except KeyError as e:
        log.warning("转股溢价率字段异常：%s", str(e)[:120])
        return None, 0
    s = pd.to_numeric(df[col], errors="coerce").dropna()
    # 用 total 字段判断是否为截断样本（部分版本可拿到真实总数）
    return (s if not s.empty else None), len(s)


def collect_cb_premium():
    """新增5. 可转债转股溢价率（全市场中位数），判断转债贵不贵。

    优先东财全市场（约 300+ 只，含在价券），集思录仅作应急兜底并标注偏差风险。
    """
    out = {"转债溢价率%": MISSING, "转债样本数": MISSING, "_note": ""}

    s = _cb_premium_from_em()
    if s is not None and len(s) >= 50:
        out["转债溢价率%"] = round(float(s.median()), 2)
        out["转债样本数"] = int(len(s))
        out["_note"] = f"转债样本{len(s)}只(东财全市场)"
        return out

    s, n = _cb_premium_from_jsl()
    if s is not None:
        out["转债溢价率%"] = round(float(s.median()), 2)
        out["转债样本数"] = int(n)
        out["_note"] = f"转债样本{n}只(集思录游客态,仅最低档30只,中位数偏低)"
    return out


def _sw_fund_index_hist(symbol=SW_FUND_INDEX):
    """申万基金指数历史行情。

    直连申万接口并关闭证书校验（akshare 内置 http 客户端在本机报
    CERTIFICATE_VERIFY_FAILED），失败时由调用方回落 akshare 官方函数。
    """
    import requests
    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    r = requests.post(
        "https://www.swsresearch.com/insWechatSw/fundIndex/getFundKChartData",
        json={"swIndexCode": symbol, "type": "DAY"},
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                 "Referer": "https://www.swsresearch.com/"},
        verify=False, timeout=30,
    )
    r.raise_for_status()
    data = r.json()["data"]
    if not data:
        raise ValueError("申万基金指数返回空数据")
    df = pd.DataFrame(data).rename(columns={"bargaindate": "日期", "closeindex": "收盘指数"})
    return df[["日期", "收盘指数"]]


def collect_fund_rolling():
    """新增6. 偏债混合基金指数滚动 3 年年化收益 + 历史分位（均值回归逻辑）。"""
    out = {"偏债混合3年年化%": MISSING, "偏债混合3年分位%": MISSING, "_note": ""}
    df = safe_fetch("偏债混合基金指数", _sw_fund_index_hist, retries=1)

    def _ak_fund():
        import akshare as ak

        return ak.index_hist_fund_sw(symbol=SW_FUND_INDEX, period="day")

    if df is None or df.empty:
        df = safe_fetch("偏债混合基金指数-akshare兜底", _ak_fund, retries=1)
    if df is None or df.empty:
        return out
    try:
        col = _pick_col(df, ["收盘指数", "收盘"], "基金指数收盘价")
    except KeyError as e:
        log.warning("基金指数字段异常：%s", str(e)[:120])
        return out
    s = pd.to_numeric(df[col], errors="coerce")
    s.index = pd.to_datetime(df["日期"], errors="coerce")
    s = s.dropna().sort_index()
    s = s[~s.index.isna()]
    window = 756  # 3 年 ≈ 756 个交易日
    if len(s) <= window:
        out["_note"] = f"基金指数仅{len(s)}条,不足3年"
        return out
    ann = ((s / s.shift(window)) ** (1 / 3) - 1).dropna()
    if ann.empty:
        return out
    out["偏债混合3年年化%"] = round(float(ann.iloc[-1]) * 100, 2)
    out["偏债混合3年分位%"] = round(float((ann < ann.iloc[-1]).mean() * 100), 1)
    out["_note"] = (f"基金指数日期={s.index[-1].date()},申万{SW_FUND_INDEX}"
                    "(非Wind 885003.WI)")
    return out


def collect_m2():
    """11. 最新 M2 总量、同比、环比"""
    out = {"M2总量_万亿": MISSING, "M2同比%": MISSING, "M2环比%": MISSING, "_note": ""}
    df = safe_fetch("M2货币供应", _money_supply, retries=1)
    if df is None or df.empty:
        return out
    last = df.iloc[0]  # 接口按时间倒序
    qty = pd.to_numeric(last["货币和准货币(M2)-数量(亿元)"], errors="coerce")
    if pd.notna(qty):
        out["M2总量_万亿"] = round(float(qty) / 1e4, 2)
    out["M2同比%"] = pd.to_numeric(last["货币和准货币(M2)-同比增长"], errors="coerce")
    out["M2环比%"] = pd.to_numeric(last["货币和准货币(M2)-环比增长"], errors="coerce")
    out["_note"] = f"M2月份={last['月份']}"
    return out


def collect_top5_share():
    """12. 大盘拥挤度 + TMT 行业拥挤度（口径参考用户 a_share_analyzer.py）

    - 大盘拥挤度：成交额排名前 5% 个股的成交额占全部 A 股比重
    - TMT 拥挤度：TMT（科技/传媒/通信，清单见 TMT_CSV）成交额占全部 A 股比重
    - TMT 在前 5% 中的份额：前 5% 成交额里 TMT 所占比例
    数据源：东财全 A 快照（约 5400 只）。快照口径随运行时间自动切换：
    盘前（9:30 前）= 上一交易日收盘完整数据；盘中 = 当日实时（未收盘）；
    15:00 收盘后 = 当日收盘完整数据。备注中会标注口径。
    """
    out = {"大盘拥挤度%": MISSING, "TMT拥挤度%": MISSING, "TMT在前5%占比%": MISSING,
           "_note": ""}
    df = safe_fetch("全A快照-东财", _spot_em, retries=1)
    if df is None or df.empty or "成交额" not in df.columns:
        df = safe_fetch("全A快照-新浪兜底", _spot_sina, retries=1)
        if df is not None and not df.empty:
            out["_note"] = "快照来源=新浪; "
    if df is None or df.empty or "成交额" not in df.columns:
        return out
    d = df.dropna(subset=["成交额"])
    d = d[d["成交额"] > 0]
    if len(d) < 100:
        return out
    n = len(d)
    k = max(1, int(round(n * 0.05)))
    d_sorted = d.sort_values("成交额", ascending=False)
    top = d_sorted.head(k)
    top_sum = float(top["成交额"].sum())
    total = float(d["成交额"].sum())
    if total <= 0:
        return out
    out["大盘拥挤度%"] = round(top_sum / total * 100, 2)

    # TMT 拥挤度
    try:
        tmt_codes = pd.read_csv(TMT_CSV, encoding="utf-8-sig", dtype={"code": str})["code"]
        tmt_codes = set(tmt_codes.dropna().str.strip()) - {""}
    except Exception as e:
        log.warning("TMT 清单读取失败 [%s]: %s", TMT_CSV, str(e)[:100])
        tmt_codes = None
    if tmt_codes:
        code_col = "代码" if "代码" in d.columns else d.columns[0]
        d_codes = d[code_col].astype(str).str.strip()
        tmt_amt = float(d.loc[d_codes.isin(tmt_codes), "成交额"].sum())
        out["TMT拥挤度%"] = round(tmt_amt / total * 100, 2)
        tmt_top_amt = float(top.loc[top[code_col].astype(str).str.strip().isin(tmt_codes),
                                    "成交额"].sum())
        out["TMT在前5%占比%"] = round(tmt_top_amt / top_sum * 100, 2) if top_sum else MISSING
        out["_note"] = f"样本{n}只/前{k}只/TMT命中{int(d_codes.isin(tmt_codes).sum())}只"

    t = datetime.now().time()
    if dtime(9, 30) <= t <= dtime(15, 0):
        out["_note"] += "(当日盘中数据,未收盘)"
    return out


def collect_credit_impulse():
    """13. 信贷脉冲 = (信贷 TTM 增量 - 上年同期 TTM 增量) / GDP TTM

    信贷口径：新增人民币贷款（社融接口更新滞后，故用贷款口径，口径可在函数内切换）。
    """
    out = {"信贷脉冲%": MISSING, "新增贷款TTM_万亿": MISSING, "_note": ""}
    loan = safe_fetch("人民币贷款", _rmb_loan, retries=1)
    gdp = safe_fetch("GDP", _gdp, retries=1)
    if loan is None or loan.empty or gdp is None or gdp.empty:
        return out
    s = loan.sort_values("月份").set_index("月份")["新增人民币贷款-总额"].astype(float)
    if len(s) < 25:
        return out
    ttm = s.rolling(12).sum()
    cur, prev = float(ttm.iloc[-1]), float(ttm.iloc[-13])
    out["新增贷款TTM_万亿"] = round(cur / 1e4, 2)
    gdp_ttm = _gdp_ttm(gdp)
    if gdp_ttm:
        out["信贷脉冲%"] = round((cur - prev) / gdp_ttm * 100, 2)
        out["_note"] = f"贷款TTM截至{s.index[-1]},GDP_TTM={gdp_ttm/1e4:.1f}万亿"
    return out


def _gdp_ttm(gdp):
    """由季度累计 GDP 还原单季值，返回最近 4 个单季之和（亿元）"""
    import re

    rows = []
    for _, r in gdp.iterrows():
        m = re.match(r"(\d{4})年第1(?:-(\d))?季度", str(r["季度"]))
        if not m:
            continue
        y, q = int(m.group(1)), int(m.group(2) or 1)
        rows.append((y, q, float(r["国内生产总值-绝对值"])))
    if len(rows) < 8:
        return None
    df = pd.DataFrame(rows, columns=["year", "q", "cum"]).sort_values(["year", "q"])
    df["single"] = df.groupby("year")["cum"].diff()
    df.loc[df["q"] == 1, "single"] = df.loc[df["q"] == 1, "cum"]
    singles = df.dropna(subset=["single"])["single"].tolist()
    if len(singles) < 4:
        return None
    return sum(singles[-4:])


def _money_supply():
    import akshare as ak

    return ak.macro_china_money_supply()


def _spot_em():
    import akshare as ak

    return ak.stock_zh_a_spot_em()


def _rmb_loan():
    import akshare as ak

    return ak.macro_rmb_loan()


def _gdp():
    import akshare as ak

    return ak.macro_china_gdp()


def _bond_rate():
    import akshare as ak

    start = (pd.Timestamp.now() - pd.Timedelta(days=10)).strftime("%Y%m%d")
    return ak.bond_zh_us_rate(start_date=start)


def collect_all():
    """汇总采集全部指标，返回 (记录 dict, 缺失项列表)

    数据日期 = A 股最近一个已收盘交易日：当天收盘后运行记当天，
    盘前/盘中运行自动记上一交易日。逐项指标再按各自数据源最新可得日期取数。
    """
    trade_date = _target_trade_date()
    row = {"数据日期": trade_date}
    parts = [
        collect_margin(),
        collect_oil_gold(),
        collect_gold_cot(),
        collect_global_indices(),
        collect_a_share(target_date=trade_date),
        collect_ratio(),
    ]
    yields = collect_us_bond()
    parts.append(yields)
    parts.append(collect_erp(yields.get("_cn10y")))

    # 新增六项：多指数 ERP / 股债利差 / 国债收益率+信用利差 / 转债溢价率 / 偏债混合滚动年化
    rates = collect_rates_credit()
    parts.append(rates)
    cn10y = yields.get("_cn10y")
    if cn10y is None:
        cn10y = rates.get("_cn10y_fallback")  # 中债曲线兜底基准
    parts.append(collect_index_erp(cn10y))
    parts.append(collect_ebs_spread())
    parts.append(collect_cb_premium())
    parts.append(collect_fund_rolling())
    parts += [collect_m2(), collect_top5_share(), collect_credit_impulse()]

    notes = []
    for p in parts:
        note = p.pop("_note", "") or p.pop("_备注", "")
        p.pop("_cn10y", None)
        p.pop("_cn10y_fallback", None)
        if note:
            notes.append(str(note).strip("; "))
        row.update(p)

    row["备注"] = "; ".join(notes)
    if trade_date != date.today().strftime("%Y-%m-%d"):
        row["备注"] = (row["备注"] + "; " if row["备注"] else "") + \
            "今日数据未发布,取最近完整交易日"
    row["采集时间"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    missing = [k for k, v in row.items() if v is MISSING and not k.startswith("_")]
    row = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in row.items()}
    return row, missing


# --------------------------- CSV 落盘 ---------------------------

CSV_COLUMNS = [
    # 标识
    "数据日期",
    # A股：资金与拥挤度
    "两融余额_亿", "两融余额变动_亿",
    "A股成交额_亿", "主力净流入_亿",
    "大盘拥挤度%", "TMT拥挤度%", "TMT在前5%占比%",
    "两市成交量_亿股",
    # A股：比价
    "创业板指", "中证红利", "创业板红利比", "比率较前日%",
    # 估值与流动性
    "沪深300_PE", "沪深300盈利收益率%", "中债10Y%", "股债收益差%",
    "沪深300近12月%",
    "M2总量_万亿", "M2同比%", "M2环比%",
    "信贷脉冲%", "新增贷款TTM_万亿",
    # 新增：主要股指 ERP 与股债性价比
    "上证50_ERP%", "沪深300_ERP%", "中证500_ERP%", "中证1000_ERP%",
    "股债利差%", "股债利差分位%",
    # 新增：利率绝对水平与信用拥挤度
    "中债1Y%", "中债3Y%", "中债5Y%", "中债30Y%", "信用利差_bp",
    # 新增：转债估值与偏债混合基金（均值回归）
    "转债溢价率%", "转债样本数", "偏债混合3年年化%", "偏债混合3年分位%",
    # 海外指数与期货
    "标普500涨跌幅%", "纳指涨跌幅%", "纳指期货_点", "纳指期货涨跌幅%",
    "道指涨跌幅%", "日经225_点", "日经225涨跌幅%",
    "韩国KOSPI_点", "韩国KOSPI涨跌幅%",
    # 商品
    "布油_美元", "布油涨跌幅%", "WTI_美元", "WTI涨跌幅%",
    # 贵金属（价格 + CFTC 多空持仓）
    "COMEX黄金_美元", "黄金涨跌幅%", "COMEX白银_美元", "白银涨跌幅%", "金银比",
    "黄金COT报告日", "黄金COT多头", "黄金COT空头", "黄金COT净多",
    "黄金COT空头全历史分位%", "黄金COT空头周变化", "黄金COT净多周变化",
    # 利率
    "美债2Y%", "美债10Y%", "美债30Y%",
    # 备注
    "备注", "采集时间",
]


def save_to_csv(row):
    """按日期 upsert 到唯一 CSV；文件被占用时重试，仍失败则另存副本不丢数据"""
    df_new = pd.DataFrame([row])
    df_all = df_new
    if CSV_PATH.exists():
        try:
            df_old = pd.read_csv(CSV_PATH, dtype={"数据日期": str})
            df_old = df_old[df_old["数据日期"] != row["数据日期"]]
            df_all = pd.concat([df_old, df_new], ignore_index=True)
        except Exception as e:
            log.warning("读取旧 CSV 失败（%s），按新建处理", type(e).__name__)
            df_all = df_new
    df_all = df_all[[c for c in CSV_COLUMNS if c in df_all.columns]]

    for attempt in range(3):
        try:
            df_all.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
            log.info("已写入 %s（共 %d 行）", CSV_PATH, len(df_all))
            return
        except PermissionError:
            if attempt < 2:
                time.sleep(3)
    fallback = BASE_DIR / f"market_data_{row['数据日期']}.csv"
    df_all.to_csv(fallback, index=False, encoding="utf-8-sig")
    log.warning("CSV 被占用（可能正在 Excel 中打开），已另存为 %s；关闭占用程序后重跑可写回主文件",
                fallback.name)


# --------------------------- 报表图片 ---------------------------

def _report_sections(row):
    """把一行数据整理成分组报表结构（钉钉表格与图片共用）。

    返回 [(组名, 表头, 行列表, 涨跌着色列号集合)]，
    行内缺失值统一 '--'，着色列按前缀 +/- 红涨绿跌。
    每组不超过 3 列，保证手机端表格不被挤断。
    """
    def f(key, nd=2, suffix=""):
        return fmt(row.get(key), nd, suffix)

    def s(key, nd=2, suffix="%"):
        return sign(row.get(key), nd, suffix)

    tmt_top = fmt(row.get("TMT在前5%占比%"), 1)
    m2_amt = fmt(row.get("M2总量_万亿"))
    m2_yoy = fmt(row.get("M2同比%"))
    m2_mom = fmt(row.get("M2环比%"))
    cn10y = fmt(row.get("中债10Y%"))
    pe = fmt(row.get("沪深300_PE"))
    ey = fmt(row.get("沪深300盈利收益率%"))

    sections = [
        (f"A股 · {row['数据日期']}",
         ["指标", "数值", "说明"],
         [
             ["两市成交额", f("A股成交额_亿", 0, " 亿"), "沪深合计"],
             ["两市成交量", f("两市成交量_亿股", 0, " 亿股"), "沪深合计"],
             ["主力净流入", s("主力净流入_亿", 0, " 亿"), "上证+深证"],
             ["两融余额", f("两融余额_亿", 0, " 亿"), f"沪深北（{s('两融余额变动_亿', 0, ' 亿')}）"],
             ["大盘拥挤度", f"{fmt(row.get('大盘拥挤度%'), 1)}%", "前5%成交额占比"],
             ["TMT拥挤度", f"{fmt(row.get('TMT拥挤度%'), 1)}%", f"前5%中占 {tmt_top}%"],
             ["创业板/中证红利", f("创业板红利比", 4), s("比率较前日%")],
         ],
         {2}),
        ("估值与流动性",
         ["指标", "数值", "说明"],
         [
             ["沪深300 PE(TTM)", pe, f"盈利收益率 {ey}%"],
             ["股债收益差", f"{fmt(row.get('股债收益差%'))}%", f"中债10Y {cn10y}%"],
             ["M2 总量", f"{m2_amt} 万亿", f"同比 {m2_yoy}%/环比 {m2_mom}%"],
             ["信贷脉冲", f"{fmt(row.get('信贷脉冲%'))}%", "贷款TTM同比/GDP"],
         ],
         set()),  # 存量/水平值，不做涨跌着色
        ("股债性价比（ERP）",
         ["指数", "ERP", "说明"],
         [
             ["上证50", f("上证50_ERP%", 2, "%"), "1/PE−10Y国债"],
             ["沪深300", f("沪深300_ERP%", 2, "%"), "1/PE−10Y国债"],
             ["中证500", f("中证500_ERP%", 2, "%"), "1/PE−10Y国债"],
             ["中证1000", f("中证1000_ERP%", 2, "%"), "1/PE−10Y国债"],
             ["股债利差(乐咕)", f("股债利差%", 2, "%"),
              f"历史分位 {fmt(row.get('股债利差分位%'), 1)}%"],
         ],
         set()),
        ("转债与偏债混合",
         ["指标", "数值", "说明"],
         [
             ["转债转股溢价率", f("转债溢价率%", 2, "%"),
              f"中位数 / 样本 {fmt(row.get('转债样本数'), 0)} 只"],
             ["偏债混合滚动3年年化", f("偏债混合3年年化%", 2, "%"),
              f"历史分位 {fmt(row.get('偏债混合3年分位%'), 1)}%"],
         ],
         set()),
        ("贵金属 · 黄金/白银/金银比",
         ["指标", "价格/持仓", "涨跌幅 / 说明"],
         [
             ["COMEX 黄金", f("COMEX黄金_美元"), s("黄金涨跌幅%")],
             ["COMEX 白银", f("COMEX白银_美元"), s("白银涨跌幅%")],
             ["金银比", f("金银比"), "金价÷银价"],
             ["COT 多头(非商业)", f("黄金COT多头", 0), "手 · CFTC/COMEX"],
             ["COT 空头(非商业)", f("黄金COT空头", 0),
              f"手 · 全历史分位 {fmt(row.get('黄金COT空头全历史分位%'), 1)}%"],
             ["COT 净多(非商业)", f("黄金COT净多", 0),
              f"手 · 周变 {sign(row.get('黄金COT净多周变化'), 0)}"],
             ["COT 报告日", str(row.get("黄金COT报告日") or "--"), "CFTC周报·周五发布"],
         ],
         {2}),
        ("海外与商品",
         ["指标", "价格", "涨跌幅"],
         [
             ["布伦特原油", f("布油_美元"), s("布油涨跌幅%")],
             ["WTI 原油", f("WTI_美元"), s("WTI涨跌幅%")],
             ["纳指期货(连续)", f("纳指期货_点"), s("纳指期货涨跌幅%")],
             ["标普500", "—", s("标普500涨跌幅%")],
             ["纳斯达克", "—", s("纳指涨跌幅%")],
             ["道琼斯", "—", s("道指涨跌幅%")],
             ["日经225", f("日经225_点"), s("日经225涨跌幅%")],
             ["韩国KOSPI", f("韩国KOSPI_点"), s("韩国KOSPI涨跌幅%")],
         ],
         {2}),
        ("利率",
         ["品种", "数值"],
         [
             ["美债 2Y", f("美债2Y%", 2, "%")],
             ["美债 10Y", f("美债10Y%", 2, "%")],
             ["美债 30Y", f("美债30Y%", 2, "%")],
             ["中债 1Y", f("中债1Y%", 2, "%")],
             ["中债 3Y", f("中债3Y%", 2, "%")],
             ["中债 5Y", f("中债5Y%", 2, "%")],
             ["中债 10Y", f("中债10Y%", 2, "%")],
             ["中债 30Y", f("中债30Y%", 2, "%")],
             ["信用利差(AAA中票3Y−国债3Y)", f("信用利差_bp", 1, " bp")],
         ],
         set()),
    ]
    return sections


def save_report_image(row, missing):
    """渲染报表为 PNG 保存到脚本目录，返回文件路径。"""
    import textwrap

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
    plt.rcParams["axes.unicode_minus"] = False

    UP, DOWN, HEADER, ZEBRA, TEXT = "#c0392b", "#1e8449", "#2f5597", "#eef3f9", "#1a1a1a"
    sections = _report_sections(row)

    n_rows = sum(len(rows) + 1 for _, _, rows, _ in sections)
    # 画布高度按行数伸缩：标题区 + 表格行 + 组间距 + 页脚余量
    fig_h = 1.1 + n_rows * 0.26 + len(sections) * 0.30 + 1.55
    fig = plt.figure(figsize=(9.4, fig_h))
    ax = fig.add_axes([0, 0, 1, 1])  # 坐标轴铺满画布，便于用比例排版
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    row_h = 0.26 / fig_h          # 单行表格占画布比例
    sec_gap = 0.16 / fig_h        # 组间距
    title_h = 0.34 / fig_h        # 组标题行高

    # 顶部标题
    y = 1 - 0.10 / fig_h
    ax.text(0.025, y, f"市场数据速览 {row['数据日期']}",
            fontsize=16, fontweight="bold", color=HEADER, va="top")
    ax.text(0.975, y - 0.01 / fig_h, f"采集时间 {row['采集时间']}",
            fontsize=8.5, color="#888888", ha="right", va="top")
    y -= 0.62 / fig_h

    for title, headers, rows, color_cols in sections:
        # 组标题（va=bottom，位于表格上方，避免与表头重叠）
        ax.text(0.025, y, "▎" + title, fontsize=12, fontweight="bold",
                color=HEADER, va="bottom")
        y -= title_h
        table_h = row_h * (len(rows) + 1)
        tab = ax.table(cellText=rows, colLabels=headers,
                       bbox=[0.025, y - table_h, 0.95, table_h],
                       cellLoc="left", edges="closed")
        tab.auto_set_font_size(False)
        tab.set_fontsize(10)
        for (r, c), cell in tab.get_celld().items():
            cell.set_edgecolor("#c9d2dc")
            cell.set_linewidth(0.6)
            if r == 0:  # 表头：蓝底白字
                cell.set_facecolor(HEADER)
                cell.set_text_props(color="white", fontweight="bold",
                                    ha="right" if c > 0 else "left")
            else:
                cell.set_facecolor(ZEBRA if r % 2 == 0 else "white")
                txt = rows[r - 1][c] if c < len(rows[r - 1]) else ""
                color = TEXT
                if c in color_cols and txt and not txt.startswith(("--", "—")):
                    if txt.startswith("+"):
                        color = UP
                    elif txt.startswith(("-", "−")):
                        color = DOWN
                cell.set_text_props(color=color,
                                    fontweight="bold" if c == 0 else "normal",
                                    ha="right" if c > 0 else "left")
        y -= table_h + sec_gap

    # 页脚（长文本自动换行）
    foot = []
    if missing:
        foot.append(f"缺失：{'、'.join(missing)}")
    if row.get("备注"):
        foot.extend(textwrap.wrap(f"注：{row['备注']}", width=68))
    foot.append("数据来源：沪深北交易所 / 中证指数 / 新浪 / 腾讯 / 东方财富（akshare）")
    ax.text(0.025, y + 0.04 / fig_h, "\n".join(foot), fontsize=8, color="#777777",
            va="top", linespacing=1.6)

    out = BASE_DIR / f"market_brief_{row['数据日期']}.png"
    fig.savefig(out, dpi=150, facecolor="white")
    plt.close(fig)
    return out


# --------------------------- 微信推送 ---------------------------

def build_message(row, missing):
    d = row["数据日期"]
    lines = [f"## 市场数据速览 {d}", ""]

    lines += [
        f"**A股（{d}）**",
        "| 指标 | 数值 |",
        "| --- | --- |",
        f"| 两市成交额 | {fmt(row['A股成交额_亿'], 0, ' 亿')} |",
        f"| 两市成交量 | {fmt(row['两市成交量_亿股'], 0, ' 亿股')} |",
        f"| 主力净流入 | {fmt(row['主力净流入_亿'], 0, ' 亿')} |",
        f"| 两融余额（沪深北） | {fmt(row.get('两融余额_亿'), 0, ' 亿')}（{sign(row.get('两融余额变动_亿'), 0, ' 亿')}） |",
        f"| 大盘拥挤度（前5%成交额占比） | {fmt(row.get('大盘拥挤度%'), 1)}% |",
        f"| TMT拥挤度（占全A成交额） | {fmt(row.get('TMT拥挤度%'), 1)}%（在前5%中占 {fmt(row.get('TMT在前5%占比%'), 1)}%） |",
        f"| 创业板指/中证红利 | {fmt(row['创业板红利比'], 4)}（{sign(row['比率较前日%'])}%） |",
        "",
        "**估值与流动性**",
        "| 指标 | 数值 |",
        "| --- | --- |",
        f"| 沪深300 PE(TTM) | {fmt(row.get('沪深300_PE'))} |",
        f"| 股债收益差（1/PE-10Y国债） | {fmt(row.get('股债收益差%'))}%（中债10Y {fmt(row.get('中债10Y%'))}%） |",
        f"| 股债利差（乐咕） | {fmt(row.get('股债利差%'))}%（历史分位 {fmt(row.get('股债利差分位%'), 1)}%） |",
        f"| 主要股指 ERP | 上证50 {fmt(row.get('上证50_ERP%'))}% / 沪深300 {fmt(row.get('沪深300_ERP%'))}% / 中证500 {fmt(row.get('中证500_ERP%'))}% / 中证1000 {fmt(row.get('中证1000_ERP%'))}% |",
        f"| M2 总量 | {fmt(row.get('M2总量_万亿'))} 万亿（同比 {fmt(row.get('M2同比%'))}%，环比 {fmt(row.get('M2环比%'))}%） |",
        f"| 信贷脉冲 | {fmt(row.get('信贷脉冲%'))}% |",
        "",
        "**转债与偏债混合**",
        "| 指标 | 数值 |",
        "| --- | --- |",
        f"| 转债转股溢价率（中位数） | {fmt(row.get('转债溢价率%'))}%（样本 {fmt(row.get('转债样本数'), 0)} 只） |",
        f"| 偏债混合滚动3年年化 | {fmt(row.get('偏债混合3年年化%'))}%（历史分位 {fmt(row.get('偏债混合3年分位%'), 1)}%） |",
        "",
    ]
    lines += [
        "**贵金属 · 黄金/白银/金银比**",
        "| 指标 | 数值 | 说明 |",
        "| --- | --- | --- |",
        f"| COMEX 黄金 | {fmt(row['COMEX黄金_美元'])} | {sign(row['黄金涨跌幅%'])}% |",
        f"| COMEX 白银 | {fmt(row.get('COMEX白银_美元'))} | {sign(row.get('白银涨跌幅%'))}% |",
        f"| 金银比 | {fmt(row.get('金银比'))} | 金价÷银价 |",
        f"| COT 多头(非商业) | {fmt(row.get('黄金COT多头'), 0)} | 手 · CFTC/COMEX |",
        f"| COT 空头(非商业) | {fmt(row.get('黄金COT空头'), 0)} | 手 · 全历史分位 {fmt(row.get('黄金COT空头全历史分位%'), 1)}% |",
        f"| COT 净多(非商业) | {fmt(row.get('黄金COT净多'), 0)} | 手 · 周变 {sign(row.get('黄金COT净多周变化'), 0)} |",
        f"| COT 报告日 | {row.get('黄金COT报告日') or '--'} | CFTC周报·周五发布 |",
        "",
        "**海外与商品**",
        "| 指标 | 数值 | 涨跌幅 |",
        "| --- | --- | --- |",
        f"| 布伦特原油 | {fmt(row['布油_美元'])} | {sign(row['布油涨跌幅%'])}% |",
        f"| WTI 原油 | {fmt(row['WTI_美元'])} | {sign(row['WTI涨跌幅%'])}% |",
        f"| 标普500 | - | {sign(row['标普500涨跌幅%'])}% |",
        f"| 纳斯达克 | - | {sign(row['纳指涨跌幅%'])}% |",
        f"| 小型纳指期货(连续) | {fmt(row.get('纳指期货_点'))} | {sign(row.get('纳指期货涨跌幅%'))}% |",
        f"| 道琼斯 | - | {sign(row['道指涨跌幅%'])}% |",
        f"| 日经225 | {fmt(row.get('日经225_点'))} | {sign(row['日经225涨跌幅%'])}% |",
        f"| 韩国KOSPI | {fmt(row.get('韩国KOSPI_点'))} | {sign(row['韩国KOSPI涨跌幅%'])}% |",
        f"| 美债 2Y | {fmt(row['美债2Y%'])}% | - |",
        f"| 美债 10Y | {fmt(row['美债10Y%'])}% | - |",
        f"| 美债 30Y | {fmt(row['美债30Y%'])}% | - |",
        f"| 中债 1Y/3Y/5Y | {fmt(row.get('中债1Y%'))}% / {fmt(row.get('中债3Y%'))}% / {fmt(row.get('中债5Y%'))}% | - |",
        f"| 中债 10Y/30Y | {fmt(row.get('中债10Y%'))}% / {fmt(row.get('中债30Y%'))}% | - |",
        f"| 信用利差(AAA中票3Y−国债3Y) | {fmt(row.get('信用利差_bp'), 1)} bp | - |",
        "",
    ]
    if row.get("备注"):
        lines += [f"> 注：{row['备注']}", ""]
    if missing:
        lines += [f"> ⚠️ 本次缺失：{'、'.join(missing)}", ""]
    lines += [f"数据来源：交易所/中证指数/新浪/东方财富（akshare）、CFTC 黄金持仓（COMEX），采集时间 {row['采集时间']}"]
    return "\n".join(lines)


def build_dingtalk_message(row, missing, style=DINGTALK_STYLE):
    """生成钉钉 markdown 消息：四组表格 + 脚注（默认 Markdown 管道表格）"""
    try:
        from dingtalk_utils import render_sections
    except ImportError:
        log.error("找不到 dingtalk_utils.py，请确认它在上一级 notice 目录")
        return None

    body = render_sections(_report_sections(row), style=style)
    parts = [f"#### 市场数据速览 · {row['数据日期']}", body]

    if missing:
        parts.append(f"**本次缺失**：{'、'.join(missing)}")
    if row.get("备注"):
        parts.append(f"**口径**：{row['备注']}")
    parts.append(f"**采集时间**：{row['采集时间']}")
    return "\n\n".join(parts)


def send_dingtalk(title, text):
    """推送到钉钉群"""
    if not text:
        return False
    try:
        from dingtalk_utils import DingTalkNotifier
    except ImportError:
        log.error("找不到 dingtalk_utils.py（应在上一级 notice 目录），跳过钉钉推送")
        return False
    ok = DingTalkNotifier().send_markdown(title, text, at_all=False)
    if ok:
        log.info("钉钉推送成功")
    else:
        log.warning("钉钉推送失败（详见上方日志）")
    return ok


def send_wechat(title, desp):
    """通过 Server酱 推送到微信"""
    if SENDKEY.startswith("请替换"):
        log.error("未配置 SENDKEY，跳过推送。请到 https://sct.ftqq.com/ 获取后填入脚本顶部。")
        return False
    try:
        from serverchan_sdk import sc_send

        response = sc_send(SENDKEY, title, desp, {"tags": SC_TAGS})
        log.info("Server酱 返回：%s", str(response)[:200])
        return True
    except Exception as e:
        log.warning("推送失败：%s: %s", type(e).__name__, str(e)[:150])
        return False


# --------------------------- 主流程 ---------------------------

def run_job(send=True, wechat=False, image=False, style=DINGTALK_STYLE):
    log.info("开始采集…")
    row, missing = collect_all()
    save_to_csv(row)
    log.info("采集完成，缺失项：%s", "、".join(missing) if missing else "无")

    # 报表图片（可选，默认不生成 —— 钉钉改用表格形式）
    if image:
        try:
            img = save_report_image(row, missing)
            log.info("报表图片已生成：%s", img)
        except Exception as e:
            log.warning("报表图片生成失败：%s: %s", type(e).__name__, str(e)[:150])

    if send:
        title = f"市场数据速览 {row['数据日期']}" + ("（部分缺失）" if missing else "")
        send_dingtalk(title, build_dingtalk_message(row, missing, style))
        if wechat:
            send_wechat(title, build_message(row, missing))


def main():
    args = sys.argv[1:]

    def has(*flags):
        return any(f in args for f in flags)

    def opt(name, default=None):
        """取 --name value 形式的值"""
        if name in args:
            i = args.index(name)
            if i + 1 < len(args):
                return args[i + 1]
        return default

    style = opt("--style", DINGTALK_STYLE)
    if style not in ("html", "md", "align"):
        log.warning("未知表格风格 %s，回退到 html", style)
        style = "html"

    if has("--daemon", "--schedule", "-d"):
        log.info("常驻模式启动：每天 %s 采集并推送钉钉（Ctrl+C 退出）", RUN_AT)
        schedule.every().day.at(RUN_AT).do(
            run_job, send=True, wechat=has("--wechat"), image=has("--image"), style=style
        )
        while True:
            schedule.run_pending()
            time.sleep(30)

    # 默认行为：立即执行一次（--now 保留为兼容写法，可省略）
    run_job(send=not has("--no-send"), wechat=has("--wechat"),
            image=has("--image"), style=style)


if __name__ == "__main__":
    main()
