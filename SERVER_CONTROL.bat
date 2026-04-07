@echo off
echo ================================
echo   NovaLuce Server Control
echo ================================
echo.
echo  [1] Start
echo  [2] Stop
echo  [3] Restart
echo  [4] Status
echo  [5] Quitter
echo.
set /p choice="Choix : "
if "%choice%"=="1" node server-manager.js start
if "%choice%"=="2" node server-manager.js stop
if "%choice%"=="3" node server-manager.js restart
if "%choice%"=="4" node server-manager.js status
if "%choice%"=="5" exit
pause
