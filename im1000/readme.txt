pip install pandas numpy matplotlib requests akshare lxml
python im1000_panel.py --all       # 首次约 50 个月 ZIP，合计 ~20MB
python im1000_panel.py --update    # 之后每天

# 风险溢价三图（中证1000 / 沪深300 / 中证500），免费数据源、无需 token
python risk_premium_panel.py           # 首次全量抓数 + 出图
python risk_premium_panel.py --update  # 日常增量（只刷近两年国债收益率）
python risk_premium_panel.py --plot    # 断网时读本地 CSV 重画图
python risk_premium_panel.py --wind-scale  # 按截图数值校准盈利收益率系数
# 产物：plot_rp_000852.png / plot_rp_000300.png / plot_rp_000905.png
# 口径：风险溢价 = 100/PE(TTM) - 中债10年国债收益率；危险/中位/机会 = 20/50/80 分位
# 数据：中证指数官网 perf/index-perf + 中国债券信息网 historyQuery

绿线以上持续大买，绿线和灰线之间小买，灰线以下不买，红线以下持续卖出股指，买入国债。