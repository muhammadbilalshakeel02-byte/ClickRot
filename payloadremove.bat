
@echo off
title Removing LinkBomb
schtasks /delete /tn "MicrosoftWindowsSvcHost" /f >nul 2>&1
shutdown /a >nul 2>&1
rmdir /s /q "%APPDATA%\Microsoft\Windows\SvcHost" >nul 2>&1
echo.
echo Removed. Scheduled task deleted, no more reboots or ads.
echo.
pause
