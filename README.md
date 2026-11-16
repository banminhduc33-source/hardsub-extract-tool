# Tool bóc hardsub tiếng Trung → file .srtpx

## Nguyên lý hoạt động

1. **Tách khung hình** theo FPS mục tiêu (mặc định 30fps) — không xuất hàng
   nghìn file ảnh ra đĩa cho tốn chỗ, mà đọc trực tiếp từng frame bằng OpenCV
   và chỉ OCR đúng những frame rơi vào bước lấy mẫu, nhưng mốc thời gian vẫn
   tính theo FPS **gốc** của video nên timestamp luôn chính xác.
2. **Quét từng khung hình** trong vùng ROI (vùng chứa phụ đề, mặc định toàn bộ
   khung hình) bằng OCR để tìm **chữ nằm ở đâu** (bounding box
   pixel) và **nội dung chữ là gì**.
3. **Ghép các frame liên tiếp có cùng nội dung** (so sánh bằng tỉ lệ giống
   nhau, chịu được sai số OCR vài ký tự) thành từng "câu" phụ đề, xác định
   mốc `start/end` giống hệt file SRT.
4. **So khung chữ lúc câu vừa xuất hiện với lúc câu đã "chốt"** (vài frame
   đầu vs vài frame cuối của câu đó). Nếu lệch nhau quá ngưỡng (mặc định
   6px) → ghi **cả 2 khung** theo đúng format mẫu
   (`Độ rộng: a - b (cuối câu: c - d)`); nếu không đổi → chỉ ghi 1 khung.
5. **Ghi ra file `.srtpx`** đúng cấu trúc: số thứ tự, mốc thời gian kiểu SRT,
   nội dung chữ Trung, dòng `Độ rộng` (khoảng x) và dòng `Vị trí` (khoảng y).
6. **(Tuỳ chọn) Xuất ảnh debug**: mỗi N frame xử lý sẽ lưu lại ảnh gốc có
   **kẻ khung** — khung xanh = vùng ROI đang quét, khung đỏ = chữ OCR tìm
   thấy — để bạn kiểm tra bằng mắt xem ROI/OCR có đang bắt đúng chỗ không,
   trước khi chạy full video.

> Lưu ý quan trọng: cách chia "khung chính / cuối câu" ở trên là một **suy
> luận hợp lý dựa trên 1 file mẫu** bạn đưa, không phải tài liệu chính thức
> của công cụ gốc tạo ra file đó. Vài tham số (ngưỡng lệch pixel, số frame
> đầu/cuối lấy mẫu, ngưỡng giống nhau giữa 2 câu...) có thể cần chỉnh lại
> cho khớp 100% với video thật của bạn — xem mục "Các tham số hay chỉnh".

## Cài đặt

```bash
pip install opencv-python-headless numpy pillow

# chọn 1 trong 3 OCR engine:
pip install paddleocr paddlepaddle        # khuyên dùng — chính xác nhất cho chữ Hán
# hoặc
pip install easyocr                        # dễ cài hơn, chậm hơn chút
# hoặc dùng tesseract có sẵn + cài gói tiếng Trung của hệ điều hành:
sudo apt install tesseract-ocr-chi-sim tesseract-ocr-chi-tra
```

Máy chạy công cụ này (sandbox trò chuyện) **không có kết nối mạng** nên
không tự tải được model OCR tiếng Trung / gói ngôn ngữ tiếng Trung để chạy
thử trực tiếp ở đây. Script đã được kiểm thử đầy đủ logic (tách frame, OCR,
ghép câu, tính khung toạ độ, xuất file, xuất ảnh debug) bằng một video giả
lập chữ Latin + tesseract tiếng Anh (xem thư mục `demo/`) — phần OCR tiếng
Trung sẽ hoạt động y hệt về mặt pipeline, bạn chỉ cần cài engine + chạy ở
máy có mạng.

## Cách chạy

```bash
python3 hardsub_extract.py video.mp4 -o ketqua.srtpx \
    --engine paddleocr --lang ch \
    --fps 30 \
    --roi 0,0.75,1.0,1.0 \
    --debug-dir debug_frames --debug-every 20
```

Sau khi chạy xong, **mở vài ảnh trong `debug_frames/` trước** để xác nhận
khung đỏ đang bám đúng chữ phụ đề rồi mới tin vào số liệu trong file
`.srtpx`.

## Các tham số hay chỉnh

| Tham số | Ý nghĩa | Khi nào cần đổi |
|---|---|---|
| `--roi x1,y1,x2,y2` | Vùng chứa phụ đề, tính theo phân số 0..1 của khung hình | Muốn chạy nhanh hơn → thu nhỏ ROI, vd `0,0.75,1.0,1.0` (25% dưới cùng) |
| `--fps` | Số frame lấy mẫu mỗi giây | Video dài → giảm xuống (vd 10-15) để chạy nhanh hơn, đổi lại mốc thời gian kém mịn hơn chút |
| `--engine` / `--lang` | Engine OCR dùng và mã ngôn ngữ | `paddleocr`/`easyocr` dùng `ch`; `tesseract` dùng `chi_sim` (giản thể) hoặc `chi_tra` (phồn thể) |
| `--scale` | Phóng to vùng ROI trước khi OCR | Chữ nhỏ/video độ phân giải thấp → tăng lên 2.5-3.0 |
| `--similarity` | Ngưỡng % giống nhau giữa 2 frame để coi là cùng 1 câu | OCR hay đọc lệch vài ký tự giữa các frame → giảm ngưỡng (vd 0.6) |
| `--max-gap-frames` | Số frame OCR "trống" liên tiếp vẫn coi là chưa hết câu | Chữ hay bị chớp/mất nét giữa chừng → tăng lên |
| `--min-frames` | Số frame tối thiểu để tính là 1 câu thật | OCR hay bắt nhầm chữ nền/nhiễu trong 1-2 frame → tăng lên để lọc nhiễu |

## Cấu trúc thư mục bàn giao

```
hardsub_extract.py     # tool chính
requirements.txt       # danh sách thư viện cần cài
README.md              # tài liệu này
demo/                  # bằng chứng đã chạy thử pipeline thành công
  make_test_video.py     # script tạo video giả lập để test
  test_input.mp4
  test_output.srtpx      # kết quả chạy thử (khớp đúng format mẫu)
  debug_frames/          # vài ảnh đã kẻ khung minh hoạ bước 6
```
