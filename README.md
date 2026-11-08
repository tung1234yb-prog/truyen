# Hướng Dẫn Tải & Đẩy Trang Đọc Truyện Lên GitHub Pages

Thư mục dự án: `D:\Code\truyen-cao-vo`

### 1. Cấu trúc thư mục
- `index.html`: Giao diện web đọc truyện (gồm mục lục, đổi cỡ chữ, đổi theme tối/sáng/giấy cũ, responsive trên điện thoại & máy tính).
- `chapters.json`: Danh sách dữ liệu các chương truyện đã dịch sang tiếng Việt.
- `translator.py`: Tool tự động dịch văn bản tiếng Trung sang tiếng Việt.
- `add_chapter.py`: Script tự động nối chương mới vào `chapters.json`.

---

### 2. Các bước đưa lên GitHub Pages (Miễn phí)

#### Bước 1: Tạo Repository trên GitHub
1. Đăng nhập [GitHub.com](https://github.com).
2. Tạo một repository mới (ví dụ đặt tên là: `truyen-cao-vo`).
3. Chọn chế độ **Public**.

#### Bước 2: Đẩy source code từ máy lên GitHub
Mở PowerShell tại thư mục `D:\Code\truyen-cao-vo` và chạy các lệnh:

```powershell
cd D:\Code\truyen-cao-vo
git branch -M main
git remote add origin https://github.com/<tai-khoan-github-cua-ban>/truyen-cao-vo.git
git push -u origin main
```

#### Bước 3: Kích hoạt GitHub Pages
1. Vào repository trên GitHub -> Bấm tab **Settings**.
2. Tìm mục **Pages** ở thanh menu bên trái.
3. Ở phần **Branch**, chọn `main` và thư mục `/ (root)`, sau đó bấm **Save**.
4. Chờ khoảng 1 - 2 phút, GitHub sẽ cung cấp đường link web đọc truyện dạng:
   `https://<tai-khoan-github-cua-ban>.github.io/truyen-cao-vo/`
