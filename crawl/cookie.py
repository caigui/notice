import base64
import gzip
import zlib
import json
import pickle
import urllib.parse
import requests
from typing import Optional

class CookieDecoder:
    """Cookie解码器 - 无需浏览器，Linux服务器可用"""
    
    @staticmethod
    def decode_php_serialized(data: str) -> dict:
        """解码PHP序列化数据"""
        import re
        
        result = {}
        # 简单的PHP序列化解析
        pattern = r's:(\d+):"([^"]+)";s:(\d+):"([^"]+)";'
        matches = re.findall(pattern, data)
        for match in matches:
            key = match[1]
            value = match[4]
            result[key] = value
        return result
    
    @staticmethod
    def decode_base64_gzip(encoded: str) -> str:
        """Base64 + GZIP解码"""
        try:
            # 添加padding
            missing_padding = len(encoded) % 4
            if missing_padding:
                encoded += '=' * (4 - missing_padding)
            
            # Base64解码
            compressed = base64.b64decode(encoded)
            
            # 尝试GZIP解压
            try:
                decompressed = gzip.decompress(compressed)
                return decompressed.decode('utf-8')
            except:
                # 尝试zlib解压
                decompressed = zlib.decompress(compressed)
                return decompressed.decode('utf-8')
        except Exception as e:
            print(f"解码失败: {e}")
            return encoded
    
    @staticmethod
    def url_safe_base64_decode(encoded: str) -> str:
        """URL安全的Base64解码"""
        # 替换URL安全的字符
        encoded = encoded.replace('-', '+').replace('_', '/')
        return CookieDecoder.decode_base64_gzip(encoded)
    
    @staticmethod
    def decode_kbzw_cookie(cookie_value: str) -> str:
        """专门解码kbzw__user_login cookie"""
        # 先URL解码
        decoded = urllib.parse.unquote(cookie_value)
        
        # 如果是压缩数据，解压
        if '.' in decoded and len(decoded) > 100:
            try:
                # 尝试Base64+GZIP解码
                result = CookieDecoder.url_safe_base64_decode(decoded)
                if result:
                    return result
            except:
                pass
        
        return decoded

# 使用示例
def fix_python_cookie(python_cookie_value: str) -> str:
    """将Python获取的Cookie转换为浏览器格式"""
    decoder = CookieDecoder()
    browser_format = decoder.decode_kbzw_cookie(python_cookie_value)
    return browser_format

# 实际应用
python_cookie = "kbzw__user_login=7Obd08_P1ebax9aXwZOqmrCorKuRpIKvpuXK7N_u0ejF1dSerMegwtfdrMqqn6qVr5rcqaqwx9PDpt3bz6qdrpqnlqyYrqXW2cXS1qCbq6KtlK2amLKgubXOvp-qrKCppK2YqJWtmK6ltrG_0aTC2PPV487XkKylo5iJx8ri3eTg7IzFtpaSp6Wjs4HHyuKvqaSZ5K2Wn4G45-PkxsfG1sTe3aihqpmklK2Xm8OpxK7ApZXV4tfcgr3G2uLioYGzyebo4s6onaiUpJGlp6GogcPC2trn0qihqpmklK2XuNzIn5Klq6OZp52ulKiPras.; expires=Thu, 19-Feb-2026 10:17:26 GMT; path=/', 'Expires': 'Mon, 26 Jul 1997 05:00:00 GMT"

browser_cookie = fix_python_cookie(python_cookie)
print(f"原始长度: {len(python_cookie)}")
print(f"转换后长度: {len(browser_cookie)}")
print(f"转换后: {browser_cookie[:100]}...")
print(f"转换后: {browser_cookie}")

# 在requests中使用
session = requests.Session()
session.cookies.set('kbzw__user_login', browser_cookie)
session.cookies.set('kbzw__Session', 'rjdl1rdess5garielkrb5t48h0')  # 你提供的session

# 测试请求
response = session.get('https://example.com')