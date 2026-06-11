# FlowApp — Tự động dịch + lồng tiếng Việt video donghua

Pipeline: tải video (YouTube/Bilibili/Douyin) → đọc phụ đề hardsub bằng OCR
(fallback Whisper) → dịch bằng Claude API → TTS tiếng Việt (edge-tts) → giữ
nhạc nền → phụ đề Việt (soft/burn, che sub gốc) → render. Điều khiển qua
dashboard web local. Kế hoạch chi tiết: [PLAN.md](PLAN.md).

## Cài đặt máy mới (Windows)

Yêu cầu: Python 3.13+ ([python.org](https://python.org)), FFmpeg trong PATH
([gyan.dev](https://www.gyan.dev/ffmpeg/builds/) bản full), git.

```powershell
git clone https://github.com/Funasukin/vietsubvideo.git
cd vietsubvideo
.\run.bat   # tự tạo venv + cài thư viện + tạo .env (điền ANTHROPIC_API_KEY khi notepad mở ra)
```

Lần sau chỉ cần double-click `run.bat`. Kiểm tra API key: `.venv\Scripts\python scripts\check_api.py`

## Sử dụng

**Dashboard (khuyên dùng):** chạy `run.bat` → mở http://127.0.0.1:8790 — 3 tab:
- **Tổng quan**: sản lượng, chi phí dịch ước tính, dung lượng đĩa
- **Jobs**: dán link tạo job, theo dõi tiến độ từng bước, chỉnh phụ đề/vùng che
  với nút Xem thử, xem video thành phẩm, xóa job dọn đĩa
- **Cấu hình**: đổi model dịch / giọng TTS / nguồn transcript ngay trên giao diện

**Dòng lệnh:**
```powershell
.venv\Scripts\python cli.py <link-video>      # chạy pipeline 1 video
.venv\Scripts\python cli.py --resume <job_id> # chạy tiếp job dở (sau lỗi/tắt máy)
```

Kết quả nằm trong `data/jobs/<job_id>/`: `final.mp4`, `sub_vi.srt`,
transcript, báo cáo mix... Mỗi bước có checkpoint — kill giữa chừng không mất gì.

## Script tiện ích (`scripts/`)

| Script | Công dụng |
|---|---|
| `check_api.py` | Kiểm tra API key + credit |
| `refix_job.py <id>` | Áp lại bộ lọc segment (sau khi đổi `core/segtools.py`) rồi dịch lại — không OCR lại |
| `fix_leak_job.py <id>` | Quét + dịch lại các câu sót chữ Hán |
| `rerender.py <id>` | Render lại final.mp4 (đổi cài đặt phụ đề) — không làm lại pipeline |

## Cấu hình (.env)

Xem đủ trong `.env.example`. Đáng chú ý:

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `CLAUDE_MODEL` | claude-haiku-4-5-20251001 | Nâng `claude-sonnet-4-6` nếu cần dịch hay hơn |
| `WHISPER_MODEL` | small | tiny/base/small/medium/large-v3 |
| `TRANSCRIPT_SOURCE` | auto | auto/ocr/whisper |
| `SUBTITLE_MODE` | soft | soft/burn/none (override theo job trên dashboard) |
| `TTS_VOICE` | vi-VN-NamMinhNeural | Giọng nữ: vi-VN-HoaiMyNeural |

## Lưu ý

- Thư mục `data/` (video, job) và `.env` (API key) **không** vào git.
- Thời gian xử lý trên CPU: OCR ~4x thời lượng video là bước chậm nhất
  (kế hoạch tối ưu trong PLAN.md).
- Dự án dùng cho mục đích cá nhân; đăng lại nội dung có bản quyền lên các
  nền tảng là rủi ro tự chịu.
