@echo off
cd /d %~dp0
echo FlowApp dashboard: http://127.0.0.1:8790
start http://127.0.0.1:8790
.venv\Scripts\python -m uvicorn webui.server:app --host 127.0.0.1 --port 8790
