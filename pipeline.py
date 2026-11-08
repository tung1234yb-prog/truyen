"""
pipeline.py - Dịch truyện Cao Võ từ raw TXT sang tiếng Việt
Cải tiến:
  - Model: gemini-2.5-flash (chất lượng cao hơn hẳn, cùng 500 RPD)
  - Context liên chương: truyền 300 chữ cuối chương trước để nhất quán
  - Batch 2 chương / 1 API call
  - Fallback: batch lỗi → retry từng chương
  - Post-processing: replace glossary sau mỗi lần dịch

Usage:
    python -X utf8 pipeline.py [start] [end]
    python -X utf8 pipeline.py           # dịch tất cả còn thiếu
    python -X utf8 pipeline.py 11 299    # dịch chương 11-299
"""

import sys
import re
import json
import time
import os
import requests

# ── Cấu hình ──────────────────────────────────────────────────────────────────
API_KEY    = os.environ.get("GEMINI_API_KEY", "")
MODEL      = "gemini-3.8-flash"
RAW_FILE   = "full_raw_564_chapters.txt"
JSON_FILE  = "chapters.json"
BATCH_SIZE = 2       # chương mỗi API call
DELAY_SEC  = 2       # giây chờ giữa các call
CONTEXT_CHARS = 300  # ký tự cuối chương trước dùng làm context
# ──────────────────────────────────────────────────────────────────────────────

# ── Glossary post-processing ───────────────────────────────────────────────────
# Thêm vào đây khi phát hiện tên bị dịch sai
GLOSSARY_FIXES = {
    # Nhân vật
    "Đơn Hoằng Nghị": "Đan Hoằng Nghị",
    "Bát Ngạc":        "Bệ Ngạn",
    # Thêm dần khi phát hiện...
}
# ──────────────────────────────────────────────────────────────────────────────

GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{MODEL}:generateContent?key={API_KEY}"
)

# ── Bảng thuật ngữ nhúng vào prompt ───────────────────────────────────────────
GLOSSARY_PROMPT = """
## BẢNG THUẬT NGỮ BẮT BUỘC (dùng chính xác, nhất quán)

### Nhân vật:
沈长安→Thẩm Trường An | 许明镜→Hứa Minh Cảnh | 顾敛→Cố Liễm | 单弘毅→Đan Hoằng Nghị
杜月→Đỗ Nguyệt | 鹿清→Lộc Thanh | 向情→Hướng Tình | 安暖→An Noãn
吕南→Lữ Nam | 宋之薇→Tống Chi Vi | 史远→Sử Viễn | 卓怀山→Trác Hoài Sơn
裴昭→Bùi Chiếu | 方纪明→Phương Ký Minh | 冯烈→Bằng Liệt | 纪思→Kỷ Tư
李悦→Lý Duyệt | 张海→Trương Hải | 朱崇→Chu Sùng | 白崇→Bạch Sùng
许屠→Hứa Tu | 顾天→Cố Thiên | 顾琴→Cố Cầm

### Tổ chức / Địa danh TQ:
镇夜司→Trấn Dạ Ti | 魔都→Ma Đô | 京城→Kinh Thành | 东海→Đông Hải
北冥→Bắc Minh | 黑天鹅→Hắc Thiên Nga | 渊门→Uyên Môn | 大梦→Đại Mộng | 苍古→Thương Cổ

### Pháp bảo / Thuật ngữ:
碑岸→Bệ Ngạn | 黑炎→Hắc Viêm | 神魂→thần hồn | 灵力→linh lực | 武者→võ giả

## QUY TẮC:
- Địa danh / tên người NƯỚC NGOÀI: GIỮ NGUYÊN tiếng Anh (New York, London, Adam, Victor...)
- Văn phong tự nhiên theo thể loại tiên hiệp Việt, giữ nguyên cấu trúc đoạn văn
- KHÔNG thêm lời mở đầu hay giải thích thêm
"""


def apply_glossary(text: str) -> str:
    """Post-processing: replace tên sai sau khi dịch."""
    for wrong, correct in GLOSSARY_FIXES.items():
        text = text.replace(wrong, correct)
    return text


def load_raw_chapters(filepath: str) -> dict[int, tuple[str, str]]:
    """Parse raw TXT → {chap_num: (chinese_title, chinese_content)}"""
    with open(filepath, encoding="utf-8") as f:
        text = f.read()

    pattern = r'【(第\s*(\d+)\s*章[^\】\n\r]*)】'
    matches = list(re.finditer(pattern, text))
    chapters: dict[int, tuple[str, str]] = {}

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
    """Lấy 300 ký tự cuối chương trước (nếu có) làm context."""
    prev = next((c for c in existing if c["id"] == f"chuong-{chap_num - 1}"), None)
    if prev and prev.get("content"):
        tail = prev["content"][-CONTEXT_CHARS:].strip()
        return f"\n[Đoạn kết chương {chap_num - 1} — chỉ để tham khảo văn phong, KHÔNG dịch lại]\n{tail}\n"
    return ""


def translate_batch(
    batch: list[tuple[int, str, str]],
    existing: list[dict]
) -> list[dict] | None:
    """
    Gửi 1 API call dịch batch chương.
    batch = [(num, cn_title, cn_content), ...]
    """
    # Lấy context từ chương liền trước chương đầu tiên trong batch
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
        f"Bạn là dịch giả chuyên nghiệp dòng truyện đô thị cao võ / tiên hiệp Trung Quốc.\n"
        f"Hãy dịch {len(batch)} chương sau từ tiếng Trung sang tiếng Việt.\n"
        f"{GLOSSARY_PROMPT}"
        f"{prev_ctx}\n"
        f"Trả về JSON hợp lệ, KHÔNG có markdown, theo đúng format:\n"
        f'[{{"num": <số chương>, "vi_title": "<tiêu đề>", "vi_content": "<nội dung>"}}]\n\n'
        f"Dữ liệu cần dịch:\n"
        + "\n\n".join(sections)
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 8192,
        }
    }

    try:
        resp = requests.post(GEMINI_URL, json=payload, timeout=180)
        resp.raise_for_status()
        raw_resp = resp.json()
        text = raw_resp["candidates"][0]["content"]["parts"][0]["text"].strip()

        # Bóc JSON khỏi markdown nếu có
        if text.startswith("```"):
            text = re.sub(r'^```[^\n]*\n', '', text)
            text = re.sub(r'\n```$', '', text.rstrip())

        return json.loads(text)

    except json.JSONDecodeError as e:
        print(f"  ❌ JSON parse lỗi: {e}")
        if 'text' in locals():
            print(f"     Tail: ...{text[-300:]}")
        return None
    except (requests.RequestException, KeyError) as e:
        print(f"  ❌ Lỗi API: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"     Response: {e.response.text[:400]}")
        return None


def save_chapter_entry(
    existing: list[dict],
    existing_nums: set[int],
    num: int,
    vi_title: str,
    vi_content: str
) -> None:
    """Thêm/cập nhật 1 chương vào list và sort."""
    vi_content = apply_glossary(vi_content)
    vi_title   = apply_glossary(vi_title)
    chapter_entry = {
        "id":      f"chuong-{num}",
        "title":   f"Chương {num}: {vi_title}",
        "content": vi_content
    }
    existing_nums.add(num)
    # Xoá entry cũ nếu có
    existing[:] = [c for c in existing if c["id"] != f"chuong-{num}"]
    existing.append(chapter_entry)
    existing.sort(key=lambda c: int(c["id"].replace("chuong-", "")))


def main():
    args = sys.argv[1:]

    # Load raw
    print(f"📖 Đọc file raw: {RAW_FILE}")
    raw = load_raw_chapters(RAW_FILE)
    print(f"   Tổng raw: {len(raw)} chương")

    # Load existing translated
    existing = load_existing(JSON_FILE)
    existing_nums = {int(c["id"].replace("chuong-", "")) for c in existing}
    print(f"   Đã dịch: {len(existing_nums)} chương")
    print(f"   Model: {MODEL}")

    # Xác định range cần dịch
    if len(args) >= 2:
        start_chap = int(args[0])
        end_chap   = int(args[1])
        to_translate = [n for n in range(start_chap, end_chap + 1)
                        if n in raw and n not in existing_nums]
    elif len(args) == 1:
        start_chap = int(args[0])
        to_translate = [n for n in sorted(raw.keys())
                        if n >= start_chap and n not in existing_nums]
    else:
        to_translate = [n for n in sorted(raw.keys()) if n not in existing_nums]

    if not to_translate:
        print("✅ Không còn chương nào cần dịch!")
        return

    total = len(to_translate)
    total_calls = (total + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"\n🚀 Cần dịch: {total} chương ({to_translate[0]}→{to_translate[-1]})")
    print(f"   Batch size: {BATCH_SIZE} chương/call → ≈{total_calls} API calls\n")

    success_count = 0
    fail_count    = 0

    for batch_idx in range(0, total, BATCH_SIZE):
        batch_nums = to_translate[batch_idx: batch_idx + BATCH_SIZE]
        batch_data = [(n, raw[n][0], raw[n][1]) for n in batch_nums]

        chap_range  = f"{batch_nums[0]}-{batch_nums[-1]}" if len(batch_nums) > 1 else str(batch_nums[0])
        call_num    = batch_idx // BATCH_SIZE + 1
        print(f"[{call_num}/{total_calls}] Dịch chương {chap_range}...", end=" ", flush=True)

        result = translate_batch(batch_data, existing)

        if result:
            added = 0
            for item in result:
                try:
                    num = int(item["num"])
                    save_chapter_entry(
                        existing, existing_nums,
                        num,
                        item["vi_title"].strip(),
                        item["vi_content"].strip()
                    )
                    added += 1
                except (KeyError, ValueError) as e:
                    print(f"\n  ⚠️  Parse lỗi: {e} | {str(item)[:80]}")

            save_chapters(JSON_FILE, existing)
            success_count += added
            print(f"✅ +{added} chương (tổng: {len(existing)})")

        elif len(batch_nums) > 1:
            # Fallback: retry từng chương
            print(f"⚠️  Batch lỗi → retry từng chương...")
            for single_num in batch_nums:
                print(f"   Retry chương {single_num}...", end=" ", flush=True)
                r = translate_batch([(single_num, raw[single_num][0], raw[single_num][1])], existing)
                if r:
                    item = r[0]
                    save_chapter_entry(
                        existing, existing_nums,
                        int(item["num"]),
                        item["vi_title"].strip(),
                        item["vi_content"].strip()
                    )
                    save_chapters(JSON_FILE, existing)
                    success_count += 1
                    print(f"✅ (tổng: {len(existing)})")
                else:
                    fail_count += 1
                    print("❌")
                time.sleep(DELAY_SEC)
        else:
            fail_count += len(batch_nums)
            print("❌ Thất bại (bỏ qua)")

        if batch_idx + BATCH_SIZE < total:
            time.sleep(DELAY_SEC)

    print(f"\n{'='*50}")
    print(f"✅ Dịch xong: {success_count} chương thành công")
    if fail_count:
        print(f"❌ Thất bại:  {fail_count} chương")
    print(f"📄 chapters.json: {len(existing)} chương tổng cộng")


if __name__ == "__main__":
    main()
