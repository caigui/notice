#!/bin/bash

# 14 9 * * 1-5 /data/caigui/notice/main.sh >> /data/caigui/notice/run_main.log 2>&1
# 获取当前时间的小时和分钟
current_time=$(date +%H:%M)

# 设置开始和结束时间
start_time="09:14"
end_time="15:00"

# 设置 Python 脚本路径（请根据实际路径修改）

SCRIPT_PATH="/data/caigui/notice/main.py"

# 启动 Python 脚本并记录其 PID
python3 "$SCRIPT_PATH" &
PYTHON_PID=$!

# 将 PID 保存到文件以便后续管理
echo $PYTHON_PID > /tmp/python_script.pid

# 计算从 9:14 到 15:00 的秒数
duration=$(( ($(date -d "$end_time" +%s) - $(date -d "$current_time" +%s)) ))

# 等待指定的持续时间
sleep $duration

# 使用 kill 命令终止 Python 进程
if ps -p $PYTHON_PID > /dev/null; then
    kill $PYTHON_PID
    echo "Python 进程已终止"
fi

# 清理 PID 文件
rm -f /tmp/python_script.pid
