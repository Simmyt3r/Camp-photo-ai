@echo off
setlocal

REM Build an offline Windows package using a buffalo_l model you already
REM possess. This script does NOT download or redistribute model weights.

set MODEL_SOURCE=models\buffalo_l
if exist models\buffalo_l.zip set MODEL_SOURCE=models\buffalo_l.zip

echo.
echo CampPhoto AI offline build
echo ==========================
echo Model source: %MODEL_SOURCE%
echo.

if not exist "%MODEL_SOURCE%" (
    echo ERROR: No local buffalo_l model was found.
    echo.
    echo Put either:
    echo   models\buffalo_l\  ^(with the five ONNX files^)
    echo or
    echo   models\buffalo_l.zip
    echo.
    echo Then run this script again.
    exit /b 2
)

call scripts\build_windows.bat
if errorlevel 1 exit /b %errorlevel%

echo.
echo Bundling local buffalo_l model into GUI and CLI builds...
python scripts\bundle_buffalo_model.py --source "%MODEL_SOURCE%" --required
if errorlevel 1 exit /b %errorlevel%

echo.
echo Creating offline GUI ZIP...
if exist CampPhotoAI-Windows-Offline.zip del /f /q CampPhotoAI-Windows-Offline.zip
powershell -NoProfile -Command "Compress-Archive -Path 'dist\CampPhotoAI\*' -DestinationPath 'CampPhotoAI-Windows-Offline.zip' -Force"
if errorlevel 1 exit /b %errorlevel%

echo.
echo Offline package created successfully:
echo   CampPhotoAI-Windows-Offline.zip
echo.
echo Recipients can unzip it and run CampPhotoAI.exe without downloading
echo buffalo_l on first use.
echo.
echo IMPORTANT: Ensure you have the right to redistribute the pretrained
echo model for your intended use. InsightFace model-zoo weights have their
echo own licence terms and are not covered by CampPhoto AI's code licence.

endlocal
