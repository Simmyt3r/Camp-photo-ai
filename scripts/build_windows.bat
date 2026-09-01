@echo off
REM Builds the Windows distributable (spec section 36) via PyInstaller.
REM Must be run ON Windows -- PyInstaller does not cross-compile, so
REM running this on macOS/Linux produces a macOS/Linux binary, not a
REM Windows .exe. See docs/INSTALLATION.md for the full walkthrough.

echo Installing build dependencies...
pip install -r requirements.txt
pip install pyinstaller

echo.
echo Building CampPhotoAI.exe and camp-photo-ai-cli.exe...
pyinstaller pyinstaller.spec --noconfirm

echo.
if exist dist\CampPhotoAI\CampPhotoAI.exe (
    echo Build succeeded.
    echo   GUI: dist\CampPhotoAI\CampPhotoAI.exe
    echo   CLI: dist\camp-photo-ai-cli\camp-photo-ai-cli.exe
    echo.
    echo Move the whole dist\CampPhotoAI folder ^(and/or dist\camp-photo-ai-cli^)
    echo wherever you want to run it from -- Desktop, Documents, a USB drive.
    echo Do NOT put it under Program Files: the app writes its own data/,
    echo logs/, models/, and output/ folders next to the .exe, and standard
    echo Windows accounts can't write there without admin rights.
) else (
    echo Build did not produce the expected .exe -- check the output above for errors.
    exit /b 1
)
