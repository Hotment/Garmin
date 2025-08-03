@echo off
echo Compiling Python script with PyInstaller...

pyinstaller ^
    --name VoiceTriggerApp ^
    --windowed ^
    --onedir ^
    --clean ^
    --icon=icon.ico ^
    --add-data "icon.ico;." ^
    --add-data "config.ini;." ^
    --noconfirm ^
    main.py

echo.
echo Compilation finished.
echo Application files are located in the 'dist/VoiceTriggerApp' directory.
pause
