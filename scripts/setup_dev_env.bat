@echo off
REM Sets up a local development environment for CampPhoto AI on Windows.

python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt

mkdir data 2>nul
mkdir logs 2>nul
mkdir output 2>nul
mkdir models 2>nul

echo.
echo Environment ready. Activate it with: .venv\Scripts\activate.bat
echo Then try:  python -m app.cli --help
