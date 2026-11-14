@echo off
rem Daily competitor research (Task Scheduler, 3:00 AM). Refreshes the creators' YouTube uploads and
rem top Twitch clips, then finds which moments went viral for other clip channels (data\winners.json).
rem Also writes the trending-music report (data\reports\music-<date>.md: what to download).
rem Nothing is downloaded in full, cut, or posted by this job.
cd /d "%~dp0.."
if not exist data\logs mkdir data\logs
set PYTHONIOENCODING=utf-8
set LOG=data\logs\winners-%DATE:~-4%%DATE:~4,2%%DATE:~7,2%.log
echo ==== %DATE% %TIME% discover >> "%LOG%"
.venv\Scripts\python.exe -m clipper discover --niche streams >> "%LOG%" 2>&1
echo ==== %DATE% %TIME% winners >> "%LOG%"
.venv\Scripts\python.exe -m clipper winners --niche streams >> "%LOG%" 2>&1
echo ==== %DATE% %TIME% music >> "%LOG%"
.venv\Scripts\python.exe -m clipper music >> "%LOG%" 2>&1
echo ==== %DATE% %TIME% done (exit %ERRORLEVEL%) >> "%LOG%"
