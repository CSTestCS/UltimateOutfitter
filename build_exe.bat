@echo off
REM Builds dist\UltimateOutfitter.exe on Windows. Requires Python 3.10+ on PATH.
python -m venv .venv || goto :error
call .venv\Scripts\activate.bat || goto :error
python -m pip install --upgrade pip || goto :error
python -m pip install -r requirements.txt pyinstaller || goto :error
pyinstaller --noconfirm --clean UltimateOutfitter.spec || goto :error
echo.
echo Done: dist\UltimateOutfitter.exe
goto :eof
:error
echo Build failed with error %errorlevel%.
exit /b %errorlevel%
