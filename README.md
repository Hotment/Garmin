# PC Dash Cam - Voice-Activated Screen Recorder

PC Dash Cam is a lightweight, background application for Windows that continuously records your screen and audio, much like a dash cam in a car. It keeps a rolling buffer of the last minute of activity and, when triggered by a voice command, saves a video clip of the event, including the moments leading up to and following the command.

This makes it perfect for capturing unexpected moments during gameplay, video calls, or any other screen activity without having to constantly record and manage large video files.

## Features

* **Continuous Background Recording:** Runs silently in the system tray, constantly recording your primary monitor to a temporary in-memory buffer.
* **Voice Activation:** Use a wake phrase like "Ok Garmin" to activate the command listener.
* **Pre- and Post-Event Buffering:** Saves a video clip that includes the 60 seconds *before* you gave the command and the 30 seconds *after*, ensuring you never miss the action.
* **Combined Audio:** Captures both your microphone audio and the system's output audio (e.g., game sounds, call audio) and mixes them into the final video.
* **External Configuration:** All settings, phrases, and languages can be easily modified in a simple `config.ini` file without touching the code.
* **Live Reload:** Refresh the configuration on-the-fly from the system tray menu without restarting the app.
* **Visual Feedback:** A small, semi-transparent "Listening..." window appears on your focused screen to confirm the wake word was heard.
* **Multi-Language Support:** Define command phrases in multiple languages within the configuration file.

## Installation

1.  **Prerequisites:** Ensure you have Python 3.9+ installed on your system.
2.  **Download:** Download the project files (`main.py`, `compile.bat`, etc.) and place them in a folder.
3.  **Install Dependencies:** Open a command prompt or terminal in the project folder and run the following command to install the required Python libraries:
    ```bash
    pip install speechrecognition pystray pillow numpy mss pyaudio moviepy thefuzz pydub configparser
    ```

## Usage

1.  **Run the Application:** Double-click the `main.py` file or run `python main.py` from the terminal.
2.  **System Tray Icon:** The application will start and an icon will appear in your system tray. Right-click the icon for options.
3.  **Voice Command Workflow:**
    * Say the activation phrase (e.g., **"Ok Garmin"**).
    * A beep will sound, and a **"Listening..."** indicator will appear on your focused monitor.
    * You have 10 seconds to say the save command (e.g., **"Save video"**).
    * Three quick beeps will confirm the command was received, and the video clip will be saved in the `recordings` folder.

### Tray Menu Options

* **Settings:** Opens the `config.ini` file in your default text editor for easy modification.
* **Refresh Config:** Reloads all settings from `config.ini` without needing to restart the application.
* **Quit:** Safely stops all recording threads and closes the application.

## Configuration (`config.ini`)

The `config.ini` file allows you to customize the application's behavior.

### `[General]`

* `Monitor`: The monitor to record. `1` is your primary monitor, `2` is your secondary, etc.
* `VideoFPS`: Frames per second for the recording. `15` is a good balance of quality and performance.
* `BufferSeconds`: How many seconds of footage to keep in memory before a command.
* `ExtraRecordSeconds`: How many seconds to continue recording after a command.

### `[Recognition]`

* `PauseThreshold`: How long the app waits for silence before processing a command (in seconds). Lower is faster.
* `NonSpeakingDuration`: Must be equal to or less than `PauseThreshold`.
* `MatchConfidence`: How "sure" the app needs to be to accept a command (as a percentage).
* `ActivationPhrases`: A comma-separated list of wake words.

### `[Commands]`

* Define the "save video" command in different languages. The format is `language-code: command phrase`.

## Compiling to an `.exe`

To create a standalone executable that can be run on any Windows machine (without needing Python installed), simply run the `compile.bat` file. This uses **Nuitka** to package the script and all its dependencies into a single `.exe` file located in the `build` directory.

## To-Do List & Future Ideas

* [ ] **Memory saving:** Switch to a more efficient approach for the video saving.
* [ ] **Full Settings GUI:** Create a proper graphical user interface for the "Settings" option instead of just opening the `.ini` file.
* [ ] **On-the-fly Monitor Switching:** Add an option in the tray menu to switch the recording monitor without editing the config file.
* [ ] **Audio Mixing Controls:** Implement volume controls in the config file to adjust the balance between microphone and system audio.
* [ ] **Automatic Cleanup:** Add a feature to automatically delete recordings older than a certain number of days to save disk space.
* [ ] **Performance Profiles:** Create "High Quality" and "High Performance" presets in the config file that adjust FPS and other settings.
* [ ] **Hardware Acceleration:** Investigate using GPU-accelerated video encoding for better performance on supported systems.