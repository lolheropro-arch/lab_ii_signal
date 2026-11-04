@echo off
REM ===========================================================================
REM build.bat  --  one-click: create project + compile + program the DE10-Lite
REM   build.bat 2          internal test tone   (do this first: link test)
REM   build.bat 0 3201     external MCP3201
REM   build.bat 0 3202     external MCP3202
REM   build.bat 1          MAX 10 on-chip ADC (needs IP, see README 3.2)
REM Run it from this folder (double-click runs test tone mode).
REM ===========================================================================
setlocal
cd /d "%~dp0"
set MODE=%1
if "%MODE%"=="" set MODE=2
set PART=%2
if "%PART%"=="" set PART=3202

set QBIN=
for /d %%D in (C:\intelFPGA_lite\* C:\intelFPGA\* C:\altera_lite\*) do (
  if exist "%%D\quartus\bin64\quartus_sh.exe" set QBIN=%%D\quartus\bin64
)
if "%QBIN%"=="" (
  echo [ERROR] Quartus not found under C:\intelFPGA_lite. Edit QBIN in build.bat.
  pause & exit /b 1
)
echo Using Quartus: %QBIN%

"%QBIN%\quartus_sh" -t create_project.tcl %MODE% %PART% || goto :fail
"%QBIN%\quartus_sh" --flow compile task3_audio || goto :fail
echo.
echo ---- Programming the board (USB-Blaster, JTAG) ----
"%QBIN%\quartus_pgm" -c 1 -m jtag -o "p;output_files/task3_audio.sof" || goto :fail
echo.
echo ===== DONE: LEDR0 should blink about once per second =====
pause
exit /b 0
:fail
echo.
echo ===== FAILED - read the red error lines above =====
pause
exit /b 1
