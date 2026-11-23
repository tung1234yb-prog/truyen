# Thư Viện Truyện Dịch

Trang đọc truyện tĩnh (HTML + JSON), deploy bằng GitHub Pages. Hỗ trợ **nhiều truyện**.

## Cấu trúc thư mục

```
.
├── index.html                 # Giao diện: trang chọn truyện + trang đọc
├── books.json                 # Danh sách truyện (metadata)
├── books/
│   ├── cao-vo/
│   │   └── chapters.json      # Nội dung các chương (tiếng Việt)
│   └── ngu-linh-can/
│       └── chapters.json
└── raw_chapters/              # Raw tiếng Trung (gitignored, không deploy)
```

### `books.json`

Mảng metadata, mỗi truyện gồm:

| Trường | Ý nghĩa |
| --- | --- |
| `id` | Khóa duy nhất, cũng là tên thư mục trong `books/` |
| `title`, `author` | Tên truyện, tác giả |
| `tag` | Nhãn thể loại hiển thị trên trang chủ |
| `protagonist` | Nhân vật chính (hiển thị ở đầu chương) |
| `description` | Tóm tắt ngắn |
| `chapterCount` | Số chương hiện có (cập nhật khi thêm chương) |
| `latestChapter` | Tên chương mới nhất |
| `path` | Đường dẫn tới `chapters.json` của truyện |

### `chapters.json` (mỗi truyện)

Mảng chương, mỗi chương:

```json
{
  "id": "chuong-563",
  "chapterNumber": 563,
  "title": "Chương 563: Có chuyện muốn nói",
  "content": "Đoạn 1...\n\nĐoạn 2..."
}
```

`content` tách đoạn bằng `\n\n`; `index.html` render mỗi đoạn thành một `<p>`.

## Điều hướng

- `#/` — trang chủ chọn truyện
- `#/book/cao-vo` — mở truyện, chương đầu
- `#/book/cao-vo/chuong-563` — mở đúng chương (link chia sẻ được)

## Thêm truyện mới

1. Tạo thư mục `books/<id>/`, thêm `chapters.json`.
2. Thêm một object vào `books.json` với `id` và `path` tương ứng.
3. Cập nhật `chapterCount` / `latestChapter` mỗi khi thêm chương.

## Deploy GitHub Pages

Settings → Pages → Branch `main`, thư mục `/ (root)` → Save.

Trang sẽ có dạng `https://<tai-khoan>.github.io/<repo>/`.
