"""viXTTS engine — lồng tiếng tiếng Việt NHÂN BẢN giọng, chạy GPU (Coqui XTTS fine-tune).

Tải model 1 lần/tiến trình; cache speaker latent theo clip mẫu. Đầu ra .mp3 để
giữ nguyên interface với S5/S7 (tts/seg_NNNN.mp3).

Phụ thuộc (TUY CHON, cài tay — xem requirements.txt): torch CUDA (cu128, tự gói
sẵn CUDA runtime), coqui-tts, transformers<5, torchcodec, + FFmpeg SHARED (major
4-7) cho torchcodec. Thiếu/lỗi bất kỳ → raise để S5 fallback edge-tts.
"""
from __future__ import annotations

import os
import re
import tempfile
import threading

import config

_model = None
_latent_cache: dict[str, tuple] = {}
# Tuần tự hóa truy cập GPU: model + latent_cache là global dùng chung giữa nhiều
# luồng (nghe thử của dashboard chạy trong threadpool của FastAPI) và unload() do
# luồng khác gọi. RLock vì synth() giữ lock rồi gọi _load() (cũng cần lock).
_gpu_lock = threading.RLock()


def _setup_dll_dirs() -> None:
    """torchcodec cần FFmpeg SHARED. (torch cu128 tự gói CUDA nên không cần thêm.)"""
    if os.name != "nt":
        return
    binp = config.FFMPEG_SHARED_BIN
    if binp and os.path.isdir(binp):
        try:
            os.add_dll_directory(binp)
        except OSError:
            pass
        os.environ["PATH"] = binp + os.pathsep + os.environ.get("PATH", "")


def _vi_clean(txt: str) -> str:
    """Làm sạch text tiếng Việt cho XTTS: thường hóa, đọc số thành chữ."""
    txt = txt.lower()

    def _num(m: re.Match) -> str:
        try:
            from num2words import num2words
            return " " + num2words(int(m.group()), lang="vi") + " "
        except Exception:
            return m.group()

    txt = re.sub(r"\d+", _num, txt)
    return re.sub(r"\s+", " ", txt).strip()


def _load():
    """Tải viXTTS lên GPU (1 lần, thread-safe). Raise nếu thiếu phụ thuộc/model/GPU."""
    global _model
    if _model is not None:
        return _model
    with _gpu_lock:                # chỉ 1 luồng dựng model → tránh double-load gây OOM
        if _model is None:
            _model = _build_model()
        return _model


def _build_model():
    """Dựng model viXTTS (gọi 1 lần dưới _gpu_lock)."""
    if not (config.VIXTTS_DIR / "config.json").exists():
        raise RuntimeError(f"Chưa có model viXTTS tại {config.VIXTTS_DIR} "
                           "(tải capleaf/viXTTS)")
    import time as _time
    _t0 = _time.perf_counter()
    _setup_dll_dirs()

    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import Xtts
    import TTS.tts.layers.xtts.tokenizer as xtok

    # tokenizer gốc chưa biết 'vi' → vá char_limits + preprocess (làm 1 lần)
    if "vi" not in getattr(xtok.VoiceBpeTokenizer, "_vi_patched", {}):
        _orig_pp = xtok.VoiceBpeTokenizer.preprocess_text

        def _pp(self, txt, lang):
            if lang.split("-")[0] == "vi":
                return _vi_clean(txt)
            return _orig_pp(self, txt, lang)

        xtok.VoiceBpeTokenizer.preprocess_text = _pp
        xtok.VoiceBpeTokenizer._vi_patched = {"vi": True}

    cfg = XttsConfig()
    cfg.load_json(str(config.VIXTTS_DIR / "config.json"))
    model = Xtts.init_from_config(cfg)
    model.load_checkpoint(cfg, checkpoint_dir=str(config.VIXTTS_DIR),
                          use_deepspeed=False)
    model.to(config.VIXTTS_DEVICE)
    try:
        model.tokenizer.char_limits["vi"] = 250
    except Exception:
        pass
    # Telemetry W-0: chi phí nạp model lên GPU — dữ liệu quyết định model host
    try:
        import torch
        _vram = int(torch.cuda.memory_allocated() / 1e6) if torch.cuda.is_available() else 0
    except Exception:
        _vram = 0
    print(f"MODEL backend=vixtts event=load seconds={_time.perf_counter() - _t0:.1f} "
          f"device={config.VIXTTS_DEVICE} vram_mb={_vram}")
    return model


def is_available() -> bool:
    """True nếu viXTTS tải + sẵn sàng (thử load 1 lần)."""
    try:
        _load()
        return True
    except Exception as e:
        print(f"  viXTTS không sẵn sàng: {e}")
        return False


def unload() -> None:
    """Nhả model + VRAM. Dashboard gọi trước khi worker (tiến trình con) chạy job
    GPU, để hai tiến trình không cùng giữ viXTTS → tránh OOM trên GPU 8GB. No-op
    nếu chưa nạp."""
    global _model, _latent_cache
    with _gpu_lock:               # đợi synth đang chạy xong rồi mới giải phóng GPU
        if _model is None:
            return
        _model = None
        _latent_cache = {}
        try:
            import gc
            import torch
            gc.collect()
            torch.cuda.empty_cache()
        except Exception:
            pass


def _latents(model, ref_wav: str):
    if ref_wav not in _latent_cache:
        _latent_cache[ref_wav] = model.get_conditioning_latents(audio_path=[ref_wav])
    return _latent_cache[ref_wav]


def synth(text: str, ref_wav: str, out_mp3: str, speed: float = 1.0) -> None:
    """Đọc 1 câu tiếng Việt bằng giọng nhân bản từ ref_wav → ghi out_mp3.

    speed: hệ số tốc độ NGAY LÚC synth (length_scale của XTTS) — nén tự nhiên hơn
    atempo hậu kỳ nhiều. Trọng tài thời lượng (core/duration.py) chỉ truyền trong
    khoảng 1.0–1.25; ngoài khoảng đó XTTS bắt đầu vỡ prosody."""
    # Giữ lock cho phần GPU: chỉ 1 inference/lần (tránh OOM khi nghe thử nhiều dòng)
    # và chặn unload() xen vào giữa khi đang đọc latent_cache / model.
    with _gpu_lock:
        model = _load()
        gpt_cond, spk = _latents(model, ref_wav)
        out = model.inference(text, "vi", gpt_cond, spk,
                              temperature=0.7, enable_text_splitting=True,
                              speed=speed)

    import numpy as np
    import soundfile as sf
    from pydub import AudioSegment

    wav = np.asarray(out["wav"], dtype=np.float32)
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    try:
        sf.write(tmp.name, wav, 24000)
        AudioSegment.from_file(tmp.name).export(out_mp3, format="mp3")
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
