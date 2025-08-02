# PC Dash Cam - Voice-Controlled Screen Recorder

PC Dash Cam is an always-running, low-footprint Windows background app that keeps recording your screen and audio at all times. It has a rolling buffer of the last minute of activity and, upon being triggered by a voice command, saves a video clip of what transpired, including the short time before and after the command.

This makes it perfect to capture surprise moments of gameplay, video calls, or any other screen activity without repeatedly recording and managing large video files.

## Inspiration

The project was inspired by a popular internet meme which made me laugh. I had to replicate the voice-controlled, instant replay functionality for my PC.

## Features

* **Continuous Background Recording:** Runs silently in the system tray, constantly recording your primary monitor to a transient in-memory buffer continuously.
* **Voice Activation:** Use a wake phrase like "Ok Garmin" to activate the command listener.
* **Pre- and Post-Event Buffering:** Saves a video clip that includes the 60 seconds *before* you gave the command and the 30 seconds *after*, so you never miss the action.
* **Mixed Audio:** Captures both your microphone audio and the system's sound (e.g., game sound, call sound) and mixes them into the final video.
* **External Configurability:** All settings, phrases, and languages can be easily modified in a simple `config.ini` file without touching the code.
* **Live Reload:** Reload the config in real time from the system tray menu without requiring a restart of the app.
* **Visual Feedback:** A small, semi-transparent "Listening..." window appears on your current screen to show the wake word was heard.
* **Multi-Language Support:** Define command words in multiple languages in the config file.

## Installation

1.  **Prerequisites:** Install Python 3.9+ on your machine.
2.  **Download:** Clone the repository to your local machine using `git clone`.
3.  **Install Dependencies:** Open a command prompt or terminal in the project folder and run the following command to install all required Python libraries from the `requirements.txt` file:
    ```bash
    pip install -r requirements.txt
    ```

## Usage

1.  **Run the Application:** Double-click on the `main.py` file or run `python main.py` from the terminal.
2.  **System Tray Icon:** The app will launch and show an icon will appear in your system tray. Right-click the icon for options.
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
* `VideoFPS`: Frames per second for the recording. `15` is a good quality vs. performance compromise.
* `BufferSeconds`: Amount of seconds of video to hold in memory before a command.
* `ExtraRecordSeconds`: Amount of seconds to continue recording after a command.

### `[Recognition]`

* `PauseThreshold`: How long the app waits for silence before processing a command (in seconds). Lower is faster.
* `NonSpeakingDuration`: Must be equal to or less than `PauseThreshold`.
* `MatchConfidence`: How "sure" the app needs to be to accept a command (as a percentage).
* `ActivationPhrases`: A comma-separated list of wake words.

### `[Commands]`

* Define the "save video" command in different languages. The format is `language-code: command phrase`.

## Compiling to an `.exe`

To compile to a standalone `.exe` that can be executed on any Windows machine (without the need to have Python installed), simply run the `compile.bat` file. This uses **Nuitka** to package the script and all its dependencies into a single `.exe` file located in the `build` directory.

## To-Do List & Future Ideas

* [ ] **Memory saving:** Switch to a more efficient approach for the video saving.
* [ ] **Full Settings GUI:** Create a proper graphical user interface for the "Settings" option instead of just opening the `.ini` file.
* [ ] **On-the-fly Monitor Switching:** Add an option in the tray menu to switch the recording monitor without editing the config file.
* [ ] **Audio Mixing Controls:** Implement volume controls in the config file to adjust the balance between microphone and system audio.
* [ ] **Automatic Cleanup:** Add a feature to automatically delete recordings older than a certain number of days to save disk space.
* [ ] **Performance Profiles:** Create "High Quality" and "High Performance" presets in the config file that adjust FPS and other settings.
* [ ] **Hardware Acceleration:** Investigate using GPU-accelerated video encoding for better performance on supported systems.