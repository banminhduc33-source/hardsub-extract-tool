# Tool bóc hardsub tiếng Trung → file .srtpx

## Định dạng .srtpx (theo file mẫu `demo/testvn.srtpx`)

```
#res 768x576                      ← độ phân giải video
                                  
1
00:00:00,267 --> 00:00:09,467     ← bắt đầu → kết thúc (kết thúc = lúc câu biến mất)
Nội dung chữ
Độ rộng: 252px - 520px            ← khung chữ ổn định (x1 - x2)
Vị trí: 46px - 80px               ← (y1 - y2)
KF 0.27s: 217 555 -21 18          ← chỉ có khi khung chữ chuyển động (hiệu ứng)
KF 1.00s: 252 520 46 80              mỗi dòng = "thời gian: x1 x2 y1 y2"
KF 9.47s: 252 520 46 80
```
Xuống dòng kiểu CRLF, UTF-8 không BOM. Chạy `python demo/test_format.py` để kiểm tra
bộ ghi file tạo ra **giống từng byte** file mẫu.

## Nguyên lý

1. Đọc video, lấy mẫu khung hình theo `--fps`.
2. OCR trong vùng `--roi` (mặc định toàn khung hình) để tìm chữ nằm ở đâu và là chữ gì.
3. Gom các ô chữ gần nhau thành một khối (một câu). Mặc định **bỏ chữ không phải chữ Hán**
   (số, logo...) để không bị dính vào khung. Nhiều câu ở nhiều vị trí khác nhau được theo dõi riêng.
4. Theo dõi từng khối qua các khung hình; các mảnh bị đứt do OCR đọc lệch/hiệu ứng xuất hiện được nối lại.
5. Khung chữ đứng yên → chỉ ghi `Độ rộng`/`Vị trí`. Khung chữ chuyển động → ghi thêm các dòng `KF`.
6. (Tuỳ chọn) xuất ảnh debug có kẻ khung đỏ quanh chữ tìm được.

> Cách chia khung chính / KF là suy luận từ file mẫu, không phải tài liệu chính thức. Hiệu ứng
> trượt vào từ ngoài khung (toạ độ âm như `-21` trong mẫu) OCR không đo được vì chữ chưa nằm trong
> khung hình, nên các KF đầu của loại hiệu ứng đó có thể khác mẫu.

## Cách chạy

```bash
python3 hardsub_extract.py video.mp4 -o ketqua.srtpx --engine paddleocr --lang ch --fps 12 \
    --debug-dir debug_frames --debug-every 20
```
Fps càng cao thì mốc thời gian càng sát (fps cao khớp mẫu nhất) nhưng chạy càng lâu.

## Tham số hay chỉnh

| Tham số | Ý nghĩa |
|---|---|
| `--roi x1,y1,x2,y2` | Vùng quét (phân số 0..1). Mặc định toàn khung hình; thu nhỏ (vd `0,0.75,1,1`) để chạy nhanh hơn |
| `--fps` | Số khung quét mỗi giây |
| `--engine` / `--lang` | `paddleocr`: `ch`/`chinese_cht`; `easyocr`: `ch_sim`/`ch_tra`; `tesseract`: `chi_sim`/`chi_tra` |
| `--keep-non-cjk` | Giữ cả chữ không phải chữ Hán (mặc định bỏ) |
| `--similarity` | Ngưỡng giống nhau để coi 2 khung là cùng một câu (mặc định 0.6) |
| `--merge-sim` | Ngưỡng nối các mảnh câu bị đứt (mặc định 0.5) |
| `--kf-tol` | Khung lệch quá số pixel này thì tính là chuyển động (mặc định 6) |
| `--stable-sec` | Khung giữ yên ít nhất số giây này mới là khung ổn định chính (mặc định 0.5) |
| `--min-frames` / `--max-gap-frames` | Lọc nhiễu / chịu được OCR chớp tắt |
| `--min-height` | Chỉ lấy chữ cao ít nhất tỉ lệ này so với chiều cao video (mặc định 0.035 = 3.5%), bỏ chữ li ti trong bảng/giao diện; `0` = tắt |
| `--min-chars` | Khối chữ phải có ít nhất ngần này chữ mới lấy (mặc định 2) |
| `--no-poly-secondary` | Tắt chế độ "mọi phụ đề phụ đều là đa giác" (mặc định **bật**, chỉ với `--tilt-mode quad`): khi bật, mọi câu **không** thuộc phụ đề chính đều xuất dòng `Đa giác:` / `KP` (kể cả chữ thẳng, cột chữ dọc, câu ngắn, thẻ chữ bay + xoay); phụ đề chính vẫn là hộp chữ nhật đen. Khi tắt, chỉ chữ nghiêng từ `--tilt` độ trở lên mới thành đa giác |
| `--tilt` | Chữ nghiêng từ ngần này độ trở lên (mặc định 2, `0` = tắt) thì thay hộp đen to bằng 1 hộp chính (có chữ) + chuỗi hộp nhỏ không chữ chạy theo đường chéo. Dùng được cả khi chữ **vừa nghiêng/xoay vừa chuyển động** (mỗi hộp có KF riêng) và khi chữ nghiêng tới 80°; cần engine có góc đa giác (paddleocr/easyocr) |
| `--pad` | Nở hộp đen ra mỗi phía = số này × chiều cao 1 dòng chữ, để che hết viền/bóng chữ (mặc định 0.05, tối thiểu 2px: hộp sát chữ; `0` = tắt) |
| `--join-gap` | 2 câu liên tiếp (cùng hàng) cách nhau ≤ số giây này thì nối đuôi câu trước vào đầu câu sau (mặc định 0.5, `0` = tắt) |
| `--no-tighten` | Tắt bước siết hộp OCR theo nét chữ thật (mặc định bật: cắt nền thừa ở mép hộp, mở rộng nếu chữ bị cắt mất; chỉ áp dụng cho chữ thẳng) |
| `--split-sim` | 2 đoạn chữ ổn định kề nhau trong cùng 1 câu mà giống nhau < số này (mặc định 0.85) thì **tách thành 2 câu** (trước đây câu liền kề giống ≥60% bị gộp thành 1). `0` = tắt |
| `--min-run-sec` | Một nội dung phải ổn định ít nhất số giây này mới tính là 1 câu riêng khi tách (mặc định 0.3) |
| `--scale` | Phóng to vùng quét trước khi OCR (chữ nhỏ → tăng lên) |
| `--no-refine` | Tắt bước tinh chỉnh mốc thời gian (xem dưới). Mặc định **bật** |
| `--refine-reach` | Số khung gốc tối đa xét lùi/tới ở mỗi đầu câu khi tinh chỉnh (mặc định `max(bước lấy mẫu, 4)`) |
| `--no-split-jumps` | Tắt bước tách block khi chữ phụ nhảy chỗ (xem dưới). Mặc định **bật** |
| `--jump-rows` | Chữ đổi chỗ từ ngần này lần chiều cao 1 dòng chữ (mặc định 2, tối thiểu 5% chiều cao khung hình) giữa 2 khung lấy mẫu liền nhau mới tính là nhảy; `0` = tắt |
| `--jump-speed` | ...và phải nhanh hơn ngần này chiều cao khung hình mỗi giây (mặc định 0.5). Chữ trượt/bay vào chậm hơn nhiều nên không bị tách |


### Phụ đề phụ: chữ nhảy chỗ thì tạo block mới

Chữ đứng yên ở A suốt vài giây rồi **nhảy** sang B chỉ có 2 keyframe (lúc bắt đầu A, lúc đến B), nên `srtpx_cover` nội suy A → B trên cả khoảng đó: hộp và chữ **trượt chậm** từ A sang B dù thực tế chữ biến mất ở A và hiện ở B trong 1 khung. Nay với **phụ đề phụ** (câu không thuộc nhóm cùng vị trí đông nhất, cùng luật "phụ đề chính" của `srtpx_cover`), nếu giữa 2 khung lấy mẫu liền nhau chữ đổi chỗ ≥ `--jump-rows` × chiều cao 1 dòng chữ **và** nhanh hơn `--jump-speed`, tool **tách thành block mới** bắt đầu đúng lúc chữ hiện ở chỗ mới (mỗi block đứng yên, không có KF trượt qua). Chữ trượt/bay vào thật (chậm) vẫn là 1 block có KF.

- Chỉ tách khi **cả hai mép** ngang (hoặc cả hai mép dọc) cùng dời: chữ dài ra/ngắn đi (một mép đổi) không phải nhảy.
- OCR đo lệch 1–2 khung rồi về chỗ cũ không bị tách; đoạn quá ngắn (< `--min-move-sec`) nhập vào đoạn kế bên.
- Phụ đề chính (hàng chữ ở dưới) không bao giờ bị tách. Không xác định được nhóm chính (ít hơn 2 câu cùng vị trí) thì mọi câu được coi là phụ.
- `--report` in ra các câu bị tách. Test: `python demo/test_jump_split.py`.

### Tinh chỉnh mốc bắt đầu/kết thúc theo khung gốc

OCR chỉ chạy ở các khung lấy mẫu (`--fps 10` trên video 30fps = cứ 3 khung một lần) và hay bỏ sót khung đầu khi chữ đang hiện dần, nên mốc bắt đầu thường trễ 1–3 khung: chữ gốc hiện ra trước rồi 1 khung sau mới có hộp đen. Sau khi gom câu, tool đọc lại các **khung gốc** sát trước đầu/sau cuối mỗi câu (không OCR, chỉ so nét chữ trong vùng chữ) và dời mốc về đúng khung chữ bắt đầu hiện / vừa tắt. Câu chữ chuyển động (có KF) không bị đổi.

## Dịch sang tiếng Việt (Gemini)

`translate_srtpx.py` dịch phần chữ Hán trong file `.srtpx` sang tiếng Việt, giữ nguyên thời gian, `Độ rộng`, `Vị trí`, `KF`.

- **GitHub Actions**: vào Settings → Secrets and variables → Actions → New repository secret, tên `GEMINI_API_KEYS`, giá trị là các API key, **mỗi dòng một key**. Có secret này thì workflow tự dịch sau khi bóc (tắt bằng ô `translate` khi chạy tay). Bản tiếng Trung được giữ ở `output/<tên>.zh.srtpx`. Đổi model: tạo Variable `GEMINI_MODEL` (mặc định `gemini-4-hydrogen`).
- **Trên máy**: tạo file `keys.txt` cạnh script (mỗi dòng một key, file này đã được git bỏ qua), rồi chạy `python translate_srtpx.py video.srtpx -o video_vi.srtpx --keep-original video.zh.srtpx`, hoặc tích ô "Dịch sang tiếng Việt" trong giao diện.
- Key hết quota thì tự đổi sang key kế tiếp; key bị từ chối thì bị loại.
- **Dịch cả file trong 1 lần gọi API** (mặc định `--chunk 0`), để model thấy toàn bộ video và dịch nhất quán. Nếu model trả sai định dạng hoặc quá thời gian (`--timeout`, mặc định 300 giây) thì tự chia đôi rồi dịch lại. Muốn dịch từng đợt thì đặt `--chunk N`.

## Kiểm tra

`python demo/test_regress.py` (gộp câu, chữ dọc, hộp chéo cho chữ xoay/nghiêng) và các `demo/test_*.py` khác.

## Chữ nghiêng / chạy chéo

- **Chữ nghiêng đứng yên** (mặc định `--tilt-mode quad`, nghiêng từ `--tilt` 2° trở lên): xuất thêm dòng `Đa giác: x,y x,y x,y x,y` (4 góc thật: trên-trái, trên-phải, dưới-phải, dưới-trái). `srtpx_cover` vẽ hộp đen theo đa giác; `Độ rộng/Vị trí` vẫn là hộp thẳng nên bản cũ không hiểu dòng này vẫn che được.
- **Chữ nghiêng/xoay + chuyển động** (có KF): mỗi dòng `KF` kèm 1 dòng `KP <giây>s: x,y x,y x,y x,y` (đa giác tại keyframe đó, nội suy giữa các keyframe); cần `srtpx_cover` có "Đa giác theo keyframe". Bản `srtpx_cover` cũ bỏ qua `KP` và che bằng hộp bao to hơn — dùng `--tilt-mode cover` nếu cần.
- **Phụ đề phụ luôn là đa giác** (mặc định, tắt bằng `--no-poly-secondary`): phụ đề chính được nhận bằng `main_lane_ids` (cùng luật với `srtpx_cover/core/maincap.py`); mọi câu còn lại xuất `Đa giác:` (đứng yên) hoặc `KP` ở từng `KF` (chuyển động). Chữ nghiêng từ `--tilt` độ trở lên lấy đa giác OCR (không giới hạn góc, kể cả cột chữ dọc xoay qua 90°, không bắt buộc ≥ 60% khung dựng được); chữ thẳng hoặc khung không có đa giác lấy 4 góc của hộp đã siết theo nét chữ. Thứ tự 4 góc được nối tiếp giữa các keyframe để hộp không bị xoắn khi cột chữ xoay qua 45°. Ở `srtpx_cover` các câu này đi qua lớp vẽ từng khung (như chữ nghiêng) nên xuất video chậm hơn một chút.
- `--tilt-mode cover`: luôn dùng chuỗi hộp chữ nhật nhỏ (cho phần mềm đọc cũ). Test: `python demo/test_quad_output.py`.
