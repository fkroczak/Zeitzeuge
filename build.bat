@echo off
REM Baut dist\ZeitZeuge.exe auf dem eigenen PC
py -m pip install -r requirements.txt || exit /b 1
py -m PyInstaller --noconfirm --clean ZeitZeuge.spec || exit /b 1
echo.
echo Fertig: dist\ZeitZeuge.exe
pause
