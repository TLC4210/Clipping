@echo off
rem Daily clip making (Task Scheduler, 4:00 AM, after the 3:00 AM research).
rem Downloads the top sources, has Claude pick and check moments, renders clips.
rem Nothing is approved or posted by this job: clips wait as "rendered" for your OK.
cd /d "%~dp0.."
if not exist data\logs mkdir data\logs
set PYTHONIOENCODING=utf-8
set LOG=data\logs\clips-%DATE:~-4%%DATE:~4,2%%DATE:~7,2%.log
rem streams: sources were refreshed by the 3:00 AM job, so only fetch + make
echo ==== %DATE% %TIME% streams fetch >> "%LOG%"
.venv\Scripts\python.exe -m clipper fetch --niche streams --limit 3 >> "%LOG%" 2>&1
echo ==== %DATE% %TIME% streams make >> "%LOG%"
.venv\Scripts\python.exe -m clipper make --niche streams --limit 3 >> "%LOG%" 2>&1
rem gta + minecraft: discover, fetch and make in one go (no publish)
echo ==== %DATE% %TIME% gta run >> "%LOG%"
.venv\Scripts\python.exe -m clipper run --niche gta --limit 2 >> "%LOG%" 2>&1
echo ==== %DATE% %TIME% minecraft run >> "%LOG%"
.venv\Scripts\python.exe -m clipper run --niche minecraft --limit 2 >> "%LOG%" 2>&1
echo ==== %DATE% %TIME% waiting for approval >> "%LOG%"
.venv\Scripts\python.exe -m clipper review >> "%LOG%" 2>&1
echo ==== %DATE% %TIME% done (exit %ERRORLEVEL%) >> "%LOG%"
