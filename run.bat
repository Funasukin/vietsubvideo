@echo off
rem FlowApp - chay truc tiep: tu cai dat lan dau (venv, thu vien, .env) roi mo dashboard
cd /d %~dp0
title FlowApp

rem Neu dashboard da chay san thi chi mo trinh duyet
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8790 -State Listen -ErrorAction SilentlyContinue) { exit 1 } else { exit 0 }"
if errorlevel 1 (
  echo FlowApp dang chay san - mo trinh duyet...
  start "" http://127.0.0.1:8790
  exit /b 0
)

rem 1. Python
where python >nul 2>nul
if errorlevel 1 (
  echo [LOI] Chua cai Python. Tai Python 3.13+ tai https://python.org roi chay lai.
  pause
  exit /b 1
)

rem 2. Tao venv neu chua co (lan dau sau khi clone)
if not exist .venv\Scripts\python.exe (
  echo [*] Tao moi truong Python .venv ...
  python -m venv .venv
  if errorlevel 1 ( pause & exit /b 1 )
)

rem 3. Cai thu vien neu thieu
.venv\Scripts\python -c "import fastapi, yt_dlp, edge_tts, anthropic, rapidocr_onnxruntime, faster_whisper" >nul 2>nul
if errorlevel 1 (
  echo [*] Cai thu vien - lan dau mat vai phut...
  .venv\Scripts\pip install -r requirements.txt
  if errorlevel 1 ( echo [LOI] Cai thu vien that bai & pause & exit /b 1 )
)

rem 4. .env - tao tu mau va nhac dien API key
if not exist .env (
  copy .env.example .env >nul
  echo [!] Da tao file .env - HAY DIEN ANTHROPIC_API_KEY tu console.anthropic.com roi luu lai.
  notepad .env
)

rem 5. FFmpeg
where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo [!] Chua thay FFmpeg trong PATH - tai ban full tai https://www.gyan.dev/ffmpeg/builds/
  echo     Pipeline se loi o buoc tach audio neu thieu.
  pause
)

rem 6. Chay dashboard
echo.
echo FlowApp dashboard: http://127.0.0.1:8790  (dong cua so nay de tat)
start "" http://127.0.0.1:8790
.venv\Scripts\python -m uvicorn webui.server:app --host 127.0.0.1 --port 8790
pause
