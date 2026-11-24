# -*- coding: utf-8 -*-
"""
us_etf_premium_alert.py —— 美股 ETF 折溢价每日提醒
==================================================

按 qdii_notice.csv 的清单，筛出「跟踪美股指数的场内 ETF」：

  * 剔除 LOF（16xxxx / 50xxxx / 名称含 LOF）；
  * 剔除清单里的非美股 ETF（港股/恒生/日经/德国/法国/沙特/黄金/商品等）；
  * 只保留 etf/Arbitrage/info_etf_qdii.json 中有元数据的 QDII ETF；
  * 名称含纳指/纳斯达克/标普/道琼斯/美国50/罗素/费城半导体等关键词。

溢价率优先取 woody 实时估值（woody/realtime_netvalue.get_merged_data），
缺失时回落集思录 T-1 溢价率（crawl/qdii_jsl.qdii_e_index_jsl）。
给出每个标的的溢价率与**等权平均溢价率**、中位数、折价/溢价只数。

推送频率：每交易日 14:40 之后首次成功推送一次，状态落盘
`state/us_etf_premium_state.json`，发送失败则下一轮重试。

用法
----
    python us_etf_premium_alert.py --once            # 立即跑一次（真实推送）
    python us_etf_premium_alert.py --once --dry-run  # 只打印，不推送/不落状态
    python us_etf_premium_alert.py --once --force    # 绕过"每日一次"限制
"""

from __future__ import print_function

import argparse
import csv
import datetime
import json
import os
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from dingtalk_utils import DingTalkNotifier

CSV_PATH = os.path.join(HERE, "qdii_notice.csv")
META_PATH = os.path.join(HERE, "etf", "Arbitrage", "info_etf_qdii.json")
STATE_DIR = os.path.join(HERE, "state")
STATE_FILE = os.path.join(STATE_DIR, "us_etf_premium_state.json")

TITLE = "美股ETF折溢价日报"
TRIGGER_HM = (14, 40)          # 14:40 之后首个成功轮次推送
RETRY_SECONDS = 300            # 发送失败时最短重试间隔

# 美股相关关键词：跟踪美国市场/美国行业指数的 QDII ETF
US_KEYWORDS = (
    "纳指", "纳斯达克", "标普500", "标普", "道琼斯", "美国50", "美国",
    "罗素", "费城半导体", "纳指100", "纳指科技",
)
# 明确排除：这些虽然也在 QDII 清单里，但不是"美股 ETF"
EXCLUDE_KEYWORDS = (
    "中概", "中国", "港股", "恒生", "香港", "H股", "国企",
    "日经", "日本", "东证", "德国", "法国", "亚太", "东南亚",
    "沙特", "印度", "巴西", "中韩", "新兴亚洲", "新经济",
    "美元债", "债券", "黄金", "豆粕", "有色", "原油",
)


# ---------------------------------------------------------------------------
# 清单与分类
# ---------------------------------------------------------------------------
def _read_text(path):
    """qdii_notice.csv 可能是 UTF-8 或 GBK，逐个尝试。"""
    for enc in ("utf-8-sig", "gb18030", "gbk"):
        try:
            with open(path, "r", encoding=enc, newline="") as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    return ""


def load_target_codes():
    text = _read_text(CSV_PATH)
    if not text:
        return []
    codes = []
    for i, row in enumerate(csv.reader(text.splitlines())):
        if not row:
            continue
        code = row[0].strip().lstrip("\ufeff")
        if i == 0 and not code.isdigit():
            continue                      # 表头 fund_code
        if code.isdigit():
            codes.append(code.zfill(6))
    return list(dict.fromkeys(codes))


def load_meta():
    try:
        with open(META_PATH, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def is_lof(code, name):
    return code.startswith(("16", "50", "18")) or "LOF" in name.upper()


def is_us_etf(code, name):
    if not name or is_lof(code, name):
        return False
    if any(k in name for k in EXCLUDE_KEYWORDS):
        return False
    return any(k in name for k in US_KEYWORDS)


def classify_us_etfs():
    """返回 [(code, name)]，附带被剔除的原因统计。"""
    meta = load_meta()
    pairs, skipped = [], {"no_meta": 0, "lof": 0, "non_us": 0}
    for code in load_target_codes():
        info = meta.get(code) or {}
        name = info.get("InstrumentName") or ""
        if not name:
            skipped["no_meta"] += 1
            continue
        if is_lof(code, name):
            skipped["lof"] += 1
            continue
        if not is_us_etf(code, name):
            skipped["non_us"] += 1
            continue
        pairs.append((code, name))
    return pairs, skipped


# ---------------------------------------------------------------------------
# 溢价率取数
# ---------------------------------------------------------------------------
def _parse_pct(value):
    """集思录 '1.23%' / '1.23' → 小数 0.0123；已是小数的按原样返回。"""
    try:
        if isinstance(value, str):
            v = float(value.strip().rstrip("%"))
        else:
            v = float(value)
    except (TypeError, ValueError):
        return None
    return v / 100.0 if abs(v) > 1.5 else v


def fetch_premiums():
    """返回 {code: (溢价率小数, 来源)}；两路数据源互不阻断。"""
    out = {}
    try:
        from woody.realtime_netvalue import get_merged_data
        data = get_merged_data(cache_duration=600) or {}
        for code, val in data.items():
            try:
                out[str(code).zfill(6)] = (float(val), "woody实时")
            except (TypeError, ValueError):
                continue
    except Exception as e:
        print("[warn] woody 实时溢价取数失败：%s" % e)

    try:
        from crawl.qdii_jsl import qdii_e_index_jsl
        df = qdii_e_index_jsl()
        for _, row in df.iterrows():
            code = str(row.get("代码") or "").strip().zfill(6)
            val = _parse_pct(row.get("T-1溢价率"))
            if code and val is not None and code not in out:
                out[code] = (val, "集思录T-1")
    except Exception as e:
        print("[warn] 集思录 T-1 溢价取数失败：%s" % e)
    return out


def analyze():
    pairs, skipped = classify_us_etfs()
    premiums = fetch_premiums()
    rows, missing = [], []
    for code, name in pairs:
        hit = premiums.get(code)
        if not hit:
            missing.append(code)
            continue
        rows.append({"code": code, "name": name, "premium": hit[0], "source": hit[1]})
    rows.sort(key=lambda x: x["premium"], reverse=True)
    vals = [r["premium"] for r in rows]
    return {
        "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "rows": rows,
        "missing": missing,
        "skipped": skipped,
        "count": len(rows),
        "avg": sum(vals) / len(vals) if vals else None,
        "median": statistics.median(vals) if vals else None,
        "n_premium": sum(1 for v in vals if v > 0),
        "n_discount": sum(1 for v in vals if v < 0),
    }


# ---------------------------------------------------------------------------
# 消息与状态
# ---------------------------------------------------------------------------
def _pct(v):
    return "—" if v is None else "%+.2f%%" % (v * 100.0)


def build_message(res):
    lines = ["### %s" % TITLE, ""]
    sk = res["skipped"]
    lines.append("> %s · 样本 **%d** 只（美股 ETF，已剔除 LOF/非美股）· "
                 "平均溢价率 **%s** · 中位数 %s · 溢价 %d / 折价 %d"
                 % (res["at"], res["count"], _pct(res["avg"]), _pct(res["median"]),
                    res["n_premium"], res["n_discount"]))
    lines.append("> 清单过滤：无 ETF 元数据 %d / LOF %d / 非美股 %d；"
                 "无溢价数据 %d 只（不参与平均）"
                 % (sk["no_meta"], sk["lof"], sk["non_us"], len(res["missing"])))
    lines.append("")
    if res["rows"]:
        lines.append("| 代码 | 名称 | 溢价率 | 数据源 |")
        lines.append("|---|---|---|---|")
        for r in res["rows"]:
            lines.append("| %s | %s | %s | %s |"
                         % (r["code"], r["name"], _pct(r["premium"]), r["source"]))
    else:
        lines.append("> 本轮没有取到有效溢价数据。")
    lines.append("")
    lines.append("> 规则：清单来自 `qdii_notice.csv`；溢价率优先 Woody 实时估值，"
                 "缺失回落集思录 T-1；平均为等权平均，不含无数据标的。"
                 "每交易日 14:40 后首次成功推送一次。")
    return "\n".join(lines)


def _read_sent_date():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return (json.load(f) or {}).get("sent_date")
    except Exception:
        return None


def _write_state(res):
    try:
        if not os.path.isdir(STATE_DIR):
            os.makedirs(STATE_DIR)
        payload = {
            "sent_date": datetime.date.today().isoformat(),
            "sent_at": res["at"],
            "count": res["count"],
            "avg_pct": None if res["avg"] is None else round(res["avg"] * 100, 3),
        }
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STATE_FILE)
    except Exception as e:
        print("[warn] 状态落盘失败：%s" % e)


def run_once(dry_run=False, force=False, send=True):
    res = analyze()
    msg = build_message(res)
    if dry_run:
        print("\n" + "=" * 70 + "\n" + msg + "\n" + "=" * 70 + "\n")
        return {"ok": True, "sent": False, "reason": "dry-run", "result": res}

    if not force and _read_sent_date() == datetime.date.today().isoformat():
        return {"ok": True, "sent": False, "reason": "今日已推送", "result": res}
    if not res["rows"]:
        return {"ok": False, "sent": False, "reason": "无有效溢价数据", "result": res}
    if not send:
        return {"ok": True, "sent": False, "reason": "send=False", "result": res}

    try:
        ok = DingTalkNotifier().send_markdown(TITLE, msg, at_all=False)
    except Exception as e:
        return {"ok": False, "sent": False, "reason": "发送异常: %s" % e, "result": res}
    if ok:
        _write_state(res)
    return {"ok": bool(ok), "sent": bool(ok),
            "reason": "已发送" if ok else "钉钉未发送", "result": res}


# ---------------------------------------------------------------------------
# 常驻任务（被 main.py 挂起）
# ---------------------------------------------------------------------------
class CancellableTask(object):
    def __init__(self):
        self._is_cancelled = False

    async def loop(self):
        while not self._is_cancelled:
            try:
                await self.run_task()
                import asyncio
                await asyncio.sleep(1)
            except Exception as e:
                print("[error] %s: %s" % (self.__class__.__name__, e))
                import traceback
                traceback.print_exc()

    async def run_task(self):
        raise NotImplementedError()

    def cancel(self):
        self._is_cancelled = True


class UsEtfPremiumMonitor(CancellableTask):
    """每交易日 14:40 后首次运行推送；失败则每 RETRY_SECONDS 重试。"""

    def __init__(self):
        CancellableTask.__init__(self)
        self._last_try = 0.0

    async def run_task(self):
        now = datetime.datetime.now()
        if now.weekday() >= 5:
            return
        if (now.hour, now.minute) < TRIGGER_HM or now.hour >= 15:
            return
        if time.time() - self._last_try < RETRY_SECONDS:
            return
        self._last_try = time.time()
        r = run_once()
        print("[us_etf_premium] %s · 样本 %d · 平均 %s"
              % (r["reason"], r["result"]["count"], _pct(r["result"]["avg"])))


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="美股 ETF 折溢价每日提醒")
    ap.add_argument("--once", action="store_true", help="只跑一轮后退出")
    ap.add_argument("--dry-run", action="store_true", help="只打印，不推送不落状态")
    ap.add_argument("--force", action="store_true", help="忽略每日一次限制")
    a = ap.parse_args()
    r = run_once(dry_run=a.dry_run, force=a.force)
    print("结果：%s" % {k: v for k, v in r.items() if k != "result"})
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
