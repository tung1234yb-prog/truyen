"""
Công cụ hỗ trợ tải, dịch và tạo Web đọc truyện "Cao Võ: Trường Thương Hắc Viêm Trấn Yêu Ma"
"""
import os
import json
import urllib.request
import urllib.parse
import re

def translate_text(text, target_lang='vi', source_lang='zh-CN'):
    """Dịch đoạn văn bản bằng Google Translate API miễn phí"""
    if not text.strip():
        return ""
    paragraphs = text.split('\n')
    translated_paras = []
    
    for p in paragraphs:
        p_clean = p.strip()
        if not p_clean:
            translated_paras.append('')
            continue
        try:
            url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl={source_lang}&tl={target_lang}&dt=t&q=" + urllib.parse.quote(p_clean)
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                res = "".join([part[0] for part in data[0] if part[0]])
                translated_paras.append(res)
        except Exception as e:
            translated_paras.append(p_clean)
            
    return '\n\n'.join(translated_paras)

if __name__ == '__main__':
    test = "依照《东煌国妖类暂行管理条例》，越界伤人者，杀无赦。"
    print("Bản gốc:", test)
    print("Dịch thử:", translate_text(test))
