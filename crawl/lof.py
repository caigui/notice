import time
import requests
import re
import pytz
import json
import configparser
from datetime import datetime
import os

class LOF:
    def __init__(self):
        self.cp = configparser.ConfigParser()
        # 获取当前脚本的目录路径
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # 拼接 config.cfg 的路径
        config_path = os.path.join(current_dir, "config.cfg")
        self.cp.read(config_path, encoding="utf8")
        if "LOF" and "content" not in list(self.cp.sections()):
            raise Exception("Please create config.cfg first")
        self.content = self.cp._sections['content']
        self.LOFList = json.loads(self.cp.get('LOF','LOFList'))
        if self.LOFList:
            self.LOFList.sort()
        self.disLimit = self.cp.getfloat('LOF', 'disLimit')
        self.preLimit = self.cp.getfloat('LOF', 'preLimit')
        if self.disLimit < 0.: self.disLimit = 0.
        if self.preLimit > 0.: self.preLimit = 0.
        self.apiKey = self.cp.get('LOF', 'apiKey')

        self.session = requests.Session()
        header = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/71.0.3578.80 Safari/537.36",}
        self.session.headers.update(header)
        # self.urlBase = "https://www.jisilu.cn/data/lof/detail/"
        self.urlLOF = ["https://www.jisilu.cn/data/lof/stock_lof_list/?___jsl=LST___t="
                       ,"https://www.jisilu.cn/data/lof/index_lof_list/?___jsl=LST___t="
                        ,"https://www.jisilu.cn/data/qdii/qdii_list/C?rp=22&page=1&___jsl=LST___t="
                        ,"https://www.jisilu.cn/data/qdii/qdii_list/E?rp=22&page=1&___jsl=LST___t="
                        ,"https://www.jisilu.cn/data/qdii/qdii_list/A?rp=22&page=1&___jsl=LST___t="]




    def getInfo(self, id):
        all_rows = []
        for url in self.urlLOF:
            r = self.session.get(url + str(int(time.time())*1000))
            if r.status_code == 200:
                r = r.json()
                all_rows.extend([row["cell"] for row in r["rows"]])
            else:
                return
        rows = all_rows #Fetch all rows
        if self.LOFList: #If LOFList is not empty, filter rows by it
            rows = [row["cell"] for row in r["rows"] if int(row["id"]) in self.LOFList]

        res = []
        for row in rows:
            if row["discount_rt"] == "-":
                continue
            discount_rt = float(row["discount_rt"][:-1])
            if discount_rt >= self.disLimit or discount_rt <= self.preLimit:
                if "开放" in row["apply_status"]:
                    s = {}
                    for key, value in self.content.items():
                        s[key] = row[value] 
                        # s[key] = row[value] if value != "fund_id" else "".join(["[", row[value], "](", self.urlBase, row[value], ")"])
                    res.append(s)
        return res

    def md(self, info):
        if not info: return
        res = ["| " + " | ".join(list(info[0])) + " |"]
        res.append("| " + " :---: | " * (len(info[0]) - 1) + " :---: |")
        for i in info:
            res.append("| " + " | ".join(list(i.values())) + " |")
        res = "\n".join(res)
        return res

    def message(self, key, title, body):
        #TODO
        if not key: return

    def main(self):
        info = self.getInfo(id)
        print(info)
        if len(info):
            md = self.md(info)
            self.message(self.apiKey, "LOF-溢价: " + datetime.now(tz=pytz.timezone("Asia/Shanghai")).strftime("%m-%d %H:%M"), md)


if __name__ == "__main__":
    lof = LOF()
    lof.main()
