# -*- coding: utf-8 -*-
"""
Created on Wed Apr 29 13:13:34 2020

@author: hs101
"""

from urllib import request
import pandas as pd
import os

class ETF_Crawler:
    def __init__(self, num_code):
        self.num_code = num_code
        self.target = "http://query.sse.com.cn/etfDownload/downloadETF2Bulletin.do?etfType="
        self.url = self.target + str(num_code)
        self.html = self.get_html()
        # Add absolute path handling
        self.base_path = os.path.dirname(os.path.abspath(__file__))
        self.save_to_csv()
        self.dataRaw = self.get_dataRaw()

    def get_html(self):
        try:
            html = request.urlopen(self.url).read()
            html = html.decode('gb2312')
        except:
            html = "Error" + '\n' + "etfType = " + str(self.num_code)
            return html
        else:
            return html

    def save_to_csv(self):
        name = str(self.num_code) + '.ETF'
        # Use absolute path for file operations
        file_path = os.path.join(self.base_path, 'dataRaw', name)
        if not os.path.exists(file_path):
            with open(file_path, 'w+', encoding='gb2312') as file:
                file.write("")  # Create an empty file
        with open(file_path, 'w+', encoding='gb2312') as file:
            file.write(self.html)
    # 这里需要优化成：
    # 一天内只读取一次数据，
    # 接下来的分析都在已经存在的文件上操作

    def get_dataRaw(self):
        # Use absolute path for reading the file
        file_path = os.path.join(self.base_path, 'dataRaw', f'{self.num_code}.ETF')
        dataRaw = pd.read_csv(file_path, sep='\n', encoding='gb2312')
        return dataRaw

i = 511520
etf_crawler = ETF_Crawler(i)
temp = etf_crawler.save_to_csv()