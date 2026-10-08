@echo off
title Celldus Pharma - Cloudflare Live Tunnel
echo ========================================================
echo   Starting Cloudflare Live Tunnel for Celldus Pharma
echo   Forwarding to: http://127.0.0.1:8000
echo ========================================================
echo.
"%~dp0cloudflared.exe" tunnel --url http://127.0.0.1:8000
pause
