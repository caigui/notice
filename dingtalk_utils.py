# -*- coding: utf-8 -*-
"""
钉钉群机器人推送工具（全工程统一版）
====================================
只依赖 requests，不需要安装 dingtalkchatbot。

基础用法
--------
    from dingtalk_utils import DingTalkNotifier
    nt = DingTalkNotifier()
    nt.send_markdown("市场数据速览", "### 正文\\n- 内容")
    nt.send_text("纯文本内容")
    nt.send_alert(正文, 标题)      # 兼容旧接口，等价 send_markdown(标题, 正文, at_all=True)

表格渲染
--------
钉钉官方 markdown 只支持「标题 / 引用 / 加粗 / 斜体 / 链接 / 图片」，
**不支持标准表格语法**。本模块提供三种风格，由 style 参数切换：

    "html"   HTML <table> 标签 —— PC 端能渲染成真正的表格（带边框），
             移动端部分版本兼容，不兼容时会把标签原样显示（较丑）
    "md"     标准 Markdown 管道表格 —— 支持时最漂亮，不支持时挤成一行
    "align"  等宽对齐纯文本 —— 任何客户端都不会乱，兼容性最好

使用方：
  - notice 下各提醒脚本（new_stock_info / qdii_arbitrage_alert / cb / stock /
    stock_exchange_alert）：`DingTalkNotifier().send_alert(message, title)`
  - market_brief/market_brief.py：按文件路径加载本模块，用 render_sections 拼表格后
    调 send_markdown(..., at_all=False)
"""

import base64
import hashlib
import hmac
import time
import unicodedata
import urllib.parse
from datetime import time as dtime
from datetime import datetime

import requests

# ----------------------------- 机器人配置 -----------------------------
# 在钉钉群 → 群设置 → 智能群助手 → 添加机器人 → 自定义 里获取
DEFAULT_WEBHOOK = (
    "https://oapi.dingtalk.com/robot/send?access_token="
    "7cc49fb6a3b71f21dd3c0b85db4982067f1fa2eb264e20e4d2b1150d29745999"
)
DEFAULT_SECRET = "SEC10d71ad2ff4ebc9c55c8e542318dbc6ad81a5a2390c29d81bd4b04abb89a2dda"

# 全局默认免打扰时段：12:30-13:00 不发送（与旧版行为一致）
# 需要调节的脚本可传 quiet_window=(dtime(x,y), dtime(x,y))，或传 None 表示全天发送
DEFAULT_QUIET_WINDOW = (dtime(12, 30), dtime(13, 0))

# 报表统一使用的中性色 / 涨跌色（html 风格下生效）
COLOR_UP = "#d93026"    # 涨：红
COLOR_DOWN = "#00873c"  # 跌：绿


# ----------------------------- 表格渲染 -----------------------------

def _disp_width(text):
    """按显示宽度计算字符长度（中文/全角算 2，其余算 1）"""
    width = 0
    for ch in str(text):
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F", "A") else 1
    return width


def _pad(text, width, align="left"):
    text = str(text)
    gap = width - _disp_width(text)
    if gap <= 0:
        return text
    if align == "right":
        return " " * gap + text
    if align == "center":
        left = gap // 2
        return " " * left + text + " " * (gap - left)
    return text + " " * gap


def _cell_text(value, color=False):
    """单元格文本：可选附带涨跌箭头/颜色"""
    text = "" if value is None else str(value)
    if not color or not text:
        return text
    stripped = text.lstrip()
    if stripped.startswith(("+", "↑")):
        return f"{text} ▲"
    if stripped.startswith(("-", "−", "↓")) and not stripped.startswith("--"):
        return f"{text} ▼"
    return text


def _cell_html(value, color=False):
    """HTML 单元格：涨跌用箭头标注（font 标签可能被钉钉过滤，箭头一定显示）"""
    text = "" if value is None else str(value)
    if not color or not text:
        return text
    stripped = text.lstrip()
    if stripped.startswith("+"):
        return f"{text} ▲"
    if stripped.startswith(("-", "−")) and not stripped.startswith("--"):
        return f"{text} ▼"
    return text


def render_html_table(headers, rows, color_cols=()):
    """HTML 表格：钉钉 PC 端可渲染为带边框的表格"""
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = []
    for r in rows:
        tds = []
        for i, v in enumerate(r):
            tds.append(f"<td>{_cell_html(v, i in color_cols)}</td>")
        body.append("<tr>" + "".join(tds) + "</tr>")
    return ('<table border="1" cellspacing="0" cellpadding="5">'
            f"<tr>{head}</tr>{''.join(body)}</table>")


def render_md_table(headers, rows, color_cols=()):
    """标准 Markdown 管道表格"""
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join([" --- "] * len(headers)) + "|"]
    for r in rows:
        cells = [_cell_text(v, i in color_cols) for i, v in enumerate(r)]
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def render_align_table(headers, rows, color_cols=()):
    """等宽对齐纯文本表格（兼容性最好）"""
    data = [[_cell_text(v, i in color_cols) for i, v in enumerate(r)] for r in rows]
    widths = []
    for i, h in enumerate(headers):
        widths.append(max([_disp_width(h)] + [_disp_width(r[i]) for r in data]))

    def line(cells, aligns):
        return "  ".join(_pad(c, widths[i], aligns[i]) for i, c in enumerate(cells))

    # 第一列左对齐，其余右对齐
    aligns = ["left"] + ["right"] * (len(headers) - 1)
    sep = "  ".join("-" * w for w in widths)
    out = [line(headers, aligns), sep] + [line(r, aligns) for r in data]
    return "\n".join(out)


def render_table(headers, rows, style="md", color_cols=()):
    if style == "md":
        return render_md_table(headers, rows, color_cols)
    if style == "align":
        return render_align_table(headers, rows, color_cols)
    return render_html_table(headers, rows, color_cols)


def render_sections(sections, style="md"):
    """把分组表格拼成一段 markdown

    sections: [(组名, 表头, 行列表, 涨跌着色列号集合)]
    每个小标题与表格之间留空行 —— 钉钉的 markdown 解析要求表格前有空行才会
    识别成表格，否则会当成普通文本一行行铺开。
    """
    parts = []
    for title, headers, rows, color_cols in sections:
        parts.append(f"**{title}**")
        parts.append(render_table(headers, rows, style=style, color_cols=color_cols))
        parts.append("")
    return "\n\n".join(p for p in parts if p != "").replace("\n\n\n", "\n\n")


# ----------------------------- 发送 -----------------------------

class DingTalkNotifier:
    """钉钉群机器人（零第三方依赖，自带加签）"""

    def __init__(self, webhook=DEFAULT_WEBHOOK, secret=DEFAULT_SECRET,
                 quiet_window=DEFAULT_QUIET_WINDOW, timeout=15):
        """
        quiet_window: (start, end) 免打扰时段，例如 (dtime(12, 30), dtime(13, 0))，
                      None 表示全天发送。窗口内 send_* 返回 False 且不发。
                      默认 12:30-13:00，与旧版硬编码行为保持一致。
        """
        self.webhook = webhook
        self.secret = secret
        self.quiet_window = quiet_window
        self.timeout = timeout

    # --- 内部 ---
    def _in_quiet_window(self):
        if not self.quiet_window:
            return False
        start, end = self.quiet_window
        now = datetime.now().time()
        return start <= now < end

    def _signed_url(self):
        if not self.secret:
            return self.webhook
        timestamp = str(round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{self.secret}"
        digest = hmac.new(self.secret.encode("utf-8"),
                          string_to_sign.encode("utf-8"),
                          hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(digest))
        sep = "&" if "?" in self.webhook else "?"
        return f"{self.webhook}{sep}timestamp={timestamp}&sign={sign}"

    def _post(self, payload):
        if self._in_quiet_window():
            print(f"[DingTalk] {datetime.now():%H:%M} 处于免打扰时段，跳过发送")
            return False
        try:
            resp = requests.post(self._signed_url(), json=payload, timeout=self.timeout)
            data = resp.json() if resp.content else {}
            if data.get("errcode") == 0:
                return True
            print(f"[DingTalk] 发送失败：{data}")
            return False
        except Exception as e:  # 网络/签名/解析异常都不让主流程崩
            print(f"[DingTalk] 发送异常：{type(e).__name__}: {e}")
            return False

    # --- 对外 ---
    def send_markdown(self, title, text, at_all=False):
        return self._post({
            "msgtype": "markdown",
            "markdown": {"title": title, "text": text},
            "at": {"isAtAll": bool(at_all)},
        })

    def send_text(self, content, at_all=False):
        return self._post({
            "msgtype": "text",
            "text": {"content": content},
            "at": {"isAtAll": bool(at_all)},
        })

    def send_alert(self, message, title, at_all=True):
        """兼容旧接口：send_alert(message, title)"""
        return self.send_markdown(title, message, at_all=at_all)


# ----------------------------- 自测 -----------------------------

def main():
    nt = DingTalkNotifier(quiet_window=None)   # 自测不受免打扰影响
    rows = [
        ["两市成交额", "21,180 亿", "—"],
        ["主力净流入", "-352 亿", "-1.20%"],
        ["沪深300 PE", "12.8", "+0.35%"],
    ]
    demo = ["### 钉钉推送样式测试", ""]
    for style, label in [("html", "A · HTML 表格"), ("md", "B · Markdown 管道表格"),
                         ("align", "C · 等宽对齐文本")]:
        demo.append(f"**{label}**")
        demo.append(render_table(["指标", "数值", "涨跌幅"], rows, style=style, color_cols={2}))
        demo.append("")
    ok = nt.send_markdown("钉钉推送样式测试", "\n".join(demo), at_all=False)
    print("发送成功" if ok else "发送失败")


if __name__ == "__main__":
    main()
