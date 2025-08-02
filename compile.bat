@echo off
echo Compiling Python script to EXE with Nuitka...
echo This may take a few minutes.

REM Create a build directory if it doesn't exist
if not exist "build" mkdir "build"

REM The Nuitka command with new dependencies
python -m nuitka ^
    --standalone ^
    --onefile ^
    --output-dir=build ^
    --output-filename=VoiceTriggerApp ^
    --windows-disable-console ^
    --plugin-enable=tk-inter ^
    --plugin-enable=pillow ^
    --plugin-enable=numpy ^
    --include-module=pystray.backends.win32 ^
    --include-module=soundcard ^
    --include-module=mss ^
    --include-module=moviepy ^
    --include-module=thefuzz ^
    --windows-icon-from-ico=icon.ico ^
    --show-progress ^
    --show-memory ^
    voice_trigger_app.py

echo.
echo Compilation finished.
echo Executable is located in the 'build' directory.
pause
