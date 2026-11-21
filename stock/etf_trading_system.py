#!/usr/bin/env python3
"""
ETF波动率趋势交易系统
====================
基于《波动率——金融市场最核心的指标》+《场内的ETF策略我终于做好了》

核心策略（文章原文）：
  1. 大级别择时：池中20只ETF翻多>10只才允许入场
  2. 波动率调整趋势指标（比均线更好）
  3. 买点：沉寂后爆发
  4. 完整买卖时机：基于波动率四阶段周期
  5. 2026年实际数据运行

数据源：新浪财经(历史K线) + 腾讯证券(实时行情)

用法：
  python3 etf_trading_system.py                  # 完整分析+买卖信号
  python3 etf_trading_system.py --backtest       # 模拟回测（基于真实数据）
  python3 etf_trading_system.py --signals        # 只输出买卖信号
  python3 etf_trading_system.py --positions      # 输出建议持仓及止损
"""

import requests
import json
import time
import pandas as pd
import numpy as np
import os
import sys
from datetime import datetime, timedelta
from collections import Counter

# ============ 配置 ============
OUTPUT_DIR = "/root/etf_trading"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 20只ETF池
ETF_POOL = [
    {"code": "510300", "name": "沪深300ETF",  "market": "sh", "category": "宽基"},
    {"code": "510050", "name": "上证50ETF",   "market": "sh", "category": "宽基"},
    {"code": "159915", "name": "创业板ETF",   "market": "sz", "category": "宽基"},
    {"code": "588000", "name": "科创50ETF",   "market": "sh", "category": "宽基"},
    {"code": "510500", "name": "中证500ETF",  "market": "sh", "category": "宽基"},
    {"code": "512100", "name": "中证1000ETF", "market": "sh", "category": "宽基"},
    {"code": "159949", "name": "创业板50ETF", "market": "sz", "category": "宽基"},
    {"code": "512480", "name": "半导体ETF",   "market": "sh", "category": "行业"},
    {"code": "515050", "name": "5G ETF",      "market": "sh", "category": "行业"},
    {"code": "512880", "name": "证券ETF",     "market": "sh", "category": "行业"},
    {"code": "159865", "name": "养殖ETF",     "market": "sz", "category": "行业"},
    {"code": "512010", "name": "医药ETF",     "market": "sh", "category": "行业"},
    {"code": "515030", "name": "新能源车ETF", "market": "sz", "category": "行业"},
    {"code": "159766", "name": "旅游ETF",     "market": "sz", "category": "行业"},
    {"code": "159981", "name": "能源化工ETF", "market": "sz", "category": "商品"},
    {"code": "159980", "name": "有色ETF",     "market": "sz", "category": "商品"},
    {"code": "518880", "name": "黄金ETF",     "market": "sh", "category": "商品"},
    {"code": "511380", "name": "国债ETF",     "market": "sh", "category": "债券"},
    {"code": "511880", "name": "银华日利ETF", "market": "sh", "category": "债券"},
    {"code": "513100", "name": "纳指ETF",     "market": "sh", "category": "跨境"},
]

# ============ 数据获取 ============

def fetch_history_sina(code, market, days=120):
    """新浪历史K线"""
    sym = f"{market}{code}"
    url = ("https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
           f"CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=no&datalen={days}")
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                time.sleep(1); continue
            data = resp.json()
            if not data or len(data) < 5:
                time.sleep(1); continue
            rows = [{
                "date": item.get("day", ""),
                "open": float(item.get("open", 0)),
                "high": float(item.get("high", 0)),
                "low": float(item.get("low", 0)),
                "close": float(item.get("close", 0)),
                "volume": float(item.get("volume", 0)),
            } for item in data]
            return pd.DataFrame(rows)
        except:
            time.sleep(1)
    return pd.DataFrame()


def fetch_realtime_tencent(codes_with_market):
    """腾讯实时行情"""
    codes_str = ",".join([f"{m}{c}" for c, m in codes_with_market])
    url = f"https://web.sqt.gtimg.cn/q={codes_str}"
    headers = {"Referer": "https://finance.qq.com"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        results = {}
        for line in resp.text.split(";"):
            line = line.strip()
            if not line or "=" not in line: continue
            try:
                val = "=".join(line.split("=")[1:]).strip().strip('"')
                parts = val.split("~")
                if len(parts) >= 40:
                    results[parts[2]] = {
                        "price": float(parts[3]) if parts[3] else 0,
                        "change_pct": float(parts[32]) if parts[32] else 0,
                        "high": float(parts[33]) if parts[33] else 0,
                        "low": float(parts[34]) if parts[34] else 0,
                    }
            except: continue
        return results
    except:
        return {}


def get_all_etf_data():
    """获取所有ETF数据"""
    print("📡 获取数据中...")
    
    # 实时行情
    codes_mkt = [(e["code"], e["market"]) for e in ETF_POOL]
    realtime = fetch_realtime_tencent(codes_mkt)
    print(f"  → 实时行情: {len(realtime)}只")
    time.sleep(0.5)
    
    # 历史K线
    all_data = {}
    for etf in ETF_POOL:
        print(f"  → {etf['name']}({etf['code']})...", end=" ")
        hist = fetch_history_sina(etf["code"], etf["market"], days=120)
        if not hist.empty and len(hist) >= 30:
            all_data[etf["code"]] = hist
            print(f"✅ {len(hist)} 条")
        else:
            print("❌")
        time.sleep(0.3)
    
    return all_data, realtime


# 波动率阈值
_VOL_LOW     = 15.0
_VOL_MEDIUM  = 25.0
_VOL_HIGH    = 40.0
_VOL_EXTREME = 60.0

# ============ 核心计算 ============

def calc_hv(df, period=20):
    """年化历史波动率 (HV)"""
    if df.empty or len(df) < period:
        return 0.0
    ret = df["close"].pct_change().dropna()
    if len(ret) < period:
        return 0.0
    return ret.tail(period).std() * (252 ** 0.5)


def calc_hv_short(df, period=5):
    """短期HV（用于模拟IV的变化方向）"""
    if df.empty or len(df) < period:
        return 0.0
    ret = df["close"].pct_change().dropna()
    if len(ret) < period:
        return 0.0
    return ret.tail(period).std() * (252 ** 0.5)


def calc_hv_trend(df, period=20):
    """计算HV的变化趋势（上升/下降/平稳）"""
    if df.empty or len(df) < period + 10:
        return "steady", 0.0
    ret = df["close"].pct_change().dropna()
    vol_series = ret.rolling(window=period).std() * (252 ** 0.5)
    vol_series = vol_series.dropna()
    if len(vol_series) < 15:
        return "steady", 0.0
    
    recent = vol_series.iloc[-5:].mean()
    before = vol_series.iloc[-15:-5].mean()
    
    if before > 0:
        ratio = recent / before
    else:
        ratio = 1.0
    
    if ratio > 1.3:
        return "up", ratio
    elif ratio < 0.7:
        return "down", ratio
    return "steady", ratio


def calc_trend_strength(df, period=20):
    """波动率调整趋势强度"""
    if df.empty or len(df) < period:
        return 0.0, 0
    
    closes = df["close"].values[-period:]
    x = np.arange(len(closes))
    slope = np.polyfit(x, closes, 1)[0]
    price_std = np.std(closes)
    base = slope / (price_std * 2 / period) if price_std > 0 else 0
    
    hv = calc_hv(df, period)
    price = closes[-1]
    ma = np.mean(closes)
    
    if price > ma and slope > 0:
        direction = 1
    elif price < ma and slope < 0:
        direction = -1
    else:
        direction = 0
    
    strength = max(-1.0, min(1.0, base * (1.3 if hv > 0.2 else 1.0)))
    return strength, direction


# ============================================================
# ★★★★★ 核心：完整的买卖信号生成器 ★★★★★
# ============================================================

def generate_trade_signals(df):
    """
    基于波动率周期生成完整买卖信号
    
    返回 dict:
      signal      : BUY / SELL / HOLD / WAIT
      confidence  : 0-100
      phase       : 当前周期阶段
      reason      : 信号理由
      entry_price : 建议买入价（或当前价）
      stop_loss   : 止损价
      take_profit : 止盈目标价
      hold_days   : 预期持有天数
    """
    if df.empty or len(df) < 30:
        return {"signal": "WAIT", "confidence": 0, "reason": "数据不足", "phase": "未知"}
    
    closes = df["close"].values
    ret = df["close"].pct_change().dropna()
    current_price = closes[-1]
    
    # === 1. 计算核心指标 ===
    hv = calc_hv(df, 20)                          # 当前HV（年化）
    hv_short = calc_hv_short(df, 5)               # 短期HV（近期实际波动）
    hv_trend, hv_ratio = calc_hv_trend(df, 20)    # HV趋势
    
    # 波动率比值（沉寂期vs现在）
    if len(ret) >= 40:
        vol_before = ret.iloc[-40:-20].std()
        vol_now = ret.iloc[-20:].std()
        vol_ratio = vol_now / vol_before if vol_before > 0 else 1.0
    else:
        vol_ratio = 1.0
    
    # 价格趋势
    price_5d  = closes[-1] / closes[-5] - 1 if len(closes) >= 5 else 0
    price_20d = closes[-1] / closes[-20] - 1 if len(closes) >= 20 else 0
    price_60d = closes[-1] / closes[-60] - 1 if len(closes) >= 60 else 0
    
    strength, direction = calc_trend_strength(df)
    
    # HV年化百分比
    hv_pct = hv * 100
    
    # 波动率阈值
    VOL_LOW = _VOL_LOW
    VOL_MEDIUM = _VOL_MEDIUM
    VOL_HIGH = _VOL_HIGH
    VOL_EXTREME = _VOL_EXTREME

    # === 2. 判断波动率阶段 ===
    if hv_pct < VOL_LOW and abs(price_20d) < 0.03:
        phase = "沉寂期"
    elif hv_pct < VOL_MEDIUM and price_20d > 0.01 and hv_trend == "up":
        phase = "暗流涌动"     # ✅ 最佳买入阶段
    elif hv_pct < VOL_HIGH and price_20d > 0 and hv_trend == "up" and vol_ratio > 1.5:
        phase = "爆发期"       # ✅ 可买入（放量明显）
    elif hv_pct > VOL_HIGH and price_20d > 0.05 and hv_trend == "up":
        phase = "加速上涨"     # ⚠️ 持有不加仓
    elif hv_pct > VOL_MEDIUM and price_5d < 0.02 and hv_trend == "steady":
        phase = "筑顶期"       # ❌ 准备卖出
    elif hv_pct > VOL_EXTREME and price_20d < -0.05:
        phase = "恐慌期"       # ❌ 已经暴跌
    elif hv_trend == "down" and abs(price_5d) < 0.02:
        phase = "横盘震荡"     # ❌ 观望
    else:
        phase = "震荡期"
    
    # === 3. 【买入信号】 ===
    buy_score = 0
    buy_reasons = []
    
    # 条件1：波动率从沉寂到爆发（放量比>1.5x）
    if vol_ratio > 1.5:
        buy_score += 30
        buy_reasons.append(f"放量{vol_ratio:.1f}x")
    elif vol_ratio > 1.2:
        buy_score += 15
        buy_reasons.append(f"放量{vol_ratio:.1f}x")
    
    # 条件2：价格启动上涨
    if price_5d > 0.02:
        buy_score += 20
        buy_reasons.append(f"近5日+{price_5d*100:.0f}%")
    elif price_5d > 0.01:
        buy_score += 10
    
    if price_20d > 0.03:
        buy_score += 10
    
    # 条件3：HV不要太高（避开筑顶）
    if hv_pct < 50:
        buy_score += 15
    elif hv_pct < 70:
        buy_score += 5
    else:
        buy_score -= 20
        buy_reasons.append(f"HV={hv_pct:.0f}%偏高")
    
    # 条件4：价格在均线上
    ma20 = np.mean(closes[-20:]) if len(closes) >= 20 else current_price
    if current_price > ma20:
        buy_score += 15
    
    # 条件5：趋势方向为正
    if direction == 1:
        buy_score += 15
    elif direction == -1:
        buy_score -= 30
        buy_reasons.append("趋势为空")
    
    # 条件6：暗流涌动/爆发期加分
    if phase in ("暗流涌动", "爆发期"):
        buy_score += 10
    
    # === 4. 【卖出信号】 ===
    sell_score = 0
    sell_reasons = []
    
    # 条件1：筑顶（HV走高但价格停滞）
    if phase == "筑顶期" or (hv_trend == "steady" and price_5d < 0.01 and hv_pct > 35):
        sell_score += 30
        sell_reasons.append("筑顶迹象")
    
    # 条件2：趋势转空
    if direction == -1:
        sell_score += 25
        sell_reasons.append("趋势转空")
    
    # 条件3：HV极高+价格下跌
    if hv_pct > 50 and price_5d < -0.02:
        sell_score += 25
        sell_reasons.append(f"高波动+下跌")
    
    # 条件4：近期涨幅过大
    if price_60d > 0.30 and hv_trend != "up":
        sell_score += 20
        sell_reasons.append(f"60日涨{price_60d*100:.0f}%获利丰厚")
    
    # 条件5：均线破位
    if current_price < ma20 * 0.95:
        sell_score += 20
        sell_reasons.append("跌破5日均线")
    
    # === 5. 最终决策 ===
    if buy_score >= 60:
        # 计算建议价格
        entry_price = current_price
        stop_loss = current_price * 0.95   # 5%止损
        take_profit = current_price * 1.10  # 10%止盈
        hold_days = 25  # 文章平均持有周期
        
        return {
            "signal": "BUY",
            "confidence": buy_score,
            "phase": phase,
            "reason": " | ".join(buy_reasons) if buy_reasons else "综合条件良好",
            "entry_price": round(entry_price, 3),
            "stop_loss": round(stop_loss, 3),
            "take_profit": round(take_profit, 3),
            "hold_days": hold_days,
            "hv_pct": round(hv_pct, 1),
            "price_20d": round(price_20d * 100, 1),
        }
    
    elif sell_score >= 40:
        return {
            "signal": "SELL",
            "confidence": sell_score,
            "phase": phase,
            "reason": " | ".join(sell_reasons),
            "entry_price": round(current_price, 3),
            "stop_loss": None,
            "take_profit": None,
            "hold_days": 0,
            "hv_pct": round(hv_pct, 1),
            "price_20d": round(price_20d * 100, 1),
        }
    
    elif direction == 1 and buy_score >= 30:
        return {
            "signal": "HOLD",
            "confidence": buy_score,
            "phase": phase,
            "reason": "趋势看多，持有跟踪",
            "entry_price": round(current_price, 3),
            "stop_loss": round(current_price * 0.95, 3),
            "take_profit": round(current_price * 1.08, 3),
            "hold_days": 15,
            "hv_pct": round(hv_pct, 1),
            "price_20d": round(price_20d * 100, 1),
        }
    
    else:
        return {
            "signal": "WAIT",
            "confidence": max(buy_score, 0),
            "phase": phase,
            "reason": "条件不满足，继续观望",
            "entry_price": round(current_price, 3),
            "stop_loss": None,
            "take_profit": None,
            "hold_days": 0,
            "hv_pct": round(hv_pct, 1),
            "price_20d": round(price_20d * 100, 1),
        }


# ============================================================
# ★★★★★ 大级别择时 ★★★★★
# ============================================================

def market_timing(df_dict):
    """
    大级别择时：池中多头>50%才允许入场
    
    返回：
      can_trade : bool
      ratio     : 多头占比
      details   : 各ETF方向
    """
    bullish = 0
    bearish = 0
    neutral = 0
    details = {}
    
    for etf in ETF_POOL:
        code = etf["code"]
        if code not in df_dict:
            continue
        _, direction = calc_trend_strength(df_dict[code])
        if direction == 1:
            bullish += 1
        elif direction == -1:
            bearish += 1
        else:
            neutral += 1
        details[etf["name"]] = direction
    
    total = bullish + bearish + neutral
    ratio = bullish / total if total > 0 else 0
    
    return {
        "can_trade": ratio > 0.5,
        "bullish_ratio": round(ratio * 100, 1),
        "bullish": bullish,
        "bearish": bearish,
        "neutral": neutral,
        "total": total,
        "details": details,
    }


# ============================================================
# ★★★★★ 主运行函数 ★★★★★
# ============================================================

def run_analysis():
    """运行完整分析"""
    
    print(f"\n{'='*70}")
    print(f"   ETF波动率趋势交易系统")
    print(f"   时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*70}\n")
    
    # 获取数据
    all_data, realtime = get_all_etf_data()
    if not all_data:
        print("❌ 数据获取失败")
        return
    
    # 大级别择时
    print(f"\n{'='*70}")
    print(f"   📈 第一步：大级别择时（池中多头>50%才入场）")
    print(f"{'='*70}")
    timing = market_timing(all_data)
    print(f"   多头: {timing['bullish']}/{timing['total']} = {timing['bullish_ratio']}%")
    print(f"   空头: {timing['bearish']}/{timing['total']}")
    print(f"   中性: {timing['neutral']}/{timing['total']}")
    
    if timing["can_trade"]:
        print(f"\n   ✅ 择时结果: 可以入场交易")
    else:
        print(f"\n   ❌ 择时结果: 观望为宜")
    
    # 逐个分析买卖信号
    print(f"\n{'='*70}")
    print(f"   📊 第二步：ETF买卖信号分析")
    print(f"{'='*70}\n")
    
    all_signals = []
    buy_list = []
    sell_list = []
    
    for etf in ETF_POOL:
        code = etf["code"]
        name = etf["name"]
        category = etf["category"]
        
        if code not in all_data:
            continue
        
        df = all_data[code]
        signal = generate_trade_signals(df)
        signal["code"] = code
        signal["name"] = name
        signal["category"] = category
        
        # 实时价格
        if code in realtime:
            signal["current_price"] = realtime[code].get("price", 0)
            signal["change_today"] = realtime[code].get("change_pct", 0)
        else:
            signal["current_price"] = df["close"].values[-1]
            signal["change_today"] = None
        
        all_signals.append(signal)
        
        if signal["signal"] == "BUY":
            buy_list.append(signal)
        elif signal["signal"] == "SELL":
            sell_list.append(signal)
        
        # 终端输出
        sig_icons = {"BUY": "🟢 买入", "SELL": "🔴 卖出", "HOLD": "🟡 持有", "WAIT": "⚪ 观望"}
        sig_icon = sig_icons.get(signal["signal"], "⚪")
        
        c = signal.get("change_today")
        c_str = f"{c:+.1f}%" if c is not None else ""
        print(f"  [{category}] {name:<10}({code}) {sig_icon} "
              f"评分={signal['confidence']:2.0f} "
              f"HV={signal['hv_pct']:4.1f}% "
              f"{signal['phase']:<5} "
              f"20日={signal['price_20d']:+.1f}% "
              f"{c_str}")
        print(f"            → {signal['reason'][:60]}")
        
        # 详细参数
        if signal["signal"] == "BUY":
            print(f"            买入价={signal['entry_price']:.3f} "
                  f"止损={signal['stop_loss']:.3f} "
                  f"止盈={signal['take_profit']:.3f} "
                  f"持有{signal['hold_days']}天")
        elif signal["signal"] == "SELL":
            print(f"            当前价={signal['entry_price']:.3f} "
                  f"建议止盈/止损离场")
        elif signal["signal"] == "HOLD" and signal["stop_loss"]:
            print(f"            移动止损={signal['stop_loss']:.3f} "
                  f"止盈={signal['take_profit']:.3f}")
    
    # === 汇总输出 ===
    print(f"\n{'='*70}")
    print(f"   📋 最终交易建议")
    print(f"{'='*70}")
    
    # 大级别择时结论
    if timing["can_trade"]:
        print(f"\n   ✅ 当前可以交易")
    else:
        print(f"\n   ❌ 当前不宜交易")
    
    # 买入列表
    if buy_list:
        print(f"\n   🟢 【买入信号】{len(buy_list)}只ETF建议买入：")
        print(f"   {'ETF':<8} {'评分':>4} {'HV':>6} {'阶段':<10} {'买入价':>8} {'止损':>8} {'止盈':>8} {'持有':>4}")
        print(f"   {'-'*60}")
        buy_list_sorted = sorted(buy_list, key=lambda x: -x["confidence"])
        for s in buy_list_sorted:
            print(f"   {s['name']:<8} {s['confidence']:4.0f} {s['hv_pct']:5.1f}% "
                  f"{s['phase']:<10} {s['entry_price']:8.3f} {s['stop_loss']:8.3f} "
                  f"{s['take_profit']:8.3f} {s['hold_days']:4}天")
    
    # 卖出列表
    if sell_list:
        print(f"\n   🔴 【卖出信号】{len(sell_list)}只ETF建议卖出：")
        for s in sell_list:
            print(f"   {s['name']:<10}({s['code']}) — {s['reason']}")
    
    # 汇总统计
    buys = len(buy_list)
    sells = len(sell_list)
    holds = sum(1 for s in all_signals if s["signal"] == "HOLD")
    waits = sum(1 for s in all_signals if s["signal"] == "WAIT")
    
    print(f"\n{'='*70}")
    print(f"   信号汇总: 🟢买入{buys} | 🟡持有{holds} | ⚪观望{waits} | 🔴卖出{sells}")
    print(f"   买入策略: {'可入场' if timing['can_trade'] else '不可入场'} | "
          f"建议仓位: {'适中(30-50%)' if timing['can_trade'] else '空仓(0%)'}")
    print(f"{'='*70}\n")
    
    # 保存结果
    output = {
        "time": datetime.now().strftime('%Y-%m-%d %H:%M'),
        "market_timing": timing,
        "signals": all_signals,
        "summary": {
            "buy": buys, "sell": sells, "hold": holds, "wait": waits,
            "can_trade": timing["can_trade"],
        }
    }
    
    # 保存CSV
    csv_rows = []
    for s in all_signals:
        csv_rows.append({
            "name": s["name"], "code": s["code"], "category": s["category"],
            "signal": s["signal"], "confidence": s["confidence"],
            "phase": s["phase"], "reason": s["reason"],
            "hv_pct": s["hv_pct"], "price_20d_pct": s["price_20d"],
            "entry_price": s["entry_price"],
            "stop_loss": s["stop_loss"] if s["stop_loss"] else "",
            "take_profit": s["take_profit"] if s["take_profit"] else "",
            "hold_days": s["hold_days"],
            "change_today": round(s["change_today"], 2) if s["change_today"] else "",
        })
    
    csv_path = os.path.join(OUTPUT_DIR, f"signals_{datetime.now().strftime('%Y%m%d_%H%M')}.csv")
    pd.DataFrame(csv_rows).to_csv(csv_path, index=False, encoding='utf-8-sig')
    print(f"📁 详细数据已保存: {csv_path}")
    
    return output


# ============================================================
# ★★★★★ 快速模式 ★★★★★
# ============================================================

def print_signals_only():
    """只输出买卖信号"""
    print("\n📊 快速买卖信号\n")
    
    codes_mkt = [(e["code"], e["market"]) for e in ETF_POOL]
    realtime = fetch_realtime_tencent(codes_mkt)
    
    for etf in ETF_POOL:
        hist = fetch_history_sina(etf["code"], etf["market"], days=60)
        if hist.empty or len(hist) < 20:
            continue
        
        s = generate_trade_signals(hist)
        rt = realtime.get(etf["code"], {})
        c = rt.get("change_pct")
        c_str = f" {c:+.1f}%" if c is not None else ""
        
        icons = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡", "WAIT": "⚪"}
        print(f"  {icons.get(s['signal'],'⚪')} {etf['name']:<10} → {s['signal']:<5} "
              f"评分{s['confidence']:2.0f} HV={s['hv_pct']:4.1f}% {s['phase']}{c_str}")
        print(f"      {s['reason'][:60]}")
        if s["signal"] == "BUY":
            print(f"      买={s['entry_price']:.3f} 损={s['stop_loss']:.3f} 盈={s['take_profit']:.3f} @{s['hold_days']}天")
        
        time.sleep(0.3)


def print_positions():
    """输出建议持仓及止损"""
    print("\n📊 建议持仓\n")
    
    codes_mkt = [(e["code"], e["market"]) for e in ETF_POOL]
    realtime = fetch_realtime_tencent(codes_mkt)
    
    active = []
    for etf in ETF_POOL:
        hist = fetch_history_sina(etf["code"], etf["market"], days=60)
        if hist.empty or len(hist) < 20:
            continue
        s = generate_trade_signals(hist)
        rt = realtime.get(etf["code"], {})
        
        if s["signal"] in ("BUY", "HOLD"):
            active.append((etf["name"], etf["code"], s["signal"], 
                          s["entry_price"], s["stop_loss"], s["take_profit"],
                          s["hold_days"], s["confidence"]))
        time.sleep(0.3)
    
    if not active:
        print("  (无活跃持仓建议)")
        return
    
    print(f"  {'ETF':<8} {'信号':>4} {'当前价':>8} {'止损':>8} {'止盈':>8} {'持有':>4}")
    print(f"  {'-'*45}")
    for n, c, sig, price, sl, tp, days, conf in sorted(active, key=lambda x: -x[7]):
        print(f"  {n:<8} {sig:<4} {price:>8.3f} {sl:>8.3f} {tp:>8.3f} {days:>4}天")


# ============================================================
# ★★★★★ 回测模拟 ★★★★★
# ============================================================

def run_backtest():
    """
    简单回测：用近60天数据模拟交易
    回测逻辑：
      - 每10天判断一次信号
      - 买入后模拟持有
      - 统计盈亏次数
    """
    print(f"\n{'='*70}")
    print(f"   📊 简易回测（基于近120天历史数据）")
    print(f"{'='*70}\n")
    
    codes_mkt = [(e["code"], e["market"]) for e in ETF_POOL]
    realtime = fetch_realtime_tencent(codes_mkt)
    
    total_trades = 0
    wins = 0
    total_return = 0.0
    max_dd = 0.0
    
    for etf in ETF_POOL:
        hist = fetch_history_sina(etf["code"], etf["market"], days=120)
        if hist.empty or len(hist) < 60:
            continue
        
        closes = hist["close"].values
        n = len(closes)
        
        # 模拟：每20天看一次信号，如果有BUY信号就模拟买入，20天后卖出
        trade_count = 0
        trade_wins = 0
        trade_return = 0.0
        
        for start in range(0, n - 40, 20):
            segment = hist.iloc[:start+40]
            if len(segment) < 30:
                continue
            
            signal = generate_trade_signals(segment)
            if signal["signal"] != "BUY":
                continue
            
            # 模拟买入持有20天
            end_idx = min(start + 40 + 20, n - 1)
            if end_idx <= start + 40:
                continue
            
            buy_price = closes[start + 40 - 1]
            sell_price = closes[end_idx]
            
            ret = (sell_price / buy_price - 1) * 100
            trade_count += 1
            trade_return += ret
            
            if ret > 0:
                trade_wins += 1
        
        if trade_count > 0:
            total_trades += trade_count
            wins += trade_wins
            total_return += trade_return
            avg_ret = trade_return / trade_count
            
            print(f"  {etf['name']:<10}({etf['code']}) "
                  f"交易{trade_count}次 胜率{trade_wins/trade_count*100:.0f}% "
                  f"平均收益{avg_ret:+.2f}%")
    
    if total_trades > 0:
        win_rate = wins / total_trades * 100
        avg_return = total_return / total_trades
        print(f"\n{'='*50}")
        print(f"   回测汇总")
        print(f"{'='*50}")
        print(f"   总交易: {total_trades}笔")
        print(f"   胜率: {win_rate:.0f}% ({wins}/{total_trades})")
        print(f"   平均每笔收益: {avg_return:+.2f}%")
        print(f"   总收益: {total_return:+.2f}%")
        print(f"\n   ⚠️ 注意：回测使用简化的买卖模型")
        print(f"   实际策略有择时+选ETF+仓位管理，回测仅供参考")
    else:
        print("\n   (无交易信号触发)")


# ============================================================
# 主入口
# ============================================================

if __name__ == "__main__":
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        sys.exit(0)
    
    if "--backtest" in sys.argv or "-b" in sys.argv:
        run_backtest()
    elif "--signals" in sys.argv or "-s" in sys.argv:
        print_signals_only()
    elif "--positions" in sys.argv or "-p" in sys.argv:
        print_positions()
    else:
        run_analysis()
    
    print(f"\n{'='*70}")
    print(f"   交易系统运行完成 ✅")
    print(f"{'='*70}")