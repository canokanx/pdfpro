@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
set PYTHONIOENCODING=utf-8
title PDF PRO - Kurulum
cd /d "%~dp0"
color 1F
echo.
echo  ==========================================================
echo                 PDF PRO  -  KURULUM
echo  ==========================================================
echo.

rem ---------------------------------------------------- 1) Python
set "PY="
where py >nul 2>&1 && (py -3 -c "import sys; sys.exit(0 if sys.version_info>=(3,9) else 1)" >nul 2>&1 && set "PY=py -3")
if not defined PY (
    where python >nul 2>&1 && (python -c "import sys; sys.exit(0 if sys.version_info>=(3,9) else 1)" >nul 2>&1 && set "PY=python")
)
if not defined PY (
    echo  [1/4] Python bulunamadi, kuruluyor...
    winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
    set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    if not exist "!PY!" (
        echo.
        echo  [HATA] Python otomatik kurulamadi.
        echo  python.org adresinden Python 3.12 indirip kurun.
        echo  Kurulumda "Add python.exe to PATH" kutusunu ISARETLEYIN.
        echo  Sonra bu dosyayi tekrar calistirin.
        pause
        exit /b 1
    )
    set "PY="!PY!""
) else (
    echo  [1/4] Python bulundu.
)

rem ---------------------------------------------------- 2) Kutuphaneler
echo.
echo  [2/4] Gerekli kutuphaneler kuruluyor (internet gerekir, 1-3 dk)...
%PY% -m pip install --upgrade pip --disable-pip-version-check --no-warn-script-location -q
%PY% -m pip install -r requirements.txt --disable-pip-version-check --no-warn-script-location -q
if errorlevel 1 (
    echo  Ilk deneme basarisiz, kullanici klasorune kuruluyor...
    %PY% -m pip install --user -r requirements.txt --disable-pip-version-check --no-warn-script-location -q
)
%PY% -c "import pymupdf, pdf2docx, openpyxl, docx, pytesseract, PIL, numpy" >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [HATA] Kutuphaneler kurulamadi. Internet baglantinizi kontrol edip tekrar deneyin.
    pause
    exit /b 1
)
echo         Tamam.

rem ---------------------------------------------------- 3) Tesseract OCR
echo.
echo  [3/4] OCR motoru (Tesseract) kontrol ediliyor...
set "TESS="
if exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" set "TESS=1"
if exist "%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe" set "TESS=1"
where tesseract >nul 2>&1 && set "TESS=1"
if defined TESS (
    echo         Tesseract zaten kurulu.
) else (
    echo         Kuruluyor, 1-3 dk surebilir... ^(Gorev cubugunda izin penceresi yanip sonerse EVET deyin^)
    winget install -e --id UB-Mannheim.TesseractOCR --accept-package-agreements --accept-source-agreements --silent
    if exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" set "TESS=1"
    if exist "%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe" set "TESS=1"
    if not defined TESS (
        echo         winget olmadi, dogrudan indiriliyor...
        powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; try { Invoke-WebRequest -UseBasicParsing 'https://github.com/UB-Mannheim/tesseract/releases/download/v5.4.0.20240606/tesseract-ocr-w64-setup-5.4.0.20240606.exe' -OutFile \"$env:TEMP\tesseract_kurulum.exe\" } catch { exit 1 }"
        if exist "%TEMP%\tesseract_kurulum.exe" (
            start /wait "" "%TEMP%\tesseract_kurulum.exe" /S
            del "%TEMP%\tesseract_kurulum.exe" >nul 2>&1
        )
        if exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" set "TESS=1"
    )
    if defined TESS (
        echo         Tesseract kuruldu.
    ) else (
        echo.
        echo  [UYARI] Tesseract kurulamadi. OCR disindaki tum ozellikler calisir.
        echo  OCR icin: https://github.com/UB-Mannheim/tesseract/wiki adresinden
        echo  kurulum dosyasini indirip kurun, sonra bu dosyayi tekrar calistirin.
    )
)
echo         Turkce ve Ingilizce dil dosyalari program klasorunde hazir.

rem ---------------------------------------------------- 4) Kisayol
echo.
echo  [4/4] Masaustu kisayolu olusturuluyor...
%PY% "%~dp0kisayol_olustur.py" >nul 2>&1
if errorlevel 1 (
    echo         Kisayol olusturulamadi; programi PDF_PRO_BASLAT.bat ile acabilirsiniz.
) else (
    echo         Masaustune "PDF PRO" kisayolu eklendi.
)

echo.
echo  ==========================================================
echo     KURULUM TAMAM!  Masaustundeki "PDF PRO" ile acin.
echo  ==========================================================
echo.
choice /c EH /n /m "  Simdi acilsin mi? (E/H): "
if errorlevel 2 exit /b 0
start "" "%~dp0PDF_PRO_BASLAT.bat"
exit /b 0
