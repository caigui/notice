import time
import os
import json
import re
from datetime import date
from globalVar import log
from stock_info import StockInfo
from wechatPublicCountSendMessage import SendMessage
from stock_config import StockConfig
import requests
from dingtalk_utils import DingTalkNotifier
import asyncio
import date_utils

_STATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state")
_STATE_FILE = os.path.join(_STATE_DIR, "stock_notice_state.json")


def _read_sent_keys():
    try:
        with open(_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        if data.get("date") == date.today().isoformat():
            return set(data.get("sent") or [])
    except Exception:
        pass
    return set()


def _mark_sent(key):
    try:
        keys = _read_sent_keys()
        keys.add(key)
        if not os.path.isdir(_STATE_DIR):
            os.makedirs(_STATE_DIR)
        tmp = _STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"date": date.today().isoformat(), "sent": sorted(keys)},
                      f, ensure_ascii=False, indent=2)
        os.replace(tmp, _STATE_FILE)
    except Exception as e:
        log.logger.error(f"记录事件提醒状态失败: {e}")


def _offer_price(notes, price_max):
    m = re.search(r"要约价\s*[:：]?\s*([0-9]+(?:\.[0-9]+)?)", notes or "")
    return float(m.group(1)) if m else price_max


def _event_message(code, cfg, current, direction):
    """把事件类型 + 触发原因写进钉钉正文，而不是只有一句 Price Alert。"""
    ev = cfg.get("type", "配债")
    name = cfg.get("name") or code
    notes = cfg.get("notes") or ""
    pmin, pmax = cfg["price_min"], cfg["price_max"]
    side = ("跌破关注下界 %s" % pmin) if direction == "below" else ("突破关注上界 %s" % pmax)

    if ev == "配债":
        text = f"**配债机会** · {name}({code}) 现价 **{current}**，{side}"
        if notes:
            text += f"\n- 配债参数：{notes}"
        return text

    if ev in ("要约收购", "私有化", "吸收合并"):
        offer = _offer_price(notes, pmax)
        text = (f"**{ev}机会** · {name}({code}) 现价 **{current}**，{side}")
        if current:
            spread = (offer - current) / current * 100.0
            text += f"\n- 参考价 {offer}，隐含价差 **{spread:+.2f}%**"
        if notes:
            text += f"\n- 备注：{notes}"
        return text

    text = f"**{ev}机会** · {name}({code}) 现价 **{current}**，{side}"
    if notes:
        text += f"\n- 备注：{notes}"
    return text


"""股票监控类,达到设定价格进行提醒"""
class StockMonitor:
    def __init__(self, interactive_prompt):
        """初始化股票监控类"""
        self.interactive_prompt = interactive_prompt
        self.alert_price = interactive_prompt.get_stock_id_and_price()
        self.stockInfo = StockInfo(interactive_prompt.get_stock_exchange(), interactive_prompt.get_se_and_stock_id())
        self.notifier = DingTalkNotifier()
        self.token_time = int(str(time.time()).split(".")[0])  # 保存公众号token获取时间
    def check_current_price(self):
        """检查所有股票的现价是否达到要提醒的价位."""
        print("Checking current price...")
        # print(self.stockInfo.stock_data)
        for data in self.stockInfo.stock_data:
            stock_code = data[1]
            current_price = data[2]
            cfg = self.alert_price.get(stock_code)
            if not cfg:
                continue

            cfg.setdefault('alert_count', 0)
            cfg.setdefault('last_alert_time', 0)
            ev = cfg.get('type', '配债')
            sent_key = "%s|%s" % (stock_code, ev)
            if sent_key in _read_sent_keys():
                continue                       # 同日同类型已提醒（跨进程有效）

            price_min, price_max = cfg['price_min'], cfg['price_max']
            if current_price <= price_min:
                alert_type = "below"
            elif current_price >= price_max:
                alert_type = "above"
            else:
                continue

            current_time = time.time()
            if current_time - cfg['last_alert_time'] < 300:
                continue

            message = _event_message(stock_code, cfg, current_price, alert_type)
            ok = self.notifier.send_alert(message, "股票事件机会提醒")
            print(message)
            log.logger.info(f"{ev} {stock_code} 触发提醒，现价 {current_price}，发送={ok}")
            if ok:
                cfg['alert_count'] += 1
                cfg['last_alert_time'] = current_time
                _mark_sent(sent_key)            # 只在推送成功后落状态

    async def loop_check(self, interval_seconds=300, max_retries=3):
        """异步循环检查股票价格，直到达到指定的告警条件"""
        retry_count = 0
        while True:
            if date_utils.is_trading_time():
                try:
                    # 获取最新的股票信息
                    self.stockInfo.get_all_stock_info()
                    self.check_current_price()  # 检查股票价格
                    retry_count = 0  # 如果成功，重置重试计数器
                    log.logger.info("Stock info fetched and price checked successfully.")
                except requests.RequestException as e:
                    retry_count += 1
                    log.logger.error(f"Data fetching failed, attempt {retry_count}: {e}")
                    if retry_count >= max_retries:
                        log.logger.critical("Network request failed multiple times, exiting the program.")
                        break  # 达到最大重试次数时退出循环
                await asyncio.sleep(interval_seconds)  # 使用 asyncio.sleep 替代 time.sleep

# Main function to start the monitoring
if __name__ == "__main__":
    interactive_prompt = StockConfig()
    stock_monitor = StockMonitor(interactive_prompt)

    # Start checking the stock prices in a loop
    asyncio.run(stock_monitor.loop_check(interval_seconds=300))  # Check every 5 minutes (300 seconds)
