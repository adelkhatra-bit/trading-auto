@echo off
setlocal
echo [TRADING-AUTO] Direct webhook setup (no tunnel)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\direct-webhook-setup.ps1"
if errorlevel 1 (
  echo.
  echo [ERROR] Setup failed. Run as Administrator if firewall rule cannot be created.
  exit /b 1
)
echo.
echo [OK] Direct webhook setup finished.
endlocal
