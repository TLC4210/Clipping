@echo off
rem Daily analytics check (Task Scheduler, 8:00 AM). Read-only: channel totals and per-video stats
rem for every enabled YouTube channel, with the change since yesterday.
rem Report: data\reports\analytics-YYYY-MM-DD.md
cd /d "%~dp0.."
if not exist data\logs mkdir data\logs
set PYTHONIOENCODING=utf-8
set LOG=data\logs\analytics-%DATE:~-4%%DATE:~4,2%%DATE:~7,2%.log
echo ==== %DATE% %TIME% analytics >> "%LOG%"
.venv\Scripts\python.exe -m clipper analytics >> "%LOG%" 2>&1
echo ==== %DATE% %TIME% done (exit %ERRORLEVEL%) >> "%LOG%"
