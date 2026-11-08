"""
pipeline.py - Dịch & Biên tập truyện Cao Võ
Quy trình 2 bước:
  1. Dịch thô (Raw -> Tiếng Việt)
  2. Biên tập & Rà soát (Proofread & Polish) dùng Key tiếp theo để kiểm tra lỗi, sót chữ Hán, hành văn.
Sử dụng xoay vòng danh sách các API Keys từ file .env.
"""

import sys
import re
import json
import time
import os
import requests

# ── Cấu hình ──────────────────────────────────────────────────────────────────
def _load_keys() -> list[str]:
    env_file = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("GEMINI_API_KEYS="):
                    return [k.strip() for k in line[16:].split(",") if k.strip()]
    env_val = os.environ.get("GEMINI_API_KEYS", "")
    if env_val:
        return [k.strip() for k in env_val.split(",") if k.strip()]
    single = os.environ.get("GEMINI_API_KEY", "")
    return [single] if single else []

API_KEYS   = _load_keys()
_key_index = 0

MODEL      = "gemini-3.5-flash-lite"
RAW_FILE   = "full_raw_564_chapters.txt"
JSON_FILE  = "chapters.json"
BATCH_SIZE = 2       # 2 chương / call
DELAY_SEC  = 1       # giây chờ giữa các call
CONTEXT_CHARS = 300  # ký tự cuối chương trước
# ──────────────────────────────────────────────────────────────────────────────

GLOSSARY_FIXES = {
    "Đơn Hoằng Nghị": "Đan Hoằng Nghị",
    "Bát Ngạc":        "Bệ Ngạn",
}

GEMINI_URL_TPL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{MODEL}:generateContent?key="
)

def current_key() -> str:
    return API_KEYS[_key_index % len(API_KEYS)]

def rotate_key(reason: str = "") -> bool:
    global _key_index
    _key_index += 1
    print(f"  🔄 Chuyển sang key {_key_index % len(API_KEYS) + 1}/{len(API_KEYS)}" + (f" ({reason})" if reason else ""))
    return True

GLOSSARY_PROMPT = """
## BẢNG THUẬT NGỮ BẮT BUỘC:
### Nhân vật:
沈长安→Thẩm Trường An | 许明镜→Hứa Minh Cảnh | 顾敛→Cố Liễm | 单弘毅→Đan Hoằng Nghị
杜月→Đỗ Nguyệt | 鹿清→Lộc Thanh | 向情→Hướng Tình | 安暖→An Noãn
吕南→Lữ Nam | 宋之薇→Tống Chi Vi | 史远→Sử Viễn | 卓怀山→Trác Hoài Sơn
裴昭→Bùi Chiếu | 方纪明→Phương Ký Minh | 冯烈→Bằng Liệt | 纪思→Kỷ Tư
李悦→Lý Duyệt | 张海→Trương Hải | 朱崇→Chu Sùng | 白崇→Bạch Sùng
许屠→Hứa Tu | 顾天→Cố Thiên | 顾琴→Cố Cầm

### Tổ chức / Địa danh:
镇夜司→Trấn Dạ Ti | 魔都→Ma Đô | 京城→Kinh Thành | 东海→Đông Hải
北冥→Bắc Minh | 黑天鹅→Hắc Thiên Nga | 渊门→Uyên Môn | 大梦→Đại Mộng | 苍古→Thương Cổ

### Pháp bảo / Thuật ngữ:
碑岸→Bệ Ngạn | 黑炎→Hắc Viêm | 神魂→thần hồn | 灵力→linh lực | 武者→võ giả

## QUY TẮC:
- Tên / địa danh NƯỚC NGOÀI: Giữ nguyên tiếng Anh (New York, London, Adam, Victor...).
- Văn phong tự nhiên, giữ nguyên cấu trúc đoạn văn, KHÔNG tự ý tóm tắt hay cắt bớt.
"""

def apply_glossary(text: str) -> str:
    for wrong, correct in GLOSSARY_FIXES.items():
        text = text.replace(wrong, correct)
    return text

def load_raw_chapters(filepath: str) -> dict[int, tuple[str, str]]:
    with open(filepath, encoding="utf-8") as f:
        text = f.read()
    pattern = r'【(第\s*(\d+)\s*章[^\】\n\r]*)】'
    matches = list(re.finditer(pattern, text))
    chapters = {}
    for i, m in enumerate(matches):
        full_title = m.group(1).strip()
        chap_num   = int(m.group(2))
        start      = m.end()
        end        = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content    = text[start:end].strip()
        chapters[chap_num] = (full_title, content)
    return chapters

def load_existing(filepath: str) -> list[dict]:
    if os.path.exists(filepath):
        with open(filepath, encoding="utf-8") as f:
            return json.load(f)
    return []

def save_chapters(filepath: str, chapters: list[dict]) -> None:
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(chapters, f, ensure_ascii=False, indent=2)

def get_prev_context(existing: list[dict], chap_num: int) -> str:
    prev = next((c for c in existing if c["id"] == f"chuong-{chap_num - 1}"), None)
    if prev and prev.get("content"):
        tail = prev["content"][-CONTEXT_CHARS:].strip()
        return f"\n[Đoạn kết chương {chap_num - 1} — chỉ để tham khảo văn phong, KHÔNG dịch lại]\n{tail}\n"
    return ""

def call_gemini_api(prompt: str, expect_json: bool = True) -> any:
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 8192,
        }
    }
    if expect_json:
        payload["generationConfig"]["responseMimeType"] = "application/json"

    for attempt in range(len(API_KEYS) * 2):
        url = GEMINI_URL_TPL + current_key()
        try:
            resp = requests.post(url, json=payload, timeout=120)
            if resp.status_code == 429:
                rotate_key("429 Quota")
                time.sleep(1)
                continue
            if resp.status_code == 503:
                time.sleep(6)
                continue
            resp.raise_for_status()
            raw_resp = resp.json()
            text = raw_resp["candidates"][0]["content"]["parts"][0]["text"].strip()
            
            if not expect_json:
                return text

            if text.startswith("```"):
                text = re.sub(r'^```[^\n]*\n', '', text)
                text = re.sub(r'\n```$', '', text.rstrip())

            try:
                return json.loads(text)
            except json.JSONDecodeError:
                cleaned = re.sub(r'\\(?![/"\\bfnrtu])', r'\\\\', text)
                return json.loads(cleaned)

        except Exception as e:
            rotate_key(f"Error {e}")
            time.sleep(1)
            continue
    return None

def translate_step(batch: list[tuple[int, str, str]], existing: list[dict]) -> list[dict] | None:
    """Bước 1: Dịch thô"""
    first_num = batch[0][0]
    prev_ctx  = get_prev_context(existing, first_num)

    sections = []
    for num, title, content in batch:
        sections.append(
            f"=== CHƯƠNG {num} ===\n"
            f"TIÊU ĐỀ GỐC: 【{title}】\n"
            f"NỘI DUNG:\n{content}"
        )

    prompt = (
        f"Bạn là dịch giả tiểu thuyết đô thị cao võ / tiên hiệp tiếng Trung sang tiếng Việt.\n"
        f"Hãy dịch {len(batch)} chương sau sang tiếng Việt chuẩn xác.\n"
        f"{GLOSSARY_PROMPT}"
        f"{prev_ctx}\n"
        f"Trả về JSON dạng:\n"
        f'[{{"num": <số>, "vi_title": "<tiêu đề>", "vi_content": "<nội dung>"}}]\n\n'
        f"Dữ liệu gốc:\n" + "\n\n".join(sections)
    )
    return call_gemini_api(prompt, expect_json=True)

def proofread_step(translated_items: list[dict]) -> list[dict]:
    """Bước 2: Dùng key kế tiếp để kiểm tra, sửa sót chữ Hán, chuốt câu từ"""
    # Xoay sang key khác để chạy bước kiểm duyệt
    rotate_key("Kiểm duyệt/Proofread")
    
    sections = []
    for item in translated_items:
        sections.append(
            f"=== CHƯƠNG {item['num']} ===\n"
            f"TIÊU ĐỀ: {item['vi_title']}\n"
            f"NỘI DUNG:\n{item['vi_content']}"
        )

    prompt = (
        f"Bạn là tổng biên tập cao cấp truyện tiên hiệp / cao võ Việt Nam.\n"
        f"Hãy duyệt lại và hoàn thiện bản dịch của {len(translated_items)} chương dưới đây:\n"
        f"1. Rà soát và loại bỏ triệt để bất kỳ chữ Hán nào còn sót lại.\n"
        f"2. Đảm bảo tên riêng tuân thủ: Đan Hoằng Nghị, Bệ Ngạn, Thẩm Trường An, Trấn Dạ Ti, Hắc Viêm...\n"
        f"3. Chuốt lại câu văn cho mượt mà, thuần Việt nhưng vẫn đậm chất kiếm hiệp/cao võ.\n"
        f"4. Giữ nguyên độ dài và cấu trúc các đoạn văn.\n\n"
        f"Trả về đúng JSON format:\n"
        f'[{{"num": <số>, "vi_title": "<tiêu đề đã chuốt>", "vi_content": "<nội dung đã chuốt>"}}]\n\n'
        f"Bản dịch cần biên tập:\n" + "\n\n".join(sections)
    )
    res = call_gemini_api(prompt, expect_json=True)
    if res and isinstance(res, list):
        return res
    return translated_items # fallback nếu proofread lỗi

def save_chapter_entry(existing: list[dict], existing_nums: set[int], num: int, title: str, content: str) -> None:
    content = apply_glossary(content)
    title   = apply_glossary(title)
    entry = {
        "id": f"chuong-{num}",
        "title": f"Chương {num}: {title}",
        "content": content
    }
    existing_nums.add(num)
    existing[:] = [c for c in existing if c["id"] != f"chuong-{num}"]
    existing.append(entry)
    existing.sort(key=lambda c: int(c["id"].replace("chuong-", "")))

def main():
    args = sys.argv[1:]
    raw = load_raw_chapters(RAW_FILE)
    existing = load_existing(JSON_FILE)
    existing_nums = {int(c["id"].replace("chuong-", "")) for c in existing}

    print(f"📖 Tổng raw: {len(raw)} chương | Đã có: {len(existing_nums)} chương")
    print(f"🔑 Keys hoạt động: {len(API_KEYS)} keys | Quy trình: 2 Bước (Dịch thô + Biên tập)")

    if len(args) >= 2:
        start_chap, end_chap = int(args[0]), int(args[1])
        to_translate = [n for n in range(start_chap, end_chap + 1) if n in raw and n not in existing_nums]
    elif len(args) == 1:
        start_chap = int(args[0])
        to_translate = [n for n in sorted(raw.keys()) if n >= start_chap and n not in existing_nums]
    else:
        to_translate = [n for n in sorted(raw.keys()) if n not in existing_nums]

    if not to_translate:
        print("✅ Không còn chương nào cần dịch!")
        return

    total = len(to_translate)
    total_calls = (total + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"\n🚀 Cần dịch & kiểm tra: {total} chương ({to_translate[0]}→{to_translate[-1]})")

    success_count = 0
    fail_count = 0

    for idx in range(0, total, BATCH_SIZE):
        batch_nums = to_translate[idx: idx + BATCH_SIZE]
        batch_data = [(n, raw[n][0], raw[n][1]) for n in batch_nums]
        chap_range = f"{batch_nums[0]}-{batch_nums[-1]}" if len(batch_nums) > 1 else str(batch_nums[0])
        call_num = idx // BATCH_SIZE + 1

        print(f"[{call_num}/{total_calls}] 1️⃣ Dịch chương {chap_range}...", end=" ", flush=True)
        raw_trans = translate_step(batch_data, existing)

        if raw_trans and isinstance(raw_trans, list):
            print(f"➔ 2️⃣ Kiểm tra & Chuốt văn...", end=" ", flush=True)
            final_trans = proofread_step(raw_trans)
            
            added = 0
            for item in final_trans:
                try:
                    num = int(item["num"])
                    save_chapter_entry(existing, existing_nums, num, item["vi_title"].strip(), item["vi_content"].strip())
                    added += 1
                except Exception as e:
                    print(f"Err {e}", end=" ")

            save_chapters(JSON_FILE, existing)
            success_count += added
            print(f"✅ +{added} chương (Tổng: {len(existing)})")
        else:
            print(f"❌ Lỗi batch dịch, bỏ qua")
            fail_count += len(batch_nums)

        time.sleep(DELAY_SEC)

    print(f"\n{'='*50}")
    print(f"✅ Hoàn tất đợt: {success_count} chương thành công | Thất bại: {fail_count}")

if __name__ == "__main__":
    main()
