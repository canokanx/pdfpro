@echo off
cd /d "%~dp0"
set PDFPRO_AYRI_SUREC=1
where pyw >nul 2>&1 && (start "" pyw -3 "%~dp0PDF_PRO.pyw" & exit /b 0)
where pythonw >nul 2>&1 && (start "" pythonw "%~dp0PDF_PRO.pyw" & exit /b 0)
python "%~dp0PDF_PRO.pyw"
if errorlevel 1 pause
