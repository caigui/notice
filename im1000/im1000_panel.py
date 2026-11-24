#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中证1000股指期权 (CFFEX MO) 衍生指标面板 —— 全免费数据源版
=============================================================

复现两张图:
  图1  波动率指数 = 30天恒定到期平值隐含波动率 (ATM IV%), 右轴叠加中证1000指数(000852)
  图2  认沽认购比 PCR = 认沽持仓量 / 认购持仓量 (全合约, 未取倒数, 不叠加指数)

数据源 (全部免费, 无需 token / 积分)
-------------------------------------
  期权逐合约行情  中金所官网「历史数据下载」月度 ZIP (最原始、最权威)
                  http://www.cffex.com.cn/sj/historysj/{YYYYMM}/zip/{YYYYMM}.zip
                  包内每个交易日一个 CSV (GBK), 字段含 今结算/成交量/持仓量/Delta
  中证1000指数    东方财富 JSON 接口 (requests 直连); 备用 AkShare 新浪/东财
  Shibor 3M       AkShare  macro_china_shibor_all()  (可选); 缺失自动回退固定值
  交易日历        从 ZIP 内文件名直接取交易日; 到期日顺延用 AkShare 交易日历 (可选)

快速开始
--------
  pip install pandas numpy matplotlib requests
  # akshare 可选: 仅用于 Shibor 3M 与到期日顺延; 不装也能跑 (利率回退 FIXED_RF)
  python im1000_panel.py --all       # 首次全量: 2022-07-22 至今 (约 50 个月 ZIP, ~20MB)
  python im1000_panel.py --update    # 每日增量: 只重下当月, 其余月份走本地缓存
  python im1000_panel.py --calc      # 不联网, 只用本地库重算指标 + 重画图
  python im1000_panel.py --plot      # 只重画图

产物 (全部输出到本脚本所在目录)
--------------------------------
  mo_raw.sqlite3        原始合约行情/指数/利率 + 抓取日志 (可反复增量)
  pcr_daily.csv         PCR 日度序列 (OI 口径为主, VOL 口径备查)
  iv_daily.csv          30天恒定到期 ATM IV + 指数收盘 + 20日HV
  atm_iv_by_expiry.csv  各到期日 ATM IV 明细 (含选中的平值合约与 Delta)
  panel_daily.csv       两图指标合并
  plot_pcr.png / plot_iv.png

口径说明 (与图保持一致)
-----------------------
  * 价格默认用中金所「今结算」settle (改 PRICE_FIELD='close' 可切换到收盘价)。
  * PCR 用持仓量 oi、全合约、不取倒数。图上"认沽÷认购 >1 偏空"即原始比值。
  * IV 平值点优先用**中金所直接给出的 Delta**: 每个到期月选 |Delta_call - 0.5|
    最小的合约 (认沽则用 |Delta_put + 0.5|), 与图中 "delta≈0.5 平值" 完全对齐;
    Delta 不可用才回退到 put-call parity 反推远期 + 行权价插值。
  * 30天恒定到期: 各到期月 ATM IV -> 按 w=sigma^2*T 线性插值到 T=30/365 -> 开方。
  * 到期日 = 合约到期月份第三个周五 (遇非交易日顺延至下一交易日, 需 AkShare 日历)。
  * 分位线 (2/5/10/20/50/80/90/95/98%) 与 "最新/均值/分位" 为全样本静态统计。
  * 中金所月度 ZIP 是原始数据的免费公开出口, 回溯到 MO 上市首日 2022-07-22 已验证。
"""
from __future__ import annotations

import argparse
import io
import math
import re
import sqlite3
import statistics
import sys
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests

# ============================================================ 配置区
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "mo_raw.sqlite3"
START_DATE = "20220722"          # MO 上市首日
END_DATE = None                  # None -> 今天
TARGET_TENOR_DAYS = 30
TRADING_DAYS = 250
HV_WINDOW = 20
MIN_TENOR_DAYS = 3
MAX_TENOR_DAYS = 400
PRICE_FIELD = "settle"           # settle(今结算) / close(今收盘)
PREFER_EXCHANGE_DELTA = True     # 用中金所 Delta 挑平值合约
DIV_Q = 0.0
FIXED_RF = 0.020                 # Shibor 拿不到时的回退 (连续复利年化)
RF_DAYS = 90
CFFEX_URL = "http://www.cffex.com.cn/sj/historysj/{ym}/zip/{ym}.zip"
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "http://www.cffex.com.cn/lssjxz",
}
MAX_RETRY = 3
SLEEP_BETWEEN_MONTHS = 0.2
Q_LEVELS = [0.02, 0.05, 0.10, 0.20, 0.50, 0.80, 0.90, 0.95, 0.98]
NEAR_MONTH_ONLY = False
INVERSE_PCR = False

CSV_RENAME = {
    "今开盘": "open", "最高价": "high", "最低价": "low", "今收盘": "close",
    "今结算": "settle", "前结算": "pre_settle", "成交量": "vol",
    "成交金额": "amount", "持仓量": "oi", "持仓变化": "oi_chg", "Delta": "delta",
}
CONTRACT_PATTERN = r"^MO(\d{4})-([CP])-(\d+(?:\.\d+)?)$"
FILE_DATE_RE = re.compile(r"(\d{8})")


# ============================================================ 小工具
def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def retry(fn, *args, **kwargs):
    last = None
    for i in range(MAX_RETRY):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.2 * (i + 1))
    raise RuntimeError(f"重试 {MAX_RETRY} 次仍失败: {last}")


def _native(v):
    if v is None or (not isinstance(v, (str, bytes)) and pd.isna(v)):
        return None
    return v.item() if hasattr(v, "item") else v


def upsert(conn: sqlite3.Connection, table: str, df: pd.DataFrame) -> None:
    if df is None or df.empty:
        return
    cols = list(df.columns)
    sql = f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) VALUES ({','.join(['?'] * len(cols))})"
    rows = [tuple(_native(v) for v in row) for row in df[cols].itertuples(index=False, name=None)]
    conn.executemany(sql, rows)
    conn.commit()


def init_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    # 兼容旧版表结构 (无 delta/strike 列则重建)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(opt_daily)")]
    if cols and "delta" not in cols:
        conn.execute("DROP TABLE IF EXISTS opt_daily")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS opt_daily (
            trade_date TEXT, ts_code TEXT, call_put TEXT, strike REAL,
            expiry_ym TEXT, expiry_date TEXT, open REAL, high REAL, low REAL,
            close REAL, settle REAL, pre_settle REAL, vol REAL, amount REAL,
            oi REAL, oi_chg REAL, delta REAL,
            PRIMARY KEY (trade_date, ts_code)
        );
        CREATE TABLE IF NOT EXISTS index_daily (trade_date TEXT PRIMARY KEY, close REAL);
        CREATE TABLE IF NOT EXISTS rf_daily (trade_date TEXT PRIMARY KEY, rate REAL);
        CREATE TABLE IF NOT EXISTS month_log (
            ym TEXT PRIMARY KEY, n_rows INTEGER, n_days INTEGER, fetched_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_opt_daily_date ON opt_daily(trade_date);
        """
    )
    return conn


def month_list(start: str, end: str) -> list[str]:
    y, m = int(start[:4]), int(start[4:6])
    ey, em = int(end[:4]), int(end[4:6])
    out = []
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def third_friday(year: int, month: int) -> datetime:
    d = datetime(year, month, 1)
    return d + timedelta(days=(4 - d.weekday()) % 7 + 14)


def get_trade_calendar() -> set[str]:
    """AkShare 交易日历; 拿不到则返回空集 (直接用第三个周五)。"""
    try:
        import akshare as ak

        df = ak.tool_trade_date_hist_sina()
        return {pd.Timestamp(x).strftime("%Y%m%d") for x in df["trade_date"]}
    except Exception as exc:  # noqa: BLE001
        log(f"交易日历不可用 ({exc}), 到期日按第三个周五")
        return set()


def expiry_date_of(ym: str, calendar: set[str]) -> str:
    ym = str(ym).strip()
    if len(ym) == 4 and ym.isdigit():      # 合约代码中的 YYMM -> 20YYMM
        ym = "20" + ym
    base = third_friday(int(ym[:4]), int(ym[4:6]))
    if not calendar:
        return base.strftime("%Y%m%d")
    d = base
    for _ in range(10):
        key = d.strftime("%Y%m%d")
        if key in calendar:
            return key
        d += timedelta(days=1)
    return base.strftime("%Y%m%d")


# ============================================================ 取数: 中金所免费月度包
def fetch_cffex_months(conn, months: list[str], force=False) -> None:
    done = {r[0] for r in conn.execute("SELECT ym FROM month_log")}
    current_ym = datetime.now().strftime("%Y%m")
    calendar = get_trade_calendar()
    for ym in months:
        # 当月每日新增, 每次重下; 历史月份已缓存则跳过
        if ym in done and ym != current_ym and not force:
            continue
        url = CFFEX_URL.format(ym=ym)
        try:
            resp = retry(requests.get, url, headers=HTTP_HEADERS, timeout=40)
            resp.raise_for_status()
            zf = zipfile.ZipFile(io.BytesIO(resp.content))
        except Exception as exc:  # noqa: BLE001
            log(f"  {ym} 下载失败: {exc}")
            continue

        frames, n_days, expiry_cache = [], 0, {}

        def exp_date(x: str) -> str:
            if x not in expiry_cache:
                expiry_cache[x] = expiry_date_of(x, calendar)
            return expiry_cache[x]

        for name in zf.namelist():
            m = FILE_DATE_RE.search(name)
            if not m:
                continue
            trade_date = m.group(1)
            try:
                raw = zf.read(name)
            except Exception:  # noqa: BLE001
                continue
            df = None
            for enc in ("gbk", "gb18030", "utf-8"):
                try:
                    df = pd.read_csv(io.BytesIO(raw), encoding=enc, skipinitialspace=True)
                    break
                except (UnicodeDecodeError, pd.errors.ParserError):
                    continue
            if df is None or df.empty or "合约代码" not in df.columns:
                continue
            df.columns = [str(c).strip() for c in df.columns]
            df["合约代码"] = df["合约代码"].astype(str).str.strip()
            df = df[df["合约代码"].str.match(r"^MO\d{4}-[CP]-", na=False)].copy()
            if df.empty:
                continue

            parsed = df["合约代码"].str.extract(CONTRACT_PATTERN)
            df["expiry_ym"] = parsed[0]
            df["call_put"] = parsed[1]
            df["strike"] = pd.to_numeric(parsed[2], errors="coerce")
            df = df.dropna(subset=["expiry_ym", "call_put", "strike"])
            if df.empty:
                continue
            df["ts_code"] = df["合约代码"]
            df["trade_date"] = trade_date
            df = df.rename(columns=CSV_RENAME)
            for c in ("open", "high", "low", "close", "settle", "pre_settle",
                      "vol", "amount", "oi", "oi_chg", "delta"):
                if c not in df.columns:
                    df[c] = np.nan
                df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", "", regex=False)
                                      .str.strip(), errors="coerce")
            df["expiry_date"] = df["expiry_ym"].map(exp_date)
            keep = ["trade_date", "ts_code", "call_put", "strike", "expiry_ym",
                    "expiry_date", "open", "high", "low", "close", "settle",
                    "pre_settle", "vol", "amount", "oi", "oi_chg", "delta"]
            frames.append(df[keep])
            n_days += 1

        stamp = datetime.now().isoformat(timespec="seconds")
        if not frames:
            log(f"  {ym} 包内无 MO 数据 (上市前月份属正常)")
            upsert(conn, "month_log", pd.DataFrame([{
                "ym": ym, "n_rows": 0, "n_days": 0, "fetched_at": stamp,
            }]))
            continue
        all_df = pd.concat(frames, ignore_index=True).drop_duplicates(["trade_date", "ts_code"])
        upsert(conn, "opt_daily", all_df)
        upsert(conn, "month_log", pd.DataFrame([{
            "ym": ym, "n_rows": len(all_df), "n_days": n_days, "fetched_at": stamp,
        }]))
        log(f"  {ym}  {n_days} 个交易日 / {len(all_df)} 条 MO 行情")
        time.sleep(SLEEP_BETWEEN_MONTHS)


# ============================================================ 取数: 指数与利率 (AkShare 免费)
def fetch_index(conn, start: str, end: str) -> pd.DataFrame:
    """指数收盘: 东方财富直连 (纯 requests) -> AkShare 新浪 -> AkShare 东财。"""
    log("拉取中证1000指数收盘价 ...")
    out = pd.DataFrame()
    # 1) 东方财富 JSON 接口, 不依赖 akshare
    try:
        url = ("https://push2his.eastmoney.com/api/qt/stock/kline/get"
               "?secid=1.000852&fields1=f1,f2,f3,f4,f5,f6"
               "&fields2=f51,f52,f53,f54,f55,f56,f57,f58"
               f"&klt=101&fqt=0&beg={start}&end={end}")
        resp = retry(requests.get, url, headers=HTTP_HEADERS, timeout=30)
        klines = resp.json()["data"]["klines"]
        out = pd.DataFrame([{
            "trade_date": row.split(",")[0].replace("-", ""),
            "close": pd.to_numeric(row.split(",")[2], errors="coerce"),
        } for row in klines])
        log("  东方财富接口取数成功")
    except Exception as exc:  # noqa: BLE001
        log(f"  东方财富接口失败 ({exc})")
    # 2) AkShare 新浪 / 东财备用
    if out.empty:
        for fname, kwargs, dcol, ccol in [
            ("stock_zh_index_daily", {"symbol": "sh000852"}, "date", "close"),
            ("index_zh_a_hist", {"symbol": "000852", "period": "daily",
                                 "start_date": start, "end_date": end}, "日期", "收盘"),
        ]:
            try:
                import akshare as ak

                raw = retry(getattr(ak, fname), **kwargs)
                out = pd.DataFrame({
                    "trade_date": pd.to_datetime(raw[dcol]).dt.strftime("%Y%m%d"),
                    "close": pd.to_numeric(raw[ccol], errors="coerce"),
                })
                break
            except Exception as exc:  # noqa: BLE001
                log(f"  AkShare {fname} 失败 ({exc})")
    if out.empty:
        # 网络失败时回退到本地已缓存的指数数据
        cached = pd.read_sql("SELECT trade_date, close FROM index_daily", conn)
        if not cached.empty:
            log(f"  网络失败, 使用本地缓存的 {len(cached)} 行指数数据")
            return cached
        sys.exit("指数收盘价获取失败, 且本地无缓存。请检查网络。")
    out = out[(out["trade_date"] >= start) & (out["trade_date"] <= end)]
    out = out.dropna().drop_duplicates("trade_date").sort_values("trade_date")
    upsert(conn, "index_daily", out)
    log(f"  指数落库 {len(out)} 行")
    return out


def shibor_to_cont(pct: float) -> float:
    if not np.isfinite(pct):
        return FIXED_RF
    return math.log1p((pct / 100.0) * RF_DAYS / 360.0) * (365.0 / RF_DAYS)


def fetch_rf(conn, trade_dates: list[str]) -> None:
    have = {r[0] for r in conn.execute("SELECT trade_date FROM rf_daily")}
    need = [d for d in trade_dates if d not in have]
    if not need:
        log("利率数据已缓存")
        return
    rate_map = {}
    try:
        import akshare as ak

        fn = getattr(ak, "macro_china_shibor_all", None)
        if fn is None:
            raise AttributeError("akshare 无 macro_china_shibor_all")
        df = retry(fn)
        df.columns = [str(c).strip() for c in df.columns]
        col = None
        for c in df.columns:
            if c.lower() in ("3m", "3mth") or "3个月" in c or "3月" in c:
                col = c
                break
        if col is None:
            raise KeyError(f"未找到 3M 列: {list(df.columns)}")
        date_col = next((c for c in df.columns if "date" in c.lower() or "日期" in c), df.columns[0])
        for _, row in df.iterrows():
            d = pd.to_datetime(row[date_col], errors="coerce")
            if pd.isna(d):
                continue
            rate_map[d.strftime("%Y%m%d")] = shibor_to_cont(float(row[col]))
    except Exception as exc:  # noqa: BLE001
        log(f"  Shibor 拉取失败 ({exc}), 回退 FIXED_RF={FIXED_RF}")
    out = pd.DataFrame([{"trade_date": d, "rate": rate_map.get(d, FIXED_RF)} for d in need])
    upsert(conn, "rf_daily", out)
    n_real = sum(d in rate_map for d in need)
    log(f"  利率落库 {len(out)} 行 (Shibor {n_real} / 固定值 {len(need)-n_real})")


# ============================================================ BS / IV
def _N(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def bs_price(F: float, K: float, T: float, r: float, sigma: float, cp: str) -> float:
    v = sigma * math.sqrt(T)
    d1 = (math.log(F / K) + 0.5 * sigma * sigma * T) / v
    d2 = d1 - v
    disc = math.exp(-r * T)
    if cp == "C":
        return disc * (F * _N(d1) - K * _N(d2))
    return disc * (K * _N(-d2) - F * _N(-d1))


def implied_vol(price: float, F: float, K: float, T: float, r: float, cp: str) -> float:
    if not all(np.isfinite(x) for x in (price, F, K, T, r)) or price <= 0 or T <= 0 or K <= 0:
        return float("nan")
    disc = math.exp(-r * T)
    intrinsic = disc * max(F - K, 0.0) if cp == "C" else disc * max(K - F, 0.0)
    if price <= intrinsic + 1e-9:
        return float("nan")
    sigma = 0.25
    for _ in range(60):
        p = bs_price(F, K, T, r, sigma, cp)
        v = disc * F * _pdf((math.log(F / K) + 0.5 * sigma * sigma * T)
                            / (sigma * math.sqrt(T))) * math.sqrt(T)
        if abs(p - price) < 1e-9:
            return sigma
        if v < 1e-12:
            break
        nxt = sigma - (p - price) / v
        if not (1e-4 < nxt < 5.0):
            break
        sigma = nxt
    lo, hi = 1e-4, 5.0
    for _ in range(120):
        mid = (lo + hi) / 2.0
        if bs_price(F, K, T, r, mid, cp) > price:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2.0


def infer_forward(g: pd.DataFrame, S: float, r: float, T: float) -> float:
    piv = g.pivot_table(index="strike", columns="call_put", values=PRICE_FIELD, aggfunc="last")
    if {"C", "P"}.issubset(piv.columns):
        valid = piv.dropna(subset=["C", "P"])
        fs = [float(k) + (float(row["C"]) - float(row["P"])) * math.exp(r * T)
              for k, row in valid.iterrows() if float(k) > 0]
        fs = [f for f in fs if 0.75 * S <= f <= 1.25 * S]
        if len(fs) >= 3:
            return statistics.median(fs)
    return S * math.exp((r - DIV_Q) * T)


def atm_iv(g: pd.DataFrame, F: float, T: float, r: float) -> tuple[float, str, float]:
    """返回 (IV, 选中合约, 该合约Delta)。优先用中金所 Delta 挑平值合约。"""
    px_col = PRICE_FIELD
    if PREFER_EXCHANGE_DELTA and "delta" in g.columns:
        c = g[(g["call_put"] == "C") & g["delta"].notna() & g[px_col].gt(0)].copy()
        if not c.empty:
            row = c.loc[(c["delta"] - 0.5).abs().idxmin()]
            iv = implied_vol(float(row[px_col]), F, float(row["strike"]), T, r, "C")
            if np.isfinite(iv):
                return iv, str(row["ts_code"]), float(row["delta"])
        p = g[(g["call_put"] == "P") & g["delta"].notna() & g[px_col].gt(0)].copy()
        if not p.empty:
            row = p.loc[(p["delta"] + 0.5).abs().idxmin()]
            iv = implied_vol(float(row[px_col]), F, float(row["strike"]), T, r, "P")
            if np.isfinite(iv):
                return iv, str(row["ts_code"]), float(row["delta"])

    # 回退: OTM 期权 IV 在行权价上插值到 K=F
    calls = g.loc[g["call_put"] == "C"].groupby("strike")[px_col].last().dropna()
    puts = g.loc[g["call_put"] == "P"].groupby("strike")[px_col].last().dropna()
    strikes = sorted(set(calls.index) | set(puts.index))
    if not strikes:
        return float("nan"), "", float("nan")

    def iv_at(k: float) -> float:
        if k >= F and k in calls.index:
            cp, px = "C", float(calls.loc[k])
        elif k <= F and k in puts.index:
            cp, px = "P", float(puts.loc[k])
        elif k in calls.index and k in puts.index:
            a = implied_vol(float(calls.loc[k]), F, k, T, r, "C")
            b = implied_vol(float(puts.loc[k]), F, k, T, r, "P")
            return float(np.nanmean([a, b]))
        else:
            return float("nan")
        return implied_vol(px, F, k, T, r, cp)

    below = [k for k in strikes if k < F]
    above = [k for k in strikes if k > F]
    k1 = max(below) if below else None
    k2 = min(above) if above else None
    iv1 = iv_at(k1) if k1 is not None else float("nan")
    iv2 = iv_at(k2) if k2 is not None else float("nan")
    if np.isfinite(iv1) and np.isfinite(iv2) and k2 > k1:
        val = iv1 * (k2 - F) / (k2 - k1) + iv2 * (F - k1) / (k2 - k1)
    elif np.isfinite(iv2):
        val = iv2
    elif np.isfinite(iv1):
        val = iv1
    else:
        val = float("nan")
    return (val if 0.005 < val < 3.0 else float("nan")), "(插值)", float("nan")


def interp_constant_maturity(points: list[tuple[float, float]]) -> tuple[float, int]:
    target = TARGET_TENOR_DAYS / 365.0
    valid = [(t, s) for t, s in points if np.isfinite(s) and t > 0]
    if not valid:
        return float("nan"), 0
    valid.sort()
    if len(valid) == 1:
        return valid[0][1], 1
    lo = [p for p in valid if p[0] <= target]
    hi = [p for p in valid if p[0] >= target]
    if lo and hi:
        t1, s1 = lo[-1]
        t2, s2 = hi[0]
    else:
        (t1, s1), (t2, s2) = sorted(sorted(valid, key=lambda p: abs(p[0] - target))[:2])
    if abs(t2 - t1) < 1e-12:
        return s1, len(valid)
    w1, w2 = s1 * s1 * t1, s2 * s2 * t2
    w = w1 + (w2 - w1) * (target - t1) / (t2 - t1)
    return math.sqrt(max(w, 0.0) / target), len(valid)


# ============================================================ 指标计算
def normalize_cp(s: pd.Series) -> pd.Series:
    return (s.astype(str).str.strip().str.upper()
            .map({"C": "C", "CALL": "C", "认购": "C", "P": "P", "PUT": "P", "认沽": "P"}))


def load_raw(conn):
    return (pd.read_sql("SELECT * FROM opt_daily", conn),
            pd.read_sql("SELECT * FROM index_daily", conn),
            pd.read_sql("SELECT * FROM rf_daily", conn))


def calc_pcr(daily: pd.DataFrame) -> pd.DataFrame:
    df = daily.copy()
    df["call_put"] = normalize_cp(df["call_put"])
    df = df[df["call_put"].isin(["C", "P"])].copy()
    if NEAR_MONTH_ONLY:
        near = df[df["expiry_date"] > df["trade_date"]].groupby("trade_date")["expiry_date"].min()
        df = df.join(near.rename("near"), on="trade_date")
        df = df[df["expiry_date"] == df["near"]]
    for c in ("vol", "oi"):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    g = df.groupby(["trade_date", "call_put"])[["oi", "vol"]].sum().reset_index()
    piv = g.pivot(index="trade_date", columns="call_put", values=["oi", "vol"]).fillna(0.0)
    piv.columns = [f"{a}_{b.lower()}" for a, b in piv.columns]
    for c in ("oi_c", "oi_p", "vol_c", "vol_p"):
        if c not in piv.columns:
            piv[c] = 0.0
    out = piv.reset_index()
    out["pcr_oi"] = out["oi_p"] / out["oi_c"].replace(0, np.nan)
    out["pcr_vol"] = out["vol_p"] / out["vol_c"].replace(0, np.nan)
    if INVERSE_PCR:
        out["pcr_oi"] = 1.0 / out["pcr_oi"]
        out["pcr_vol"] = 1.0 / out["pcr_vol"]
    return out[["trade_date", "pcr_oi", "pcr_vol", "oi_c", "oi_p", "vol_c", "vol_p"]]


def calc_iv(daily: pd.DataFrame, index: pd.DataFrame, rf: pd.DataFrame):
    idx = index.set_index("trade_date")["close"].astype(float)
    rate = rf.set_index("trade_date")["rate"].astype(float)
    df = daily.copy()
    df["call_put"] = normalize_cp(df["call_put"])
    df["strike"] = pd.to_numeric(df["strike"], errors="coerce")
    df = df[df["call_put"].isin(["C", "P"]) & df["strike"].gt(0)
            & df["expiry_date"].notna()].copy()

    iv_rows, detail_rows = [], []
    for trade_date, gday in df.groupby("trade_date", sort=True):
        if trade_date not in idx.index or trade_date not in rate.index:
            continue
        S, r = float(idx.loc[trade_date]), float(rate.loc[trade_date])
        if not (np.isfinite(S) and S > 0 and np.isfinite(r)):
            continue
        pts = []
        for expiry, gmat in gday.groupby("expiry_date"):
            try:
                days = (datetime.strptime(str(expiry), "%Y%m%d")
                        - datetime.strptime(str(trade_date), "%Y%m%d")).days
            except ValueError:
                continue
            if not (MIN_TENOR_DAYS <= days <= MAX_TENOR_DAYS):
                continue
            T = days / 365.0
            F = infer_forward(gmat, S, r, T)
            sig, chosen, delta = atm_iv(gmat, F, T, r)
            pts.append((T, sig))
            detail_rows.append({
                "trade_date": trade_date, "expiry_date": expiry, "days": days,
                "spot": S, "forward": F, "rf": r, "atm_iv": sig * 100.0,
                "chosen_contract": chosen, "chosen_delta": delta,
            })
        if not pts:
            continue
        iv30, n_exp = interp_constant_maturity(pts)
        iv_rows.append({"trade_date": trade_date, "iv_30": iv30 * 100.0, "n_expiries": n_exp})

    iv = pd.DataFrame(iv_rows)
    det = pd.DataFrame(detail_rows)
    if iv.empty:
        return iv, det
    hs = pd.DataFrame({"trade_date": idx.index, "index_close": idx.values})
    hs["hv20"] = (np.log(hs["index_close"] / hs["index_close"].shift(1))
                  .rolling(HV_WINDOW, min_periods=HV_WINDOW).std()
                  * math.sqrt(TRADING_DAYS) * 100.0)
    rf_df = pd.DataFrame({"trade_date": rate.index, "rf": rate.values})
    iv = (iv.merge(hs, on="trade_date", how="left")
            .merge(rf_df, on="trade_date", how="left")
            .sort_values("trade_date").reset_index(drop=True))
    return iv, det


def add_stats_info(df: pd.DataFrame, col: str) -> str:
    s = df[col].dropna()
    if s.empty:
        return "(无有效数据)"
    q = s.quantile(Q_LEVELS)
    latest = float(s.iloc[-1])
    rank = float((s <= latest).mean()) * 100
    parts = " ".join(f"{int(p*100)}%:{q[p]:.3f}" for p in Q_LEVELS)
    return (f"分位线 {parts}\n"
            f"区间统计 最新:{latest:.3f}  均值:{s.mean():.3f}  分位:{rank:.1f}%  样本:{len(s)}")


# ============================================================ 画图
def setup_chinese_font() -> None:
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.facecolor"] = "white"
    plt.rcParams["axes.facecolor"] = "white"


def plot_pcr(df: pd.DataFrame) -> Path:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    setup_chinese_font()
    s = df.dropna(subset=["pcr_oi"]).copy()
    if s.empty:
        return BASE_DIR / "plot_pcr.png"
    x = pd.to_datetime(s["trade_date"], format="%Y%m%d")
    y = s["pcr_oi"].to_numpy()
    q = s["pcr_oi"].quantile(Q_LEVELS)
    fig, ax = plt.subplots(figsize=(14, 5.6), dpi=130)
    ax.plot(x, y, color="#1f9e6e", lw=1.3)
    for p, c in [(0.02, "#b23a48"), (0.05, "#cf5b43"), (0.10, "#d99b3d"),
                 (0.50, "#6b7280"), (0.98, "#7a4fa3")]:
        ax.axhline(q[p], color=c, ls="--", lw=1.0, alpha=0.85)
        ax.text(x.max(), q[p], f"  {int(p*100)}% {q[p]:.3f}", color=c, fontsize=8, va="center")
    ext = (y <= q[0.02]) | (y >= q[0.98])
    ax.scatter(x[ext], y[ext], s=34, facecolors="white", edgecolors="#1f9e6e",
               linewidths=1.1, zorder=5)
    ax.set_title("认沽认购比  认沽÷认购，>1 偏空    持仓量 √ 成交量 □ 仅近月 □ 取倒数 □", fontsize=11)
    ax.set_ylabel("认沽÷认购")
    ax.grid(alpha=0.18)
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.text(0.06, 0.015, add_stats_info(s, "pcr_oi"), fontsize=8.5, color="#444")
    fig.tight_layout(rect=(0, 0.12, 1, 1))
    path = BASE_DIR / "plot_pcr.png"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_iv(df: pd.DataFrame) -> Path:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    setup_chinese_font()
    s = df.dropna(subset=["iv_30"]).copy()
    if s.empty:
        return BASE_DIR / "plot_iv.png"
    x = pd.to_datetime(s["trade_date"], format="%Y%m%d")
    y = s["iv_30"].to_numpy()
    q = s["iv_30"].quantile(Q_LEVELS)
    fig, ax = plt.subplots(figsize=(14, 5.6), dpi=130)
    ax.plot(x, y, color="#1f9e6e", lw=1.3)
    for p, c in [(0.02, "#b23a48"), (0.05, "#cf5b43"), (0.10, "#d99b3d"),
                 (0.50, "#6b7280"), (0.90, "#2f6fb0"), (0.98, "#7a4fa3")]:
        ax.axhline(q[p], color=c, ls="--", lw=1.0, alpha=0.85)
        ax.text(x.max(), q[p], f"  {int(p*100)}% {q[p]:.1f}", color=c, fontsize=8, va="center")
    ext = (y <= q[0.02]) | (y >= q[0.98])
    ax.scatter(x[ext], y[ext], s=34, facecolors="white", edgecolors="#1f9e6e",
               linewidths=1.1, zorder=5)
    ax.set_ylabel("IV (%)", color="#1f9e6e")
    ax.set_ylim(max(0, np.nanmin(y) - 4), min(90, np.nanmax(y) + 6))
    ax.grid(alpha=0.18)
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax2 = ax.twinx()
    if s["index_close"].notna().any():
        ax2.plot(x, s["index_close"], color="#2f6fb0", lw=1.0, alpha=0.8)
        ax2.set_ylabel("中证1000", color="#2f6fb0")
        ax2.grid(False)
    ax.set_title("波动率指数 30天恒定到期平值IV (%)     20日HV □  中证1000 (右轴) √", fontsize=11)
    fig.text(0.06, 0.015, add_stats_info(s, "iv_30"), fontsize=8.5, color="#444")
    fig.tight_layout(rect=(0, 0.12, 1, 1))
    path = BASE_DIR / "plot_iv.png"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


# ============================================================ 主流程
def main() -> None:
    ap = argparse.ArgumentParser(description="中证1000 MO: 30天ATM IV + PCR (全免费数据源)")
    ap.add_argument("--all", action="store_true", help="全量抓取 (默认)")
    ap.add_argument("--update", action="store_true", help="增量 (只重下当月)")
    ap.add_argument("--fetch", action="store_true", help="只取数")
    ap.add_argument("--calc", action="store_true", help="只算指标 (用本地库)")
    ap.add_argument("--plot", action="store_true", help="只画图")
    ap.add_argument("--start", default=START_DATE, help="起始日 YYYYMMDD")
    ap.add_argument("--end", default=END_DATE or datetime.now().strftime("%Y%m%d"), help="结束日")
    ap.add_argument("--force", action="store_true", help="强制重下所有月份")
    args = ap.parse_args()
    if not (args.all or args.update or args.fetch or args.calc or args.plot):
        args.all = True

    conn = init_db()
    if args.fetch or args.all or args.update:
        months = month_list(args.start, args.end)
        log(f"中金所免费月度包: {months[0]} ~ {months[-1]} 共 {len(months)} 个月")
        fetch_cffex_months(conn, months, force=args.force)
        fetch_index(conn, args.start, args.end)
        days = pd.read_sql("SELECT DISTINCT trade_date FROM opt_daily", conn)
        fetch_rf(conn, sorted(days["trade_date"].tolist()))

    if args.fetch and not (args.all or args.update or args.calc or args.plot):
        log("取数完成。")
        return

    daily, index, rf = load_raw(conn)
    log(f"计算指标: MO 行情 {len(daily)} 行, 指数 {index['trade_date'].nunique()} 个交易日")
    pcr = calc_pcr(daily)
    iv, det = calc_iv(daily, index, rf)
    if pcr.empty or iv.empty:
        sys.exit("指标为空: 请先执行 --all 取数, 或检查本地库是否有数据。")
    pcr.to_csv(BASE_DIR / "pcr_daily.csv", index=False, encoding="utf-8-sig")
    iv.to_csv(BASE_DIR / "iv_daily.csv", index=False, encoding="utf-8-sig")
    det.to_csv(BASE_DIR / "atm_iv_by_expiry.csv", index=False, encoding="utf-8-sig")
    panel = iv.merge(pcr[["trade_date", "pcr_oi", "pcr_vol"]], on="trade_date", how="left")
    panel.to_csv(BASE_DIR / "panel_daily.csv", index=False, encoding="utf-8-sig")
    log(f"PCR {len(pcr)} 行 / IV {len(iv)} 行 / 到期明细 {len(det)} 行")
    log("PCR: " + add_stats_info(pcr, "pcr_oi").replace("\n", " | "))
    log("IV : " + add_stats_info(iv, "iv_30").replace("\n", " | "))

    p1 = plot_pcr(pd.read_csv(BASE_DIR / "pcr_daily.csv", dtype={"trade_date": str}))
    p2 = plot_iv(pd.read_csv(BASE_DIR / "iv_daily.csv", dtype={"trade_date": str}))
    log(f"图片输出: {p1.name}, {p2.name}")
    log("完成。")


if __name__ == "__main__":
    main()
