import json
import os
import sys
import re

def append_chapter(chapter_num, title, content_text):
    json_path = os.path.join(os.path.dirname(__file__), 'chapters.json')
    if os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            chapters = json.load(f)
    else:
        chapters = []
        
    chap_id = f"chuong-{chapter_num}"
    
    # Kiểm tra xem chương đã có chưa
    existing = next((c for c in chapters if c['id'] == chap_id), None)
    if existing:
        existing['title'] = title
        existing['content'] = content_text
    else:
        chapters.append({
            "id": chap_id,
            "chapterNumber": chapter_num,
            "title": title,
            "content": content_text
        })
        
    chapters.sort(key=lambda x: x['chapterNumber'])
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(chapters, f, ensure_ascii=False, indent=2)
        
    print(f"-> Đã lưu thành công Chương {chapter_num}: {title}")

if __name__ == '__main__':
    print("Script sẵn sàng để thêm chương mới vào chapters.json!")
