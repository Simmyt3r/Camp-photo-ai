@echo off
setlocal
title CampPhoto AI - Pilot Licence Issuer

rem ---------------------------------------------------------------------------
rem CampPhoto AI Phase One licence issuer
rem Silabs internal use only.
rem
rem Keep license_keys\CampPhotoAI_PILOT_PRIVATE_KEY.pem private.
rem Never send the private key to a customer or commit it to Git.
rem ---------------------------------------------------------------------------

for %%I in ("%~dp0..") do set "REPO_ROOT=%%~fI"
set "PRIVATE_KEY=%REPO_ROOT%\license_keys\CampPhotoAI_PILOT_PRIVATE_KEY.pem"
set "ISSUED_DIR=%REPO_ROOT%\issued_licenses"

echo.
echo ============================================================
echo          CAMP PHOTO AI - PILOT LICENCE ISSUER
echo ============================================================
echo  Simeon's Laboratories And Co Technologies Ltd
echo  Pilot activation fee: NGN 10,000
echo ============================================================
echo.

if not exist "%PRIVATE_KEY%" (
    echo [ERROR] Private issuing key was not found:
    echo         %PRIVATE_KEY%
    echo.
    echo Place CampPhotoAI_PILOT_PRIVATE_KEY.pem inside:
    echo         %REPO_ROOT%\license_keys
    echo.
    pause
    exit /b 2
)

set "PYTHON_CMD="
python --version >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=python"

if not defined PYTHON_CMD (
    py -3 --version >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=py -3"
)

if not defined PYTHON_CMD (
    echo [ERROR] Python 3 was not found on this computer.
    echo Install Python 3.11 or later, then run this script again.
    echo.
    pause
    exit /b 2
)

if not exist "%ISSUED_DIR%" mkdir "%ISSUED_DIR%" >nul 2>&1

echo Enter the activation request details exactly as supplied by the customer.
echo.

set /p "DEVICE_ID=Device ID: "
set /p "CAMP=Camp name: "
set /p "STATE=State: "
set /p "BATCH=Batch / Stream: "
set /p "CONTACT_NAME=Contact person's name: "
set /p "CONTACT=Phone or email: "
set /p "PAYMENT_REFERENCE=Payment reference: "
set /p "EXPIRES_ON=Expiry date (YYYY-MM-DD): "

echo.
echo ------------------------------------------------------------
echo VERIFY BEFORE ISSUING
echo ------------------------------------------------------------
echo Device ID:          %DEVICE_ID%
echo Camp:               %CAMP%
echo State:              %STATE%
echo Batch / Stream:     %BATCH%
echo Contact person:     %CONTACT_NAME%
echo Contact:            %CONTACT%
echo Payment reference:  %PAYMENT_REFERENCE%
echo Expiry:             %EXPIRES_ON%
echo Activation fee:     NGN 10,000
echo ------------------------------------------------------------
echo.

if "%DEVICE_ID%"=="" goto :missing
if "%CAMP%"=="" goto :missing
if "%STATE%"=="" goto :missing
if "%BATCH%"=="" goto :missing
if "%CONTACT_NAME%"=="" goto :missing
if "%CONTACT%"=="" goto :missing
if "%PAYMENT_REFERENCE%"=="" goto :missing
if "%EXPIRES_ON%"=="" goto :missing

set /p "PAYMENT_CONFIRMED=Have you personally confirmed the NGN 10,000 payment in the company account? (Y/N): "
if /I not "%PAYMENT_CONFIRMED%"=="Y" (
    echo.
    echo Licence not issued. Confirm payment before generating a licence.
    echo A payment screenshot alone is not confirmation.
    echo.
    pause
    exit /b 1
)

set "OUTPUT_FILE=%ISSUED_DIR%\%DEVICE_ID%-%RANDOM%.cpa-license"

echo.
echo Generating signed offline licence...
echo.

pushd "%REPO_ROOT%"
%PYTHON_CMD% scripts\license_admin.py issue ^
  --device-id "%DEVICE_ID%" ^
  --camp "%CAMP%" ^
  --state "%STATE%" ^
  --batch "%BATCH%" ^
  --contact-name "%CONTACT_NAME%" ^
  --contact "%CONTACT%" ^
  --payment-reference "%PAYMENT_REFERENCE%" ^
  --expires-on "%EXPIRES_ON%" ^
  --private-key "%PRIVATE_KEY%" ^
  --output "%OUTPUT_FILE%"
set "RESULT=%ERRORLEVEL%"
popd

if not "%RESULT%"=="0" (
    echo.
    echo [ERROR] Licence generation failed.
    echo Check the information above, especially the expiry date, and try again.
    echo.
    pause
    exit /b %RESULT%
)

echo.
echo ============================================================
echo LICENCE ISSUED SUCCESSFULLY
echo ============================================================
echo File:
echo %OUTPUT_FILE%
echo.
echo Send ONLY the .cpa-license file to the customer.
echo NEVER send the private .pem key.
echo ============================================================
echo.

start "" explorer "%ISSUED_DIR%"
pause
exit /b 0

:missing
echo.
echo [ERROR] Every field is required. No licence was issued.
echo.
pause
exit /b 2
