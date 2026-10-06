@echo off
echo Starting Live Tunnel for Celldus Pharma (Port 8000)...
"%TEMP%\cloudflared.exe" tunnel --url http://127.0.0.1:8000
pause
