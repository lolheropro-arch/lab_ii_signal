@echo off
REM run_host.bat  --  double-click: auto-detect the ESP32 port and open the plots
REM   run_host.bat --port COM7        (if auto-detect picks the wrong port)
REM   run_host.bat --check 20         (Fs / lost-block report, no GUI)
cd /d "%~dp0"
python task3_host.py %*
pause
