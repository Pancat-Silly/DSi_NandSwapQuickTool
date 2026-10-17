@echo off
REM DSi Nand Swap Quick Tool - build Windows exe
REM Requires Python 3.9+ from python.org (with tkinter)
setlocal

python -m pip install --upgrade pip
python -m pip install -r requirements-build.txt || goto :error

python scripts\make_version_info.py build\version_info.txt || goto :error

python -m PyInstaller --noconfirm --clean ^
  --onefile --windowed --uac-admin ^
  --name DSi_NSQT ^
  --version-file build\version_info.txt ^
  main.py || goto :error

echo.
echo Build OK: dist\DSi_NSQT.exe
goto :eof

:error
echo Build FAILED
exit /b 1
