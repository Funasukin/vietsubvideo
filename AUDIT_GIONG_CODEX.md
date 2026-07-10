# Audit chuoi xu ly GIONG - Codex

Ngay kiem: 2026-07-10
Repo/commit hien tai: `8548d9d`
Pham vi: chi doc code va job artifact co san; khong sua code, khong sua `AUDIT_GIONG.md`.

## 0. Ket luan ngan

Toi dong y voi huong chinh cua audit Claude: loi cam nhan "luc dai luc ngan, toc do/ngu dieu khong tu nhien" khong nam o mot config don le ma nam o viec thoi luong bi dieu khien rai rac qua S4/S5/S7, trong khi viXTTS hien tai lai khong co fit duration o S5.

4 phat hien CONFIRMED trong file goc ve co ban dung tren commit hien tai:

1. `MAX_SPEEDUP` dang duoc dung o ca S5 edge fit va S7 atempo, khong co trong tai tong.
2. Do dai ban dich chi la yeu cau prompt, khong co validator CPS/am tiet.
3. S5 edge fit do full mp3, S7 do ban da trim silence.
4. Overflow sau atempo khong cat/fade, co the tran sang cau sau va vung duck theo `seg.end` khong theo do dai TTS thuc.

Diem can sua so voi audit goc:

- Preview nghe thu khong con "luon edge" trong moi truong hop. Neu segment co `voice_ref`, endpoint dung viXTTS. Tuy nhien neu engine global la `vixtts` ma cau khong co `voice_ref`, preview van roi ve edge, nen van la be mat config co the noi sai.
- `PROSODY`/`EMOTION` trong code mac dinh la bat (`config.py:139-142`), nhung audit goc dua theo `.env` thuc te luc do la tat. Phai tach "nguyen nhan hien tai" voi "bay tai phat neu bat lai".
- `SUB_SPLIT` khong dung audio duration; no chi tach SRT hien thi theo `pieces`, nen khong phai tang gay lech giong.

Khuyen nghi uu tien: lam V1-V4 truoc, nhung nen gom thanh mot module "duration governor" dung chung cho S5/S7/report, thay vi sua tung diem le.

## 1. Kiem chung cac phat hien

### C1. `MAX_SPEEDUP` bi tieu 2 lan - CONFIRMED

Bang chung:

- S5 edge fit tinh ngan sach tu `config.MAX_SPEEDUP`: `core/stages/s5_tts.py:86-90`, `:123-126`.
- S7 tiep tuc atempo bang chinh `config.MAX_SPEEDUP`: `core/stages/s7_mix.py:69-76`.
- UI mo ta day la "Num TONG cho moi lop tang toc": `webui/static/index.html:892-895`.
- Per-job override xep `MAX_SPEEDUP` vao nhom `_OV_MIX`: `webui/server.py:1267`; khi doi chi drop `bgm/mixing/rendering`, khong drop `tts`: `webui/server.py:1397-1400`.

Nhan xet: claim "knob nua tac dung" dung voi engine edge neu mp3 da duoc bake fit rate o S5. Voi viXTTS hien tai thi S5 khong fit, nen override `MAX_SPEEDUP` tac dong chu yeu o S7.

### C2. Ban dich khong co validator do dai - CONFIRMED

Bang chung:

- Prompt co rule do dai tai `core/stages/s4_translate.py:30-32`, `:45-47`, `:60-63`.
- Payload gui `max_s = max(0.5, end-start)`, khong phai slot toi cau ke: `core/stages/s4_translate.py:150-154`.
- Review payload chi co `id/zh/vi/voice`, khong co `max_s`: `core/stages/s4_translate.py:247-256`.
- Review ap fix khong dem am tiet, khong so duration: `core/stages/s4_translate.py:267-286`.
- Gemini hardcode `temperature: 0.7`: `core/llm.py:89-91`.

Nhan xet: day la nguyen nhan upstream quan trong. Sau khi text da qua dai, S5/S7 chi con "chua chay" bang speedup, de nghe gap.

### C3. S5 va S7 do duration bang hai thuoc - CONFIRMED

Bang chung:

- S5 edge fit dung `_mp3_dur_s(out)` tren file mp3 day du: `core/stages/s5_tts.py:93-115`.
- S7 decode roi trim silence hai dau: `core/stages/s7_mix.py:22-38`.

He qua: edge co duoi lang se bi S5 tuong la tran, doc lai nhanh hon can thiet. S7 sau do trim duoi lang nen co the tao cam giac hut/nhanh.

### C4. Overflow sau atempo khong cat/fade - CONFIRMED

Bang chung:

- S7 neu sau atempo van dai hon slot thi chi append warning: `core/stages/s7_mix.py:77-82`.
- Sau do mix den `start + len(voice)`, khong gioi han theo slot: `core/stages/s7_mix.py:84-88`.
- S6 duck theo `[seg.start - 120ms, seg.end + 120ms]`: `core/stages/s6_bgm.py:63-75`.

Nhan xet: neu KEEP_BGM la `flat`, toan bo audio goc bi ha deu nen "vung chua duck" khong con dung theo nghia speech-window. Neu KEEP_BGM=0 speech duck thi claim nay rat dung: TTS tran qua `seg.end+pad` co the de len giong goc chua ha.

### P5. viXTTS khong co kiem soat duration - CONFIRMED/PARTIAL

Bang chung:

- `_tts_vixtts` chi goi `vixtts.synth(...)`, khong gan slot, khong do, khong fit: `core/stages/s5_tts.py:215-234`.
- `core/vixtts.py` goi `model.inference(... temperature=0.7, enable_text_splitting=True)`, khong truyen `speed`: `core/vixtts.py:137-145`.
- XTTS co tham so `speed`, anh huong `length_scale`: `.venv/Lib/site-packages/TTS/tts/models/xtts.py:448-504`.
- Fallback viXTTS loi sang edge ca tap segments: `core/stages/s5_tts.py:329-334`.

Partial: "khong seed" dung theo code goi inference, nhung toi khong kiem chung duoc muc nondeterminism thuc te neu model/runtime co thiet lap noi bo khac.

### P6. Lech ngan sach giua S4 va S5/S7 - CONFIRMED

Bang chung:

- S4 dung `end-start`: `core/stages/s4_translate.py:150-154`.
- S5/S7 dung `next.start-start`: `core/stages/s5_tts.py:291-294`, `core/stages/s7_mix.py:55-67`.

Nhan xet: khac biet nay khong luon xau. Neu co pause tu nhien giua cau, dich theo `end-start` giup khong lap day pause. Nhung pipeline sau lai co xu huong dung slot toi cau ke de nen, nen can co 2 khai niem ro: target = mouth duration, hard limit = next-start slot.

### P7. `TTS_SINGLE_VOICE=1` lam chet mot phan nam/nu va pitch - CONFIRMED

Bang chung:

- `_seg_nu` tra false neu `TTS_SINGLE_VOICE`: `core/stages/s5_tts.py:28-32`.
- Prosody pitch ve 0 khi single voice: `core/prosody.py:47-55`.
- Emotion pitch cung ve 0 khi single voice: `core/emotion.py:72-77`.
- viXTTS emotion sample cung ep gioi "nam" khi single voice: `core/emotion.py:112-118`.

Nhan xet: day khong phai loi neu user muon mot giong. Nhung UI/editor nen hien ro nam/nu per-cau khong anh huong khi single voice bat, tru casting `voice_ref`.

### P8. Khi PROSODY/EMOTION bat, co nhieu nguon rate - CONFIRMED

Bang chung:

- Prosody rate -12..+20: `core/prosody.py:32-35`, `:164-169`.
- Emotion offset rate va kep tong: `core/emotion.py:21-29`, `:72-83`.
- Edge fit them rate: `core/stages/s5_tts.py:118-129`.
- S7 atempo them lan nua: `core/stages/s7_mix.py:69-76`.

Partial: voi config audit goc `PROSODY=0`, `EMOTION=0`, day la bay tai phat chu khong phai nguyen nhan truc tiep cua cac job viXTTS hien tai.

### P9. Preview/config co the noi sai - PARTIAL, audit goc can cap nhat

Bang chung hien tai:

- Preview voi `voice_ref` dung viXTTS: `webui/server.py:1464-1487`.
- Preview paid TTS dung paid engine: `webui/server.py:1489-1511`.
- Preview edge dung `langs.edge_voices()` va emotion kwargs, bo prosody audio: `webui/server.py:1513-1539`.

Sai/loi thoi trong audit goc: khong con dung khi noi "voi config hien tai no doc bang edge trong khi render viXTTS" cho moi cau. Neu cau co `voice_ref`, preview dung viXTTS.

Van con loi: neu `TTS_ENGINE=vixtts` va cau khong co `voice_ref`, S5 render se dung viXTTS voi voice mac dinh (`core/stages/s5_tts.py:227-234`), nhung preview khong co nhanh `eng == "vixtts"` cho cau khong `voice_ref`, nen roi xuong edge. Ngoai ra preview khong fit slot, khong S7 atempo, khong voice_fx/master.

### P10. PROSODY_TRANSFER co rui ro be thanh dieu - PLAUSIBLE

Bang chung:

- Transfer lay contour F0 nguon va ep len TTS bang PSOLA: `core/prosody_transfer.py:74-128`.
- Giu duration, ghi lai mp3 48k: `core/prosody_transfer.py:118-127`.

Nhan xet: rui ro ve thanh dieu tieng Viet la hop ly, nhung can nghe AB test. Code co gate bao thu (`_MIN_DUR_S`, `_MIN_VOICED`, contour voiced), nen khong nen ket luan day la loi khi dang tat.

### P11. Sig thieu slot/rate-fit thuc ap - CONFIRMED/PARTIAL

Bang chung:

- Edge sig co budget `:f{_fit_budget()}` nhung khong co slot, duration raw, hay rate thuc ap sau fit: `core/stages/s5_tts.py:61-63`, `:170-172`.
- viXTTS sig khong co speed/duration vi chua fit: `core/stages/s5_tts.py:57-60`, `:232-234`.

Partial: editor hien tai khong sua `start`, nen slot khong doi qua edit text/voice thong thuong. Nhung neu sau nay cho sua timing, split/merge, hoac S3 rerun giu mp3 cu thi day se thanh loi that.

### P12. Kho tai hien loi - CONFIRMED

Bang chung:

- viXTTS temperature 0.7: `core/vixtts.py:144-145`.
- Cac writer `voice`: LLM `core/stages/s4_translate.py:421-424`, review `:278-285`, gender `:445-457`, speaker profile `:467-477`, user edit `webui/server.py:1312-1324`.
- `mix_report` chi ghi overflow, khong ghi raw duration/trimmed duration/factor: `core/stages/s7_mix.py:77-94`.

Nhan xet: day la van de quan sat duoc. `mix_report` nen thanh artifact chuan de debug moi job.

## 2. Diem bo sot / bo sung

### B1. `s7_mix` atempo dang dung input mp3 chua trim de speed, nhung sau do do lai ban trim

Trong S7, dieu kien `len(voice) > slot` duoc tinh sau trim (`voice = _load_voice(mp3)`), nhung ffmpeg atempo lai chay tren `mp3` goc: `core/stages/s7_mix.py:63-76`. Neu mp3 co silence dau/cuoi, atempo se speed ca silence, sau do `_load_voice(sped)` moi trim lai. Thuong khong qua nghiem trong, nhung no lam factor khong hoan toan la factor cua tin hieu da trim. Giai phap V1 trim sau synth se giai quyet sach.

### B2. `ducked.mode` marker khong ghi raw `KEEP_BGM`

S6 marker: `mode = f"{int(config.KEEP_BGM)}:{'all' if config.DUCK_ALL else 'speech'}:{gain_db:g}"` tai `core/stages/s6_bgm.py:27`. Voi raw `KEEP_BGM=flat`, `KEEP_BGM=False`, `DUCK_ALL=True`, marker thanh `0:all:...`, phan biet duoc voi `0:speech`. Khong phai bug. Nhung marker khong ghi cac tham so nhu `PAD_MS`; neu doi code pad, job cu co the reuse `ducked.wav`.

### B3. Paid TTS khong co duration fit o S5

Paid TTS (`core/stages/s5_tts.py:237-263`) khong co `_fit_slot`; speed trong provider dang fixed (`core/paid_tts.py:95-132`). Neu user chuyen sang paid, duration van chi duoc S7 atempo xu ly. V2 nen mo rong thanh "engine duration adapter" cho viXTTS + paid neu provider ho tro speed.

### B4. `brand.build_audio` doi loudness/mau am, khong doi duration

S8 co voice_fx/music/master (`core/stages/s8_render.py:406-412`, `core/brand.py:63-89`, `core/voice_fx.py:12-26`). No khong giai thich lech slot, nhung co the lam user cam nhan "am dieu/voice mau" khac ban preview, nhat la `dienanh` co echo.

### B5. `SUB_SPLIT`, `splitter`, `shorts` khong phai thu pham audio duration chinh

- `SUB_SPLIT` chi tach text SRT theo `pieces`, comment ghi "Giong doc khong doi": `core/stages/s8_render.py:80-83`.
- `core/splitter.py` cat source thanh job rieng va reset timestamp bang re-encode: `core/splitter.py:58-67`; khong lam lech timing noi bo job neu S2/S3 chay tren source da cat.
- `core/shorts.py` cat tu `final.mp4`, sau khi audio da mix/render; khong anh huong pipeline chinh.

### B6. `segtools` da co tran pieces nhung van can rule cho cau qua ngan/qua dai

`core/segtools.py` da gioi han gap, duration, chars, pieces (`:15-21`, `:80-83`). Nhung van co hai canh kho:

- cau qua ngan: viXTTS co san duration toi thieu nen 1-2 tu de tran;
- cau qua dai/nhieu speaker: 4 pieces co the van qua dai neu slot ngan.

Nen V10 dung huong, nhung can lam bang metric: min mouth duration, max CPS theo ngon ngu, va speaker boundary neu co diarize.

## 3. Danh gia V1-V13

### Nen lam truoc

V1, V2, V3, V4 la goi dung nhat.

Thu tu toi de xuat:

1. V13 truoc mot phan nho: mo rong `mix_report` de co baseline truoc/sau. Rat re, giup khong sua mu.
2. V1: trim/VAD silence sau synth cho moi engine, ghi file da trim hoac duration metric chuan.
3. V3: tao mot duration governor dung chung, `MAX_SPEEDUP` la tran tong.
4. V2: viXTTS fit bang `speed` co gioi han chat luong.
5. V4: sau tran tong thi cut/fade ngan thay vi de overlap.

### Nen lam tiep

V5-V7 dung, nhung khong nen chi dung `slot = next.start-start`. Nen gui cho S4 ca:

- `target_s = end-start` de doc gan mieng/thoai goc;
- `limit_s = next.start-start - breath_pad` de khong de len cau sau;
- `max_syllables`/`max_words` da tinh san.

V6 validator nen dung ham dem am tiet tieng Viet don gian truoc; sau do moi rerun LLM cho cac cau vuot nguong. Dung 1 vong la hop ly de kiem chi phi.

V8-V10 dung cho tu nhien hoa. V8 rat quan trong: neu chi lap day slot, pause tu nhien bien mat; neu chi nen vao slot, cau ngan viXTTS van ngan/dai bat thuong. Target mouth, hard cap slot la mo hinh dung.

V11 dung nhung nen tach hai loai preview:

- "Nghe raw TTS" de chon voice sample;
- "Nghe trong timeline" dung cache/job context, co trim/fit/atempo/voice_fx/bed mot doan ngan.

V12 dung ve UX, nhung nen lam sau khi co governor. Neu gom preset truoc, preset chi che bot do phuc tap nhung loi kien truc van con.

### Rui ro ky thuat

- XTTS `speed` dung `length_scale`; nen gioi han thuc te khoang 0.9-1.25 hoac 0.85-1.3 sau AB test. Qua cao de vo prosody/ro artifacts.
- Neu can speedup lon hon, uu tien "rewrite shorter" hon la ep XTTS.
- Synth-lai voi speed tot hon atempo cho viXTTS neu speed nam trong bien nhe; atempo nen la fallback cuoi va log ro.
- Best-of-N viXTTS theo duration co the hieu qua cho cau ngan, nhung ton GPU va nondeterministic; chi nen dung cho outlier, khong phai default.

## 4. De xuat kien truc "mot trong tai thoi luong"

Tao module moi, vi du `core/duration.py`, khong de logic nam rieng trong S5/S7.

Input moi segment:

- `start`, `end`, `next_start`
- `text_vi`, ngon ngu dich
- engine, voice/ref
- config preset: natural/tight/custom

Output plan:

- `mouth_s = max(0.3, end-start)`
- `slot_s = max(0.3, next_start-start)` hoac total cho cau cuoi
- `target_s = mouth_s` voi clamp nhe theo text length
- `limit_s = max(0.3, slot_s - 0.08/0.12 fade guard)`
- `max_total_speed = MAX_SPEEDUP`
- `engine_speed`, `post_atempo`, `cut_ms`, `status`

Phan cong:

- S4 dung `target_s/limit_s` de tao ngan sach text.
- S5 synth theo engine. Neu engine ho tro speed (viXTTS, mot so paid), synth raw -> trim -> do -> tinh speed -> synth lai toi da 1 lan. Edge co the dung rate nhung phai tinh trong tran tong.
- S7 chi ap `post_atempo` con lai neu S5 chua du, va khong bao gio vuot `max_total_speed / engine_speed_applied`.
- Neu van vuot `limit_s`, cut/fade 80-120ms va log "clipped".
- `mix_report.json` ghi day du: `raw_ms`, `trimmed_ms`, `target_ms`, `limit_ms`, `engine_speed`, `post_atempo`, `final_ms`, `gap_or_overflow_ms`, `clipped`.

Quan trong: S5 va S7 phai do cung mot thang, tot nhat la audio da trim/VAD. Neu van luu mp3 raw, can luu metadata `.dur.json` canh mp3 de S7 khong do lai theo cach khac.

## 5. Phan loai uu tien hanh dong

P0 - do truoc:

- Mo rong `mix_report` (mot phan V13).
- Script/endpoint do cac job hien co bang cung ham S7 trim de co before/after.

P1 - sua goc duration:

- V1 trim sau synth.
- V3 duration governor + cap tong.
- V2 viXTTS speed fit.
- V4 cut/fade overflow.

P2 - sua upstream text:

- V5/V6/V7: budget text co validator va rewrite ngan.

P3 - tu nhien/UX:

- V8/V9/V10: target mouth, slow-down nhe, segment rules.
- V11/V12: preview dung duong render va preset UI.

## 6. Cau tra loi truc tiep cho user

Dung, he thong hien co bi "long ghep chong cheo" qua nhieu tang duration/rate. Voi config viXTTS hien tai, thu pham lon nhat la: ban dich khong bi kiem do dai bang code, viXTTS khong fit duration, S7 phai atempo/canh slot mot minh, va overflow khong bi cat. Voi edge/prosody/emotion, nguy co con nang hon vi rate co the bi cong o nhieu tang.

Huong giai quyet khong nen la them mot knob nua. Nen lam mot trong tai thoi luong duy nhat, co report ro tung cau, roi moi toi preset UX.
