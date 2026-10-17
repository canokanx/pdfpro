@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo PDF PRO hata ayiklama modunda aciliyor. Hata olursa bu pencerede gorunur.
where py >nul 2>&1 && (py -3 "%~dp0PDF_PRO.pyw") || (python "%~dp0PDF_PRO.pyw")
pause
