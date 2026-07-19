# HƯỚNG DẪN THỰC THI TỐI ƯU (V-1/V-2/V-3) — viết cho MỌI model làm theo được

> Cặp với DEXUAT_TOIUU_SOURCE.md (danh sách + lý do + bản đồ rủi ro RM-1..17).
> File này là CHỈ DẪN THI CÔNG: từng bước có (1) lệnh ĐỊNH VỊ, (2) nội dung sửa
> NGUYÊN VĂN, (3) lệnh VERIFY + output kỳ vọng, (4) đường lui khi fail.
> Model thực thi KHÔNG cần suy luận thiết kế — chỉ cần làm đúng, verify đủ.

## 0. QUY TẮC BẮT BUỘC cho model thực thi (đọc trước, tuân thủ tuyệt đối)

1. Đọc `CLAUDE.md` + mục "Phụ lục bản đồ rủi ro" trong `DEXUAT_TOIUU_SOURCE.md`
   trước khi sửa dòng đầu tiên.
2. **CHỈ sửa đúng những gì bước đó liệt kê.** Thấy gì "tiện tay muốn sửa thêm"
   → GHI CHÚ lại, KHÔNG sửa.
3. Sau MỖI file .py sửa xong:
   `.venv\Scripts\python.exe -X utf8 -m py_compile <file>` — phải im lặng.
   Sau MỖI file .js sửa xong: `node --check <file>` — phải im lặng.
4. Sau MỌI lần Edit file (py/js/html), scan ký tự điều khiển:
   ```
   .venv\Scripts\python.exe -X utf8 -c "import io,sys; s=io.open(sys.argv[1],encoding='utf-8',newline='').read(); bad=[hex(ord(c)) for c in s if ord(c)<32 and c not in '\n\r\t']; print('SACH' if not bad else bad)" <file>
   ```
   Phải in `SACH`. (Edit tool từng chèn U+0000 làm chết toàn bộ JS — 2 lần.)
5. Sửa file .py thuộc webui/ → RESTART server bằng preview tool
   (stop/start cấu hình "flowapp"). Sửa .js/.html → chỉ cần F5.
6. Một ĐỢT = một commit. Trước commit: leak-scan
   `git diff | grep -cE "sk-ant-[a-z0-9]{5}|AIza[0-9A-Za-z_-]{10}|hf_[A-Za-z0-9]{20}"`
   phải ra 0. KHÔNG BAO GIỜ commit .env/data/output. Message tiếng Việt, kết
   thúc `Co-Authored-By: Claude <model> <noreply@anthropic.com>`.
7. **Verify FAIL ở bước nào → `git checkout -- <file>` (hoàn nguyên đúng file
   đó), DỪNG đợt, ghi lại hiện tượng, báo user.** Không cố "sửa thêm cho qua".
8. Ghi 1 mục đầu CHANGELOG.md khi xong đợt (mẫu ở mục 5).
9. Job thật của user trong data/jobs KHÔNG được đụng. Test bằng clone
   (id dạng `YYYYMMDD_00000N_aaaXXX`).

---

## 1. ĐỢT V-2 — OCR tuần tự + cache stats (làm TRƯỚC, lợi nhất)

### 1.1 PERF-1: nhánh OCR tuần tự khi OCR_WORKERS ≤ 1

**Bối cảnh phải biết:** ProcessPool scaling ÂM trên desktop (bench: 1 worker
447–465 ms/frame; 4 worker 542–817; 6 worker 855 + 20–27s khởi động pool).
Nhánh tuần tự tái dùng `_init_worker()`/`_ocr_one()` CÓ SẴN → kết quả từng
frame GIỐNG HỆT, chỉ bỏ lớp pool.

**Bước 1 — định vị** (file `core/ocr_subs.py`):
```
grep -n "ProcessPoolExecutor" core/ocr_subs.py
```
Kỳ vọng: 2 dòng (import + with) trong hàm `extract`. Mở đoạn quanh đó, thấy
đúng khối này (nếu KHÁC → dừng, báo user):
```python
    print(f"  OCR: {len(frame_paths)} frame, {config.OCR_WORKERS} worker")
    from concurrent.futures import ProcessPoolExecutor
    from core import progress
    total = len(frame_paths)
    progress.write(work_dir, "transcribing", 0, total)
    all_lines = []
    with ProcessPoolExecutor(max_workers=config.OCR_WORKERS,
                             initializer=_init_worker) as pool:
        for i, res in enumerate(
                pool.map(_ocr_one, [str(p) for p in frame_paths], chunksize=8), 1):
            all_lines.append(res)
            if i % 15 == 0 or i == total:
                progress.write(work_dir, "transcribing", i, total)
```

**Bước 2 — thay bằng** (giữ nguyên mọi thứ trước/sau khối):
```python
    from core import progress
    total = len(frame_paths)
    progress.write(work_dir, "transcribing", 0, total)
    all_lines = []
    if config.OCR_WORKERS <= 1:
        # PERF-1 (DEXUAT_TOIUU_SOURCE 2026-07-13): ProcessPool scaling ÂM trên
        # máy nhiều nhân (bench 1w=465ms/frame, 4w=542-817, 6w=855 + 20-27s
        # spawn pool) — onnxruntime không ăn thêm worker. Tuần tự trong tiến
        # trình, tái dùng đúng _init_worker/_ocr_one nên kết quả GIỐNG TỪNG BYTE.
        print(f"  OCR: {len(frame_paths)} frame, tuần tự (OCR_WORKERS=1)")
        _init_worker()
        for i, p in enumerate(frame_paths, 1):
            all_lines.append(_ocr_one(str(p)))
            if i % 15 == 0 or i == total:
                progress.write(work_dir, "transcribing", i, total)
    else:
        print(f"  OCR: {len(frame_paths)} frame, {config.OCR_WORKERS} worker")
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=config.OCR_WORKERS,
                                 initializer=_init_worker) as pool:
            for i, res in enumerate(
                    pool.map(_ocr_one, [str(p) for p in frame_paths], chunksize=8), 1):
                all_lines.append(res)
                if i % 15 == 0 or i == total:
                    progress.write(work_dir, "transcribing", i, total)
```
**CẤM** trong bước này: sửa `_ocr_one`, `_init_worker`, `_pad_for_detection`,
`_frame_lines`, mọi thứ liên quan crop/pad (RM-10).

**Bước 3 — thêm option "1" vào schema** (file `webui/settings_schema.py`):
định vị `"OCR_WORKERS"` — hiện là
`S("auto", ("auto", "2", "4", "6", "8"), profile=False)` → đổi tuple thành
`("auto", "1", "2", "4", "6", "8")`. (config.py parse int("1") sẵn — KHÔNG sửa
config.) UI (file `webui/static/app-config.js`): định vị `row("OCR_WORKERS"` →
thêm `"1"` vào mảng options + nhãn `{"1": "1 — tuần tự (nhanh nhất trên máy nhiều nhân)"}`
vào object labels (giữ nhãn auto hiện có).

**Bước 4 — verify** (bắt buộc đủ 3 mức):
1. `py_compile` + control-scan (quy tắc 0.3/0.4).
2. Parity: clone 1 job có sẵn OCR (copy `source.mp4` sang
   `data/jobs/<hômnay>_000001_aaa101/`), chạy script (LƯU RA FILE .py rồi chạy
   — KHÔNG chạy qua stdin, Windows spawn sẽ vỡ ProcessPool):
   ```python
   # scratch/run_parity.py
   import sys; sys.path.insert(0, r"F:\MyProject\vietsubvideo")
   if __name__ == "__main__":
       from pathlib import Path
       import json, time, config
       from core import ocr_subs
       d = Path(r"F:\MyProject\vietsubvideo\data\jobs\<id-clone>")
       config.OCR_WORKERS = 1
       t0 = time.time(); s1 = ocr_subs.extract(d/"source.mp4", d); t1 = time.time()-t0
       config.OCR_WORKERS = 4
       t0 = time.time(); s4 = ocr_subs.extract(d/"source.mp4", d); t4 = time.time()-t0
       print("tuần tự:", round(t1), "s | pool4:", round(t4), "s")
       print("PARITY:", "KHỚP" if json.dumps(s1, ensure_ascii=False, sort_keys=True)
             == json.dumps(s4, ensure_ascii=False, sort_keys=True) else "LỆCH — DỪNG, BÁO USER")
   ```
   Kỳ vọng: `PARITY: KHỚP` và thời gian tuần tự NHỎ HƠN rõ rệt. LỆCH → hoàn
   nguyên, dừng.
3. Xoá thư mục clone sau khi xong.

**Bước 5:** hướng dẫn user (KHÔNG tự sửa .env): vào Cấu hình → Nhận dạng →
Nâng cao → Số worker OCR → chọn "1" → Lưu. (Máy laptop: giữ nguyên tới khi
bench trên máy đó — chạy lại đúng script bước 4.)

### 1.2 PERF-2: cache /api/stats TTL 30s

**Định vị** (file `webui/server.py`): `grep -n "_dir_size\|def stats" webui/server.py`
→ thấy `def _dir_size` (~991) và `def stats` (~996). Trong server.py ĐÃ CÓ MẪU
cache đúng kiểu cần làm: `_caps_cache` + hàm `capabilities()` (grep
`_caps_cache`) — BẮT CHƯỚC y hệt mẫu đó:

Trên `def stats()` thêm:
```python
_stats_cache: tuple[float, dict] | None = None   # cache 30s — rglob toàn data/jobs mỗi 10s là phí
```
Đầu thân `stats()` thêm:
```python
    global _stats_cache
    now = time.time()
    if _stats_cache and now - _stats_cache[0] < 30:
        return _stats_cache[1]
```
Cuối hàm, thay `return {...}` bằng:
```python
    data = {...y nguyên dict cũ...}
    _stats_cache = (now, data)
    return data
```
**Verify:** restart server → `curl -s http://127.0.0.1:8790/api/stats` 2 lần
cách nhau 1s: lần 2 phải trả NHANH và giống hệt lần 1; đợi 31s gọi lại → vẫn
JSON hợp lệ. Mở tab Tổng quan trên browser: số liệu hiện bình thường.

---

## 2. ĐỢT V-1 — 9 quick-wins (mỗi mục độc lập; mục nào verify fail thì hoàn nguyên đúng mục đó, các mục khác vẫn giữ)

### 2.1 LINT-1 (phần AN TOÀN — chỉ xoá import chết + F541/F811)
```
.venv\Scripts\python.exe -m ruff check cli.py config.py core/ webui/ scripts/ --select F401,F541,F811
```
Với TỪNG dòng F401 ruff báo: mở đúng file:dòng, xoá ĐÚNG tên import đó (nếu
dòng import nhiều tên thì chỉ xoá tên thừa). Danh sách đã verify an toàn ngày
2026-07-13 (nếu ruff báo THÊM chỗ khác danh sách này → BỎ QUA chỗ đó, ghi chú):
- `webui/server.py`: `import atexit`; và 3 tên `_enqueue_reserved, _release_job,
  _reserve_job` trong khối `from webui.worker import (...)`.
- `webui/routes_editor.py`: dòng `from webui import worker`.
- `webui/common.py`: `import time` (đầu file — LƯU Ý trong file có
  `import time` CỤC BỘ trong `_unlink_quiet`, giữ nguyên cái cục bộ).
- `core/prosody_transfer.py:48`: `import parselmouth` (cục bộ, thừa vì Sound
  đã tạo ở caller — CHỈ xoá dòng import, không đụng logic).
- F541 `core/youtube_upload.py:76`: bỏ tiền tố f của f-string không placeholder.
- F811: ruff chỉ chỗ định nghĩa trùng — xoá bản ĐẦU (bản sau đang hiệu lực).
**KHÔNG** sửa E402 (lazy-load chủ đích), E731/E741 (tùy chọn — bỏ qua nếu
không chắc chắn 100%).
**Verify:** `ruff check --select F401,F541,F811` ra 0; py_compile TỪNG file đã
sửa; restart server; mở app bấm qua 5 tab không lỗi console.

### 2.2 PERF-3: hoãn scheduler trending khỏi import
Định vị `webui/server.py`: `grep -n "_start_trending_scheduler()" webui/server.py`
→ 1 dòng gọi trần (~91). Thay dòng đó bằng:
```python
# PERF-3: apscheduler+trending tốn ~0.7s import — trì hoãn sang thread nền để
# restart server (thao tác lặp nhiều nhất khi dev) nhanh hơn. Daemon: không
# chặn tắt server. Quét trending 1 lần/ngày không cần sẵn sàng giây đầu.
_sched_timer = threading.Timer(5.0, _start_trending_scheduler)
_sched_timer.daemon = True
_sched_timer.start()
```
(`threading` đã import sẵn đầu server.py — kiểm bằng grep, nếu chưa thì thêm.)
**Verify:** restart server, đo bằng log preview: server phải lên nhanh hơn;
sau >5s gọi `curl http://127.0.0.1:8790/api/trending` (hoặc mở tab Phim hot)
vẫn hoạt động như cũ.

### 2.3 DUP-2: /segments đọc 1 lần state + 1 lần .env
File `webui/routes_editor.py`, hàm `get_segments`. Định vị:
`grep -n "json.loads(sp.read_text" webui/routes_editor.py` → 3 chỗ GẦN NHAU
trong get_segments (đọc cùng `state.json`). Giữ MỘT lần đọc sớm nhất thành
biến `job_state`, hai chỗ sau đổi thành đọc từ `job_state` (các key đang lấy:
`render`, `series`, phần job_state đã có sẵn). Tiếp: định vị
`grep -n "cfg_defaults" webui/routes_editor.py` → thấy dict-comprehension gọi
`_read_env()` BÊN TRONG `{k: _read_env().get(...) for k ...}` — hoisting:
```python
    env = _read_env()
    ...
    "cfg_defaults": {k: env.get(k, ...) for k in sorted(_JOB_OVERRIDE_KEYS)},
    ...
    "engines": engine_caps(env),
```
(giữ nguyên biểu thức default trong .get — chỉ thay nguồn env.)
**Verify:** restart; mở editor 1 job có segments trên browser — panel ⚙️ hiện
đủ giá trị, console 0 lỗi; `curl -s http://127.0.0.1:8790/api/jobs/<id>/segments`
trả JSON có đủ key `segments, engines, cfg_defaults`.

### 2.4 DUP-3: _errDetail thành helper chung + vá 5 chỗ không guard
1. Định vị: `grep -n "function _errDetail" webui/static/app-trending.js` → CẮT
   nguyên hàm, DÁN vào `webui/static/app-core.js` ngay SAU hàm `toast(...)`
   (app-core nạp ĐẦU TIÊN nên mọi file sau đều thấy — RM-3: không đổi thứ tự
   nạp).
2. Định vị chỗ chưa guard: `grep -n "res.json()).detail" webui/static/*.js`
   → với TỪNG chỗ, đổi mẫu
   `(await res.json()).detail` → `_errDetail(await res.text(), res.status)`
   (giữ nguyên phần còn lại của dòng).
**Verify:** `node --check` cả 2+ file; browser: tắt server đi (preview stop)
rồi bấm 1 nút gọi API (vd 🗑 xóa job) → phải hiện TOAST lỗi thay vì im lặng;
bật lại server.

### 2.5 ROBUST-1: openGloss catch đúng chỗ
Định vị: `grep -n "catch" webui/static/app-jobs-extra.js | head` quanh hàm
`openGloss` (~174): pattern hiện tại `.json().catch(() => ...)` (catch gắn vào
json) — bọc lại để catch phủ CẢ fetch:
```js
  let data;
  try {
    const res = await fetch(...);
    data = await res.json();
  } catch (e) { toast("Không tải được tên riêng — server đang chạy không?"); return; }
```
(thích nghi theo code thật tại chỗ — mục tiêu: fetch fail KHÔNG được văng
unhandled rejection, phải toast + return.)
**Verify:** node --check; tắt server, bấm 📒 Tên riêng → toast lỗi, console
KHÔNG có "Uncaught (in promise)".

### 2.6 LEAK-1: gỡ resize listener khi mở lại editor
File `webui/static/app-trending.js` (~229): hiện
`window.addEventListener("resize", fitList);` trong `openEditor`. Sửa thành:
```js
  if (window._edResizeHandler) window.removeEventListener("resize", window._edResizeHandler);
  window._edResizeHandler = fitList;
  window.addEventListener("resize", fitList);
```
**Verify:** node --check; mở editor → đóng → mở lại 3 lần, console sạch;
(kiểm leak: DevTools `getEventListeners(window).resize.length` luôn ≤ 1 —
nếu không có DevTools thì bỏ qua kiểm này).

### 2.7 LEAK-2: revoke blob URL nghe thử tab Cấu hình
File `webui/static/app-config.js`, hàm `_cfgPlayBlobUrl` — bắt chước pattern
sẵn có của edPreview (app-editor.js có đoạn revoke URL cũ trước khi gán mới —
grep `revokeObjectURL` để xem mẫu). Sửa:
```js
let _cfgAudioUrl = null;
function _cfgPlayBlobUrl(url) {
  if (_cfgAudio) { _cfgAudio.pause(); _cfgAudio = null; }
  if (_cfgAudioUrl) { URL.revokeObjectURL(_cfgAudioUrl); }
  _cfgAudioUrl = url.startsWith("blob:") ? url : null;
  _cfgAudio = new Audio(url);
  _cfgAudio.play().catch(() => toast("Không phát được âm thanh", "err"));
}
```
(`playFxSample` dùng URL server thường — không cần revoke, giữ nguyên.)
**Verify:** node --check; tab Cấu hình bấm 🔊 nghe thử 2 lần liên tiếp — phát
bình thường cả 2 lần.

### 2.8 JS-1: cache #pending-bar
File `webui/static/app-core.js` (~517-528). Trên hàm `refresh()` (ngoài hàm)
thêm `let _lastPendingBar = null;`. Thay 2 dòng cuối khối:
```js
  if (bh !== _lastPendingBar) {       // đừng hủy-tạo nút mỗi tick 3s — click bị nuốt
    _lastPendingBar = bh;
    bar.style.display = bh ? "" : "none";
    bar.innerHTML = bh;
  }
```
**Verify:** node --check; thêm 1 job pending giả? — KHÔNG cần: chỉ cần mở tab
Jobs, console sạch, thanh vẫn ẩn/hiện đúng khi có job chờ.

### 2.9 SAFE-1: hết nuốt lỗi đọc override per-job
File `webui/worker.py`, định vị `grep -n "env_overrides" webui/worker.py` —
khối `try: _ov = Job.load(job_id).env_overrides ... except Exception: pass`
→ đổi `except Exception: pass` thành:
```python
        except Exception as e:
            print(f"[worker] {job_id}: khong doc duoc override per-job ({e}) - chay bang cau hinh chung")
```
(ASCII THUẦN — RM-12: print phía worker/server có thể chạy khi stdout không
phải UTF-8.) Tương tự tại `webui/server.py` hàm `resume_job` (grep
`except Exception:` quanh `pause_before_render`): thêm print ASCII tương tự
thay vì pass — NẾU thấy đúng pattern nuốt trần; không thấy thì bỏ qua.
**Verify:** py_compile; restart; chạy 1 job clone bất kỳ hết pipeline bình
thường (không in dòng cảnh báo mới là đúng — nó chỉ in khi state hỏng).

---

## 3. ĐỢT V-3 — đúng đắn/chống lệch (làm SAU CÙNG, có parity test)

### 3.1 DUP-4: một chuẩn parse bool env duy nhất
**Quyết định đã chốt (không bàn lại):** ngữ nghĩa chuẩn = "rỗng/thiếu → dùng
default; còn lại: chỉ '0'/'false' là False". Đây là ngữ nghĩa của
`voicesig._truthy` — chọn nó vì sig/override-impact đã dùng, và "rỗng = chưa
đặt" khớp trực giác UI.

1. Tạo file MỚI `core/boolenv.py` (không import gì — để config.py lẫn
   voicesig cùng dùng không lo vòng import):
```python
"""MỘT chuẩn parse bool cho giá trị .env — DEXUAT_TOIUU_SOURCE DUP-4.
Trước đây 3 idiom rải 18 chỗ cho kết quả KHÁC nhau với giá trị bất thường
(ca thật: TTS_SINGLE_VOICE= rỗng → config False nhưng /override-impact True
→ impact dự đoán khác S5 làm thật). Ngữ nghĩa chuẩn: rỗng/thiếu → default;
còn lại chỉ "0"/"false" (mọi hoa thường) là False."""
from __future__ import annotations


def env_bool(v, default: bool) -> bool:
    s = str(v if v is not None else "").strip().lower()
    if not s:
        return default
    return s not in ("0", "false")
```
2. `core/voicesig.py`: thân `_truthy` đổi thành gọi
   `from core.boolenv import env_bool` (import ĐẦU FILE được — boolenv không
   import gì) rồi `return env_bool(v, default)`. GIỮ nguyên chữ ký `_truthy`.
3. Liệt kê nơi cần đổi:
   `grep -rn 'in ("1", "true")\|not in ("0", "false")' config.py core/ webui/ --include="*.py"`
   Với TỪNG dòng: viết lại thành `env_bool(os.getenv("KEY", "<default-cũ>"), <default-bool-cũ>)`
   — **default bool = giá trị khi chuỗi là default-cũ** (vd
   `os.getenv("DENOISE","0")... in ("1","true")` → `env_bool(os.getenv("DENOISE"), False)`;
   `os.getenv("TTS_SINGLE_VOICE","1")...` → `env_bool(os.getenv("TTS_SINGLE_VOICE"), True)`).
   **NGOẠI LỆ KHÔNG ĐỔI:** `config.py` khối STRETCH_SHORT tombstone (RM-13);
   mọi chỗ so sánh chuỗi KHÔNG phải bool (vd KEEP_BGM có 3 giá trị "0/flat/1").
4. **Parity test (bắt buộc chạy, phải PASS 100%):**
```python
# scratch/test_boolparity.py
import sys; sys.path.insert(0, r"F:\MyProject\vietsubvideo")
from core.boolenv import env_bool
from core import voicesig
for v in ["", "0", "1", "true", "false", "True", " 1 ", "2", "yes", None]:
    for d in (True, False):
        assert voicesig._truthy("" if v is None else v, d) == env_bool(v, d), (v, d)
print("BOOL PARITY OK")
# sig không đổi với env bình thường:
seg = {"voice": "nam", "prosody": {}, "emotion": ""}
env = {"TTS_ENGINE": "edge", "MAX_SPEEDUP": "1.2", "TTS_SINGLE_VOICE": "1"}
print(voicesig.voice_signature(seg, voicesig.TtsSettings.from_env(env)))
```
   Chạy thêm: py_compile config.py + mọi file đã sửa; restart server; chạy 1
   job clone ngắn hết pipeline; so sig trên đĩa với resolver (mẫu lệnh xem
   CHANGELOG mục 2026-07-13 (1) — parity 8/8).
5. LƯU Ý HÀNH VI ĐỔI CÓ CHỦ ĐÍCH: giá trị rác ("yes","2") trước là False ở
   config nay là True — chấp nhận (schema UI không cho nhập rác; chỉ ảnh
   hưởng .env sửa tay). Ghi rõ vào CHANGELOG.

### 3.2 GON-1: một hàm ffprobe duration + timeout
1. Thêm vào `core/ffmpeg.py`:
```python
def probe_duration(path, default: float | None = None) -> float:
    """Thời lượng media (giây) qua ffprobe — MỘT bản duy nhất (GON-1, thay 6
    bản copy). timeout 15s: file hỏng làm ffprobe treo là job kẹt vô hạn.
    default=None → lỗi thì raise RuntimeError; truyền số → lỗi trả default."""
    import subprocess
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=15)
        return float((r.stdout or "").strip())
    except Exception as e:
        if default is not None:
            return default
        raise RuntimeError(f"ffprobe không đọc được thời lượng: {path} ({e})")
```
2. 6 call site (định vị lại bằng
   `grep -rn "show_entries.*format=duration" --include="*.py" core/`):
   `core/brand.py:216`, `core/ocr_subs.py:133` (hàm `_duration` — thân đổi
   thành `return ffmpeg.probe_duration(video, default=0.0)`),
   `core/shorts.py:32`, `core/splitter.py:24`, `core/stages/s3_transcript.py:21`,
   `core/thumbnail.py:36`. Quy tắc từng chỗ: chỗ nào hiện đang try/except trả
   0 → `probe_duration(p, default=0.0)`; chỗ nào đang check=True/raise →
   `probe_duration(p)`. Import: các file này đa số đã `from core import ffmpeg`
   — kiểm, thiếu thì thêm.
3. **Verify:** py_compile 7 file; chạy 1 job clone (upload video ngắn) hết
   pipeline; thử file hỏng:
   `python -c "from core import ffmpeg; print(ffmpeg.probe_duration('khongton.mp4', default=0.0))"` → `0.0`.

### 3.3 DUP-5 + RM-17: tài liệu + drift-check tự động
1. `core/voicesig.py` đầu file, thêm vào docstring: dòng cảnh báo
   "LƯU Ý: from_env chứa BẢN SAO THỨ 3 của một số factory default (cặp giọng
   paid, clamp TTS_BASE_SPEED, MAX_SPEEDUP) — CHỦ ĐÍCH để resolver thuần dữ
   liệu; đổi default ở schema/config PHẢI đổi cả đây (drift-check:
   scripts/check_defaults.py)."
   `CLAUDE.md` mục settings_schema: sửa "2 mặt của 1 setting" → "3 mặt: schema
   + config.py + voicesig.from_env (một số khóa giọng)".
2. Tạo `scripts/check_defaults.py` (chạy được là chuẩn — script này ĐÃ chạy
   tay pass 0-lệch ngày 2026-07-11):
```python
"""So default settings_schema.py ↔ os.getenv trong config.py (RM-17).
Chạy: .venv\\Scripts\\python.exe -X utf8 scripts\\check_defaults.py — kỳ vọng 'tổng lệch: 0'."""
import io, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
src = io.open(Path(__file__).resolve().parents[1] / "config.py", encoding="utf-8").read()
from webui.settings_schema import SETTINGS
pat = re.compile(r'os\.getenv\(\s*"([A-Z_0-9]+)"\s*(?:,\s*(.+?))?\)', re.S)
found = {}
for m in pat.finditer(src):
    found.setdefault(m.group(1), (m.group(2) or "").strip())
drift = []
for k, s in SETTINGS.items():
    if s.secret:
        continue
    raw = found.get(k)
    if raw is None:
        drift.append((k, "KHONG thay os.getenv trong config.py", s.default)); continue
    m2 = re.match(r'''^r?["'](.*)["']$''', raw, re.S)
    if not m2:
        drift.append((k, f"default khong phai literal: {raw[:50]}", s.default)); continue
    if m2.group(1) != s.default:
        drift.append((k, f"config.py={m2.group(1)!r}", f"schema={s.default!r}"))
for d in drift:
    print(*d, sep="  |  ")
print("tổng lệch:", len(drift))
sys.exit(1 if drift else 0)
```
3. **Verify:** chạy script → `tổng lệch: 0`, exit 0. Từ nay chạy nó trước MỌI
   commit đụng schema/config.

---

## 4. VERIFY TỔNG cuối mỗi đợt (ngoài verify từng bước)

1. `ruff check cli.py config.py core/ webui/ scripts/` — số cảnh báo KHÔNG
   TĂNG so với trước đợt (sau V-1 phải ≤ 20, toàn E402/E731/E741 chủ đích).
2. `node --check` cả 6 file js.
3. Restart server "flowapp" → mở browser bấm qua 6 tab, console 0 lỗi.
4. Chạy 1 job clone NGẮN hết pipeline (video daula122.mp4 37s trong
   F:\MyProject\videoTQ nếu cần nguồn) — final.mp4 phải ra, mix_report 0 tràn
   bất thường.
5. Đợt V-3 thêm: parity sig trên đĩa (so `.sig` với
   `voicesig.voice_signature(seg, TtsSettings.from_env(env_hiệu_lực))` — mẫu
   trong CHANGELOG 2026-07-13 (1)).
6. Leak-scan + commit + push (quy tắc 0.6) + CHANGELOG (mục 5).

## 5. MẪU CHANGELOG + commit cho từng đợt

```
## YYYY-MM-DD (n) — Desktop|Laptop (đường dẫn repo)

### Đợt V-x: <tên đợt> (theo HUONGDAN_TOIUU_CHITIET.md)

- <mục đã làm: 1 dòng/mục, kèm con số verify (thời gian OCR trước/sau,
  ruff 30→N, parity KHỚP...)>
- Verify: <liệt kê lệnh + kết quả>
- <mục nào BỎ QUA/FAIL + lý do — trung thực, không giấu>
```
Commit message: dòng đầu "Đợt V-x: <tóm tắt> (HUONGDAN_TOIUU_CHITIET.md)",
thân liệt kê mục + số đo, kết `Co-Authored-By: Claude <model> <noreply@anthropic.com>`.

## 6. Những thứ file này CỐ Ý không cho làm (đừng "sáng kiến")

- KHÔNG gộp UI editor/visual (DUP-1 — đã bác có hồ sơ: ngữ nghĩa khác nhau).
- KHÔNG chuyển ES modules, không đổi thứ tự 6 thẻ script (RM-3).
- KHÔNG sửa E402 import-muộn; KHÔNG đụng `_ocr_one/_frame_lines/pad` (RM-10);
  KHÔNG đụng sig/clamp/format (RM-1/2); KHÔNG đọc config.TTS_BASE_SPEED trong
  S7 (RM-9); KHÔNG xoá tombstone STRETCH_SHORT (RM-13); KHÔNG đổi
  trim_silence/cross-term (RM-7/8); KHÔNG "ghi default vào .env cho chắc" (RM-6).
- Gặp bất kỳ tình huống nào NGOÀI kịch bản đã tả → dừng, hỏi user. Không đoán.
