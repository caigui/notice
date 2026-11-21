#!/usr/bin/env python3
"""
ETF波动率趋势筛选工具
=======================
基于微信公众号文章核心思想：
  文1《波动率——金融市场最核心的指标》
  文2《场内的ETF策略我终于做好了》

方法论：
  1. 20只ETF池（股债商）
  2. 大级别择时：多头占比>50%才入场
  3. 波动率调整趋势指标（比均线更好）
  4. 买点：沉寂后爆发（波动率突然放大）
  5. HV/IV靠拢度分析（遛狗理论）

数据源：
  - 历史K线: 新浪财经 free API
  - 实时行情: 腾讯证券 free API

用法：
  python3 etf_volatility_screener.py           # 完整筛选
  python3 etf_volatility_screener.py --watch   # 快速多头列表
  python3 etf_volatility_screener.py --report  # 周报摘要
"""

import requests
import json
import time
import pandas as pd
import numpy as np
import os
import sys
from datetime import datetime, timedelta

# ============ 配置 ============
OUTPUT_DIR = "/root/etf_screening"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 20只ETF池（股债商）
ETF_POOL = [
    # 宽基指数（7只）
    {"code": "510300", "name": "沪深300ETF",  "market": "sh", "category": "宽基"},
    {"code": "510050", "name": "上证50ETF",   "market": "sh", "category": "宽基"},
    {"code": "159915", "name": "创业板ETF",   "market": "sz", "category": "宽基"},
    {"code": "588000", "name": "科创50ETF",   "market": "sh", "category": "宽基"},
    {"code": "510500", "name": "中证500ETF",  "market": "sh", "category": "宽基"},
    {"code": "512100", "name": "中证1000ETF", "market": "sh", "category": "宽基"},
    {"code": "159949", "name": "创业板50ETF", "market": "sz", "category": "宽基"},
    # 行业ETF（7只）
    {"code": "512480", "name": "半导体ETF",   "market": "sh", "category": "行业"},
    {"code": "515050", "name": "5G ETF",      "market": "sh", "category": "行业"},
    {"code": "512880", "name": "证券ETF",     "market": "sh", "category": "行业"},
    {"code": "159865", "name": "养殖ETF",     "market": "sz", "category": "行业"},
    {"code": "512010", "name": "医药ETF",     "market": "sh", "category": "行业"},
    {"code": "515030", "name": "新能源车ETF", "market": "sz", "category": "行业"},
    {"code": "159766", "name": "旅游ETF",     "market": "sz", "category": "行业"},
    # 商品（3只）
    {"code": "159981", "name": "能源化工ETF", "market": "sz", "category": "商品"},
    {"code": "159980", "name": "有色ETF",     "market": "sz", "category": "商品"},
    {"code": "518880", "name": "黄金ETF",     "market": "sh", "category": "商品"},
    # 债券（2只）
    {"code": "511380", "name": "国债ETF",     "market": "sh", "category": "债券"},
    {"code": "511880", "name": "银华日利ETF", "market": "sh", "category": "债券"},
    # 跨境（1只）
    {"code": "513100", "name": "纳指ETF",     "market": "sh", "category": "跨境"},
]

# 波动率分档（年化%）
VOL_LOW     = 15
VOL_MEDIUM  = 25
VOL_HIGH    = 40
VOL_EXTREME = 60

# 新浪股票代码映射（sh=0. / sz=1.）
def sina_code(code, market):
    m = market.lower()
    if m == 'sh':
        return f"sh{code}"
    elif m == 'sz':
        return f"sz{code}"
    return f"sh{code}"


# ============ 数据获取 ============

def fetch_history_sina(code, market, days=120):
    """
    从新浪财经获取历史日K线
    
    接口: money.finance.sina.com.cn/api/json_v2.php/CN_MarketData.getKLineData
    参数: symbol=sh510300, scale=240(日线), datalen=120
    """
    sym = sina_code(code, market)
    url = ("https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
           f"CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=no&datalen={days}")
    
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                time.sleep(1)
                continue
            data = resp.json()
            if not data or len(data) < 5:
                time.sleep(1)
                continue
            
            rows = []
            for item in data:
                rows.append({
                    "date": item.get("day", ""),
                    "open": float(item.get("open", 0)),
                    "high": float(item.get("high", 0)),
                    "low": float(item.get("low", 0)),
                    "close": float(item.get("close", 0)),
                    "volume": float(item.get("volume", 0)),
                })
            return pd.DataFrame(rows)
        except Exception as e:
            if attempt < 2:
                time.sleep(1.5)
                continue
            return pd.DataFrame()
    return pd.DataFrame()


def fetch_realtime_tencent(codes_with_market):
    """
    从腾讯证券获取实时行情（群取模式）
    接口: web.sqt.gtimg.cn/q=sh510300,sh510050,...
    """
    if not codes_with_market:
        return {}
    
    codes_str = ",".join([f"{m}{c}" for c, m in codes_with_market])
    url = f"https://web.sqt.gtimg.cn/q={codes_str}"
    headers = {"Referer": "https://finance.qq.com"}
    
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                time.sleep(1)
                continue
            # 腾讯返回: v_sh510300="...";v_sz159915="...";
            # 解析多个变量
            results = {}
            for line in resp.text.split(";"):
                line = line.strip()
                if not line or "=" not in line:
                    continue
                # v_sh510300="..."
                try:
                    var_name = line.split("=")[0].strip()
                    val = "=".join(line.split("=")[1:]).strip().strip('"')
                    parts = val.split("~")
                    if len(parts) >= 40:
                        code = parts[2]
                        results[code] = {
                            "name": parts[1],
                            "price": float(parts[3]) if parts[3] else 0,
                            "change_pct": float(parts[32]) if parts[32] else 0,
                            "change_amt": float(parts[31]) if parts[31] else 0,
                            "high": float(parts[33]) if parts[33] else 0,
                            "low": float(parts[34]) if parts[34] else 0,
                            "open": float(parts[5]) if parts[5] else 0,
                            "volume": float(parts[6]) if parts[6] else 0,
                            "turnover": float(parts[37]) if parts[37] else 0,
                        }
                except:
                    continue
            return results
        except Exception as e:
            if attempt < 2:
                time.sleep(1)
                continue
            return {}
    return {}


def fetch_etf_data_robust(code, market, name="", retries=3):
    """
    层层递进获取ETF数据：
    1. 新浪历史K线
    2. 如果新浪失败，等待后再试
    """
    for attempt in range(retries):
        hist = fetch_history_sina(code, market, days=120)
        if not hist.empty and len(hist) >= 20:
            return hist
        if attempt < retries - 1:
            time.sleep(1)
    return pd.DataFrame()


# ============ 核心分析函数 ============

def calc_daily_returns(df):
    """日收益率序列"""
    if df.empty or len(df) < 2:
        return np.array([])
    closes = df["close"].values
    return np.diff(closes) / closes[:-1]


def calc_historical_volatility(df, period=20):
    """
    历史波动率(HV) - 文章定义：过去N天涨跌幅的标准差
    年化后返回
    """
    if df.empty or len(df) < period:
        return 0.0, pd.Series(dtype=float)
    
    returns = calc_daily_returns(df)
    if len(returns) < period:
        return 0.0, pd.Series(dtype=float)
    
    vol_series = pd.Series(returns).rolling(window=period).std()
    current_vol = vol_series.iloc[-1] if not vol_series.empty and pd.notna(vol_series.iloc[-1]) else 0.0
    current_vol *= (252 ** 0.5)  # 年化
    
    return current_vol, vol_series


def calc_volatility_phase(df, lookback=60):
    """
    判断价格所处的波动率周期阶段
    
    文章核心框架：
    上涨初期(暗流涌动) -> 加速上涨 -> 筑顶(IV走平/HV追上) -> 横盘震荡 -> 沉寂
    """
    if df.empty or len(df) < lookback:
        return "数据不足", "unknown", 1.0
    
    returns = calc_daily_returns(df)
    if len(returns) < 40:
        return "数据不足", "unknown", 1.0
    
    # 近期（近20天）vs 中期（前40天到前20天）波动率
    r_recent = returns[-20:] if len(returns) >= 20 else returns
    r_mid = returns[-40:-20] if len(returns) >= 40 else returns[:20]
    
    hv_recent = np.std(r_recent) * (252 ** 0.5) if len(r_recent) > 1 else 0
    hv_mid = np.std(r_mid) * (252 ** 0.5) if len(r_mid) > 1 else 0
    
    # 滚动波动率趋势
    vol_series = pd.Series(returns).rolling(window=20).std()
    vol_series_ann = vol_series * (252 ** 0.5)
    
    if len(vol_series_ann) >= 10:
        recent_avg = vol_series_ann.iloc[-5:].mean()
        mid_avg = vol_series_ann.iloc[-15:-5].mean() if len(vol_series_ann) >= 15 else recent_avg
    else:
        recent_avg = hv_recent
        mid_avg = hv_mid
    
    # 波动率方向
    if pd.notna(recent_avg) and pd.notna(mid_avg) and mid_avg > 0:
        if recent_avg > mid_avg * 1.3:
            hv_trend = "up"
        elif recent_avg < mid_avg * 0.7:
            hv_trend = "down"
        else:
            hv_trend = "steady"
    else:
        hv_trend = "steady"
    
    # 价格趋势
    closes = df["close"].values
    price_trend = (closes[-1] / closes[-20] - 1) if len(closes) >= 20 else 0
    
    vol_ratio = hv_recent / hv_mid if hv_mid > 0.001 else 1.0
    hv_annual = hv_recent * 100
    
    # === 阶段判断 ===
    if hv_annual < VOL_LOW and abs(price_trend) < 0.03:
        phase = "沉寂期"
    elif hv_annual < VOL_MEDIUM and price_trend > 0.01 and hv_trend == "up":
        phase = "暗流涌动"  # 表面平静但波动率在走高
    elif vol_ratio > 1.5 and price_trend > 0:
        phase = "爆发期"
    elif hv_annual > VOL_HIGH and price_trend > 0.05 and hv_trend == "up":
        phase = "加速上涨"
    elif hv_annual > VOL_HIGH and price_trend < 0.04 and hv_trend == "steady":
        phase = "筑顶期"
    elif hv_annual > VOL_EXTREME and price_trend < -0.05:
        phase = "恐慌期"
    elif hv_trend == "down" and price_trend > -0.03:
        phase = "横盘震荡"
    else:
        phase = "震荡期"
    
    return phase, hv_trend, vol_ratio


def calc_trend_strength_vol_adjusted(df, period=20):
    """
    波动率调整后的趋势强度（文章核心）
    比均线更好的趋势指标
    """
    if df.empty or len(df) < period:
        return 0.0, 0
    
    closes = df["close"].values[-period:]
    if len(closes) < 5:
        return 0.0, 0
    
    # 1. 线性回归斜率
    x = np.arange(len(closes))
    slope = np.polyfit(x, closes, 1)[0]
    
    # 2. 波动率计算
    returns = np.diff(closes) / closes[:-1]
    hv = np.std(returns) * (252 ** 0.5) if len(returns) > 0 else 0
    
    # 3. 价格与均线位置
    ma = np.mean(closes)
    price = closes[-1]
    
    if price > ma and slope > 0:
        direction = 1
    elif price < ma and slope < 0:
        direction = -1
    else:
        direction = 0
    
    # 4. 趋势强度（波动率调整）
    price_std = np.std(closes)
    base_strength = slope / (price_std * 2 / period) if price_std > 0 else 0
    
    if direction == 1 and hv > 0.2:
        strength = min(base_strength * 1.3, 1.0)
    elif direction == -1 and hv > 0.2:
        strength = max(base_strength * 1.3, -1.0)
    else:
        strength = base_strength
    
    return max(-1.0, min(1.0, strength)), direction


def calc_buy_signal(df):
    """
    沉寂后爆发买入信号（文章核心买点）
    
    条件：
    1. 此前波动率偏低（沉寂）
    2. 近期波动率放大（爆发）
    3. 价格方向为多
    """
    if df.empty or len(df) < 50:
        return 0, "数据不足"
    
    returns = calc_daily_returns(df)
    if len(returns) < 40:
        return 0, "数据不足"
    
    # 前30天波动率（沉寂期）
    r1 = returns[-40:-20] if len(returns) >= 40 else returns[-30:-15]
    vol_before = np.std(r1) if len(r1) > 1 else 0
    
    # 近20天波动率
    r2 = returns[-20:] if len(returns) >= 20 else returns
    vol_now = np.std(r2) if len(r2) > 1 else 0
    
    activity_ratio = vol_now / vol_before if vol_before > 0 else 1.0
    
    closes = df["close"].values
    price_5d = closes[-1] / closes[-5] - 1 if len(closes) >= 5 else 0
    price_20d = closes[-1] / closes[-20] - 1 if len(closes) >= 20 else 0
    
    signals = []
    score = 0
    
    if activity_ratio > 1.5:
        signals.append(f"放量{activity_ratio:.1f}x")
        score += 30
    if price_5d > 0.02:
        signals.append(f"5日涨{price_5d*100:.0f}%")
        score += 25
    if price_20d > 0.03:
        score += 10
    
    # 波动率不能太高（避开创顶）
    hv, _ = calc_historical_volatility(df, 20)
    if hv < 0.6:
        score += 15
    else:
        score -= 15
    
    # 在均线上
    if len(closes) >= 20 and closes[-1] > np.mean(closes[-20:]):
        score += 15
    
    if score >= 60:
        return score, "爆发买入 | " + " | ".join(signals[:3])
    elif score >= 30:
        return score, "关注中 | " + " | ".join(signals[:2])
    return score, "观望"


def calc_hv_convergence(df, lookback=60):
    """
    HV靠拢度分析（遛狗理论的简化版）
    
    用短期(5日)波动率 vs 长期(60日)波动率的关系
    模拟"实际波动率 vs 预期波动率"的收敛/发散
    """
    if df.empty or len(df) < lookback:
        return 1.0, "数据不足"
    
    returns = calc_daily_returns(df)
    if len(returns) < lookback:
        return 1.0, "数据不足"
    
    hv_short = np.std(returns[-5:]) * (252 ** 0.5) if len(returns) >= 5 else 0
    hv_long = np.std(returns[-lookback:]) * (252 ** 0.5)
    
    ratio = hv_short / hv_long if hv_long > 0 else 1.0
    
    if ratio > 1.5:
        note = "实际波幅远超正常，回归压力大"
    elif ratio > 1.2:
        note = "短期偏活跃，有回归倾向"
    elif ratio < 0.7:
        note = "异常平静，变盘前兆"
    elif ratio < 0.85:
        note = "波动偏低"
    else:
        note = "均衡状态"
    
    return ratio, note


# ============ 主筛选 ============

def screen_etfs():
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    
    print(f"\n{'='*70}")
    print(f"   ETF波动率趋势筛选报告")
    print(f"   生成: {now_str}")
    print(f"   数据源: 新浪(历史K线) + 腾讯(实时)")
    print(f"{'='*70}\n")
    
    all_results = []
    
    # 1. 获取实时行情
    print("📡 获取实时行情（腾讯证券）...")
    codes_mkt = [(e["code"], e["market"]) for e in ETF_POOL]
    realtime = fetch_realtime_tencent(codes_mkt)
    print(f"   → {len(realtime)}只ETF实时数据\n")
    time.sleep(0.3)
    
    # 2. 逐个分析
    print("📊 获取历史K线并计算指标（新浪财经）...\n")
    
    bullish_count = 0
    buy_candidates = []
    
    for etf in ETF_POOL:
        code = etf["code"]
        name = etf["name"]
        market = etf["market"]
        category = etf["category"]
        
        print(f"  [{category}] {name}({code})...", end=" ")
        
        hist = fetch_etf_data_robust(code, market, name)
        if hist.empty or len(hist) < 30:
            print("❌ 数据不足")
            time.sleep(0.2)
            continue
        
        # 计算核心指标
        strength, direction = calc_trend_strength_vol_adjusted(hist)
        phase, hv_trend, vol_ratio = calc_volatility_phase(hist)
        hv_current, _ = calc_historical_volatility(hist, 20)
        hv_pct = round(hv_current * 100, 1)
        convergence_ratio, conv_note = calc_hv_convergence(hist)
        buy_score, buy_desc = calc_buy_signal(hist)
        
        # 近期收益
        closes = hist["close"].values
        ret_5d  = round((closes[-1] / closes[-5] - 1) * 100, 2) if len(closes) >= 5 else 0
        ret_20d = round((closes[-1] / closes[-20] - 1) * 100, 2) if len(closes) >= 20 else 0
        ret_60d = round((closes[-1] / closes[-60] - 1) * 100, 2) if len(closes) >= 60 else 0
        
        # 最大回撤
        max_dd = 0
        if len(closes) > 1:
            peak = closes[0]
            for v in closes:
                if v > peak:
                    peak = v
                dd = (peak - v) / peak * 100
                if dd > max_dd:
                    max_dd = dd
        
        # 实时数据
        rt = realtime.get(code, {})
        change_today = rt.get("change_pct")
        
        # 方向
        if direction == 1:
            bullish_count += 1
            dir_icon = "🟢"
        elif direction == -1:
            dir_icon = "🔴"
        else:
            dir_icon = "⚪"
        
        is_buy = buy_score >= 60 and direction == 1
        is_watch = direction == 1 and strength > 0.2
        
        if is_buy:
            buy_candidates.append((name, code, buy_score, strength, hv_pct, phase, buy_desc))
        
        result = {
            "code": code, "name": name, "category": category,
            "direction": "📈多头" if direction == 1 else ("📉空头" if direction == -1 else "⚪中性"),
            "strength": round(strength, 3),
            "phase": phase, "hv_trend": hv_trend,
            "hv_annual": hv_pct,
            "vol_ratio": round(vol_ratio, 2),
            "convergence": round(convergence_ratio, 2),
            "conv_note": conv_note,
            "buy_score": buy_score, "buy_desc": buy_desc,
            "ret_5d": ret_5d, "ret_20d": ret_20d, "ret_60d": ret_60d,
            "max_dd": round(max_dd, 2),
            "change_today": round(change_today, 2) if change_today is not None else None,
        }
        all_results.append(result)
        
        marker = "🚀" if is_buy else ("👀" if is_watch else "  ")
        change_str = f"今{change_today:+.1f}%" if change_today is not None else ""
        print(f"{marker} {dir_icon} 强度={strength:.2f} HV={hv_pct}% "
              f"{phase:<5} {ret_5d:+.1f}%/{ret_20d:+.1f}% {change_str}")
        if is_buy:
            print(f"      >> {buy_desc[:70]}")
        
        time.sleep(0.3)
    
    # === 汇总输出 ===
    if not all_results:
        print("\n❌ 未获取到有效数据")
        return None
    
    df_result = pd.DataFrame(all_results)
    total = len(df_result)
    bearish = sum(1 for r in all_results if r["direction"] == "📉空头")
    neutral = total - bullish_count - bearish
    
    print(f"\n{'='*70}")
    print(f"    📈 大级别择时（池中多头需>50%才允许入场）")
    print(f"{'='*70}")
    bullish_ratio = bullish_count / total
    print(f"   多头: {bullish_count}/{total} = {bullish_ratio*100:.0f}%")
    if bullish_ratio > 0.5:
        print(f"   ✅ 择时结论: 可以入场")
    else:
        print(f"   ❌ 择时结论: 观望为宜")
    
    print(f"\n{'='*70}")
    print(f"    🏆 买入信号（沉寂后爆发候选）")
    print(f"{'='*70}")
    if buy_candidates:
        for name, code, score, st, hv, ph, desc in sorted(buy_candidates, key=lambda x: -x[2]):
            print(f"   🚀 {name:<10}({code}) 评分={score:.0f} 强度={st:.2f} HV={hv}% {ph}")
            print(f"       {desc}")
    else:
        print("   (无符合条件的买入信号)")
    
    print(f"\n{'='*70}")
    print(f"    👀 关注列表（多头且强度>0.2）")
    print(f"{'='*70}")
    watch_list = [r for r in all_results if r["direction"] == "📈多头" and r["strength"] > 0.2]
    watch_list.sort(key=lambda x: -x["strength"])
    if watch_list:
        for r in watch_list:
            print(f"   {r['name']:<10}({r['code']}) [{r['category']}] "
                  f"强度={r['strength']:.2f} HV={r['hv_annual']}% "
                  f"{r['phase']:<5} 5日={r['ret_5d']:+.1f}% 60日={r['ret_60d']:+.1f}%"
                  + (f" 今{r['change_today']:+.1f}%" if r['change_today'] is not None else ""))
    
    print(f"\n{'='*70}")
    print(f"    ⚠️ 极端波动预警（HV>{VOL_EXTREME}%）")
    print(f"{'='*70}")
    extreme = [r for r in all_results if r["hv_annual"] > VOL_EXTREME]
    if extreme:
        for r in extreme:
            print(f"   🚨 {r['name']:<10}({r['code']}) HV={r['hv_annual']}% "
                  f"{r['phase']} 强度={r['strength']:.2f}")
    else:
        print("   (无)")
    
    # 阶段分布
    from collections import Counter
    phase_dist = Counter(r["phase"] for r in all_results)
    print(f"\n{'='*70}")
    print(f"    📋 波动率阶段分布")
    print(f"{'='*70}")
    for phase, count in phase_dist.most_common():
        print(f"   {phase}: {count}只")
    
    # 保存CSV
    csv_columns = ["code", "name", "category", "direction", "strength", 
                   "phase", "hv_annual", "buy_score", "buy_desc",
                   "ret_5d", "ret_20d", "ret_60d", "max_dd", "change_today"]
    df_save = df_result[csv_columns].copy()
    output_csv = os.path.join(OUTPUT_DIR, f"screening_{datetime.now().strftime('%Y%m%d_%H%M')}.csv")
    df_save.to_csv(output_csv, index=False, encoding='utf-8-sig')
    print(f"\n📁 详细数据: {output_csv}")
    
    return df_result


def quick_watch():
    """快速多头列表（周报参考）"""
    print("\n📌 快速查看多头ETF\n")
    
    codes_mkt = [(e["code"], e["market"]) for e in ETF_POOL]
    realtime = fetch_realtime_tencent(codes_mkt)
    
    bullish_list = []
    for etf in ETF_POOL:
        print(f"  {etf['name']}({etf['code']})...", end=" ")
        hist = fetch_etf_data_robust(etf["code"], etf["market"])
        if hist.empty or len(hist) < 20:
            print("跳过")
            continue
        
        strength, direction = calc_trend_strength_vol_adjusted(hist)
        phase, _, _ = calc_volatility_phase(hist)
        hv, _ = calc_historical_volatility(hist, 20)
        buy_score, _ = calc_buy_signal(hist)
        
        rt = realtime.get(etf["code"], {})
        change = rt.get("change_pct")
        change_str = f"今{change:+.1f}%" if change is not None else ""
        
        if direction == 1:
            bullish_list.append((etf["name"], etf["code"], etf["category"],
                                strength, phase, hv*100, buy_score, change_str))
            print(f"🟢 强度={strength:.2f} HV={hv*100:.0f}% {phase} {change_str}")
        elif direction == -1:
            print(f"🔴 空头")
        else:
            print(f"⚪ 中性")
        time.sleep(0.3)
    
    print(f"\n{'='*50}")
    print(f"多头ETF: {len(bullish_list)}只")
    print(f"{'='*50}")
    for i, (n,c,cat,st,ph,hv,bs,chg) in enumerate(sorted(bullish_list, key=lambda x: -x[3])):
        m = "🚀" if bs >= 60 else "👀" if st > 0.3 else "  "
        print(f"  {i+1:2d}. {m} {n:<10}({c}) [{cat}] 强度={st:.2f} HV={hv:.0f}% {ph} {chg}")


def print_report():
    """简洁周报摘要"""
    print("\n📊 ETF周报摘要\n")
    
    codes_mkt = [(e["code"], e["market"]) for e in ETF_POOL]
    realtime = fetch_realtime_tencent(codes_mkt)
    
    for etf in ETF_POOL:
        hist = fetch_etf_data_robust(etf["code"], etf["market"])
        if hist.empty or len(hist) < 20:
            continue
        strength, direction = calc_trend_strength_vol_adjusted(hist)
        phase, _, _ = calc_volatility_phase(hist)
        hv, _ = calc_historical_volatility(hist, 20)
        
        d = "多" if direction == 1 else ("空" if direction == -1 else "中")
        rt = realtime.get(etf["code"], {})
        c = rt.get("change_pct")
        chg = f"{c:+.1f}%" if c is not None else ""
        
        print(f"  {etf['name']:<10} {d} | 强度{strength:.2f} | HV{hv*100:.0f}% | {phase} | {chg}")
        time.sleep(0.2)


if __name__ == "__main__":
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        sys.exit(0)
    if "--watch" in sys.argv or "-w" in sys.argv:
        quick_watch()
    elif "--report" in sys.argv or "-r" in sys.argv:
        print_report()
    else:
        screen_etfs()
    print(f"\n{'='*70}")
    print("✅ 完成")
    print(f"{'='*70}")