import speech_recognition as sr
import threading
import winsound
import os
import logging
import time
from PIL import Image
from datetime import datetime
from thefuzz import fuzz
from collections import deque
import numpy as np
import mss, mss.exception
import pyaudio
from moviepy import ImageSequenceClip, AudioFileClip
from scipy.io.wavfile import write as write_wav
import tkinter as tk
from pystray import MenuItem as item, Icon

# --- Configuration ---
VIDEO_FPS = 15
BUFFER_SECONDS = 60
EXTRA_RECORD_SECONDS = 30
SAMPLE_RATE = 44100  # Standard sample rate
AUDIO_FORMAT = pyaudio.paInt16
AUDIO_CHANNELS = 1
AUDIO_CHUNK_SIZE = 1024

# --- Setup Logging ---
if not os.path.exists('logs'):
    os.mkdir('logs')
log_filename = f"logs/app_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
log_format = '[%(asctime)s | %(levelname)s | %(name)s]: %(message)s'
logger_root = logging.getLogger()
logger_root.setLevel(logging.DEBUG)
app_handler = logging.FileHandler(log_filename, encoding="utf-8")
app_handler.setLevel(logging.INFO)
app_handler.setFormatter(logging.Formatter(log_format))
logger_root.addHandler(app_handler)
logger = logger_root.getChild("main")

# --- Recorder Thread ---
class RecorderThread(threading.Thread):
    def __init__(self, name, target, *args, **kwargs):
        super().__init__(name=name, target=target, args=args, kwargs=kwargs, daemon=True)
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def is_stopped(self):
        return self._stop_event.is_set()

# --- Main Application ---
class VoiceTriggerApp:
    def __init__(self):
        self.is_listening = False
        self.is_saving = threading.Event()
        self.recognizer = sr.Recognizer()

        self.recognizer.pause_threshold = 0.4
        self.recognizer.non_speaking_duration = 0.4
        
        self.activation_phrases = ["ok garmin", "ok google"]
        self.command_phrases = {
            "en-US": "save video",
            "pl-PL": "zapisz wideo",
            "de-DE": "video speichern"
        }
        self.match_confidence_threshold = 85

        self.video_buffer = deque(maxlen=VIDEO_FPS * BUFFER_SECONDS)

        # --- PyAudio Setup ---
        self.audio_interface = pyaudio.PyAudio()
        self.mic_audio_buffer = deque(maxlen=int(SAMPLE_RATE / AUDIO_CHUNK_SIZE * BUFFER_SECONDS))
        self.audio_stream = None
       
        self.recognizer.energy_threshold = 3000
        self.recognizer.dynamic_energy_threshold = True

        try:
            with sr.Microphone() as source:
                logger.info("Adjusting for ambient noise. Please be quiet for a moment.")
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
                logger.info("Ambient noise adjustment complete.")
        except Exception as e:
            logger.error(f"Could not adjust for ambient noise: {e}")
        
        self.threads: list[RecorderThread] = []

    def log_message(self, message, level='info'):
        if level == 'error': logger.error(message)
        elif level == 'trigger': logger.info(f"[TRIGGER] {message}")
        elif level == 'user': logger.info(f"[USER] {message}")
        else: logger.info(message)

    def play_activation_sound(self):
        threading.Thread(target=lambda: winsound.Beep(1000, 200), daemon=True).start()

    def play_confirmation_sound(self):
        threading.Thread(target=lambda: [winsound.Beep(1200, 75) for _ in range(3)], daemon=True).start()

    def _record_video(self):
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            while not self.threads[0].is_stopped():
                if not self.is_saving.is_set():
                    try:
                        self.video_buffer.append(sct.grab(monitor))
                    except mss.exception.ScreenShotError as e:
                        self.log_message(f"Video capture error: {e}", "error")
                time.sleep(1 / VIDEO_FPS)

    def _audio_callback(self, in_data, frame_count, time_info, status):
        """This is called by PyAudio for each new chunk of audio."""
        if not self.is_saving.is_set():
            self.mic_audio_buffer.append(in_data)
        return (in_data, pyaudio.paContinue)

    def start_audio_stream(self):
        try:
            self.audio_stream = self.audio_interface.open(
                format=AUDIO_FORMAT,
                channels=AUDIO_CHANNELS,
                rate=SAMPLE_RATE,
                input=True,
                frames_per_buffer=AUDIO_CHUNK_SIZE,
                stream_callback=self._audio_callback
            )
            self.audio_stream.start_stream()
            self.log_message("Microphone stream started successfully.", "info")
        except Exception as e:
            self.log_message(f"Failed to start audio stream: {e}", "error")
            self.audio_stream = None

    def stop_audio_stream(self):
        if self.audio_stream and self.audio_stream.is_active():
            self.audio_stream.stop_stream()
            self.audio_stream.close()
            self.log_message("Microphone stream stopped.", "info")
        self.audio_interface.terminate()
        
    def save_video_clip(self):
        if self.is_saving.is_set():
            self.log_message("Already in the process of saving a clip.", 'warning')
            return

        self.log_message("Save command received. Capturing final 30 seconds.", 'trigger')
        self.is_saving.set()

        video_frames = list(self.video_buffer)

        audio_data_bytes = b''.join(list(self.mic_audio_buffer))
        mic_audio = np.frombuffer(audio_data_bytes, dtype=np.int16)

        extra_frames_to_grab = VIDEO_FPS * EXTRA_RECORD_SECONDS
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            for _ in range(extra_frames_to_grab):
                video_frames.append(sct.grab(monitor))
                time.sleep(1 / VIDEO_FPS)

        self.log_message("Finished recording. Now processing and saving the clip...", 'info')

        if not os.path.exists("recordings"):
            os.makedirs("recordings")
        
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        video_filename = f"recordings/recording_{timestamp}.mp4"
        mic_audio_filename = f"recordings/temp_mic_{timestamp}.wav"
        mic_clip = None

        try:
            rgb_frames = [np.array(frame)[:,:,:3] for frame in video_frames]
            video_clip = ImageSequenceClip(rgb_frames, fps=VIDEO_FPS)

            if len(mic_audio) > 0:
                write_wav(mic_audio_filename, SAMPLE_RATE, mic_audio)
                mic_clip = AudioFileClip(mic_audio_filename)
                video_clip = video_clip.with_audio(mic_clip)
            
            # TODO: Combine mic and system audio before setting it to the clip.

            video_clip.write_videofile(video_filename, codec="libx264", audio_codec="aac", logger=None)
            self.log_message(f"✅ Video saved as {video_filename}", 'trigger')

        except Exception as e:
            self.log_message(f"Failed to save video: {e}", 'error')
            logger.exception("Detailed error during video saving:")
        finally:
            if mic_clip:
                mic_clip.close()
            if os.path.exists(mic_audio_filename): 
                os.remove(mic_audio_filename)
            self.video_buffer.clear()
            self.mic_audio_buffer.clear()
            self.is_saving.clear()
            self.log_message("Ready to capture again.", 'info')

    def listen_for_activation(self):
        while self.is_listening:
            try:
                with sr.Microphone() as source:
                    audio = self.recognizer.listen(source, phrase_time_limit=5)
                
                transcript = self.recognizer.recognize_google(audio, language="en-US").lower()
                self.log_message(f"Heard: \"{transcript}\"", 'user')
                
                for phrase in self.activation_phrases:
                    if fuzz.partial_ratio(phrase, transcript) > self.match_confidence_threshold:
                        self.log_message(f"Activation phrase '{phrase.title()}' detected!", 'trigger')
                        self.handle_activation()
                        break
            except (sr.UnknownValueError, sr.RequestError):
                continue

    def handle_activation(self):
        self.play_activation_sound()
        try:
            with sr.Microphone() as source:
                self.log_message("Listening for command...", 'info')
                command_audio = self.recognizer.listen(source, timeout=10, phrase_time_limit=5)

            for lang_code, phrase in self.command_phrases.items():
                try:
                    recognized_text = self.recognizer.recognize_google(command_audio, language=lang_code).lower()
                    self.log_message(f"Heard: \"{recognized_text}\" (checking against {lang_code})", 'user')
                    if fuzz.partial_ratio(phrase, recognized_text) > self.match_confidence_threshold:
                        self.play_confirmation_sound()
                        threading.Thread(target=self.save_video_clip).start()
                        return
                except (sr.UnknownValueError, sr.RequestError):
                    continue
            self.log_message("Command not recognized.", 'error')
        except sr.WaitTimeoutError:
            self.log_message("No command heard within 10 seconds.", 'error')

    def start_all_threads(self):
        self.log_message("Starting all services...")
        self.is_listening = True
        
        self.threads.append(RecorderThread(name="video_recorder", target=self._record_video))
        self.start_audio_stream()
        self.threads.append(RecorderThread(name="voice_listener", target=self.listen_for_activation))

        for t in self.threads:
            t.start()
        self.log_message("All services running.", 'info')

    def stop_all_threads(self):
        self.log_message("Stopping all services...", 'info')
        self.is_listening = False
        for t in self.threads:
            if t.is_alive():
                t.stop()
        for t in self.threads:
            t.join()
        self.threads.clear()
        self.stop_audio_stream()
        self.log_message("All services stopped.", 'info')

# --- GUI and Tray Icon ---
class SettingsWindow:
    def __init__(self):
        self.window = tk.Tk()
        self.window.title("Configuration")
        tk.Label(self.window, text="Settings will go here.", padx=20, pady=20).pack()
        self.window.mainloop()

def show_settings():
    threading.Thread(target=SettingsWindow, daemon=True).start()

def main():
    app = VoiceTriggerApp()
    
    def quit_app(icon, item):
        app.stop_all_threads()
        icon.stop()

    image = Image.open("icon.ico")
    menu = (item('Settings', show_settings), item('Quit', quit_app))
    icon = Icon("VoiceTriggerApp", image, "Voice Trigger App", menu)

    app.start_all_threads()
    icon.run()

if __name__ == "__main__":
    main()
