import speech_recognition as sr, threading, winsound, os, logging, time
import numpy as np, mss, mss.exception, pyaudio, tkinter as tk, configparser
from PIL import Image
from datetime import datetime
from thefuzz import fuzz
from collections import deque
from moviepy import ImageSequenceClip, AudioFileClip
from scipy.io.wavfile import write as write_wav
from pystray import MenuItem as item, Icon, _win32
from pydub import AudioSegment

CONFIG_FILE = 'config.ini'

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

# --- Visual Indicator Window ---
class IndicatorWindow(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.overrideredirect(True)
        self.wm_attributes("-topmost", True)
        self.wm_attributes("-alpha", 0.75)
        self.configure(bg='black')
        
        self.label = tk.Label(self, text="Listening...", fg="white", bg="black", font=("Helvetica", 16, "bold"))
        self.label.pack(padx=20, pady=10)
        
        self.withdraw()

    def show(self):
        self.master.after(0, self._show_on_main_thread)

    def _show_on_main_thread(self):
        try:
            mouse_x, mouse_y = self.master.winfo_pointerxy()
            target_monitor = None
            with mss.mss() as sct:
                for monitor in sct.monitors:
                    if (monitor["left"] <= mouse_x < monitor["left"] + monitor["width"] and
                        monitor["top"] <= mouse_y < monitor["top"] + monitor["height"]):
                        target_monitor = monitor
                        break
            
            if target_monitor is None:
                target_monitor = sct.monitors[0]
            
            x_pos = target_monitor["left"] + 20
            y_pos = target_monitor["top"] + 20
            self.geometry(f"+{x_pos}+{y_pos}")
        except Exception as e:
            logger.error(f"Could not position indicator window: {e}")
            screen_width = self.master.winfo_screenwidth()
            self.geometry(f"+{screen_width - self.winfo_width() - 20}+20")

        self.deiconify()

    def hide(self):
        self.master.after(0, self.withdraw)

# --- Main Application ---
class VoiceTriggerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.indicator = IndicatorWindow(self.root)
        self.is_listening = False
        self.is_saving = threading.Event()
        self.recognizer = sr.Recognizer()

        self.load_config()

        self.video_buffer = deque(maxlen=self.video_fps * self.buffer_seconds)

        # --- PyAudio Setup ---
        self.audio_interface = pyaudio.PyAudio()
        self.mic_audio_buffer = deque(maxlen=int(self.sample_rate / self.audio_chunk_size * self.buffer_seconds))
        self.sys_audio_buffer = deque(maxlen=int(self.sample_rate / self.audio_chunk_size * self.buffer_seconds))
        self.mic_stream = None
        self.sys_stream = None
       
        self.recognizer.energy_threshold = 3000
        self.recognizer.dynamic_energy_threshold = True

        try:
            with sr.Microphone() as source:
                logger.info("Adjusting for ambient noise...")
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
                logger.info("Ambient noise adjustment complete.")
        except Exception as e:
            logger.error(f"Could not adjust for ambient noise: {e}")
        
        self.threads: list[RecorderThread] = []

        with mss.mss() as sct:
            self.capture_monitor = sct.monitors[1] # 1 is the primary monitor
            logger.info(f"Locked recording to primary monitor: {self.capture_monitor}")

    def create_default_config(self):
        config = configparser.ConfigParser()
        config['General'] = {
            'VideoFPS': '15',
            'BufferSeconds': '60',
            'ExtraRecordSeconds': '30'
        }
        config['Recognition'] = {
            'PauseThreshold': '0.4',
            'NonSpeakingDuration': '0.4',
            'MatchConfidence': '85',
            'ActivationPhrases': 'ok garmin, ok google'
        }
        config['Commands'] = {
            'en-US': 'save video',
            'pl-PL': 'zapisz wideo',
            'de-DE': 'video speichern'
        }
        with open(CONFIG_FILE, 'w') as configfile:
            config.write(configfile)
        logger.info(f"Created default config file: {CONFIG_FILE}")

    def load_config(self):
        if not os.path.exists(CONFIG_FILE):
            self.create_default_config()
        
        config = configparser.ConfigParser()
        config.read(CONFIG_FILE)
        
        self.video_fps = config.getint('General', 'VideoFPS')
        self.buffer_seconds = config.getint('General', 'BufferSeconds')
        self.extra_record_seconds = config.getint('General', 'ExtraRecordSeconds')
        
        self.recognizer.pause_threshold = config.getfloat('Recognition', 'PauseThreshold')
        self.recognizer.non_speaking_duration = config.getfloat('Recognition', 'NonSpeakingDuration')
        self.match_confidence_threshold = config.getint('Recognition', 'MatchConfidence')
        self.activation_phrases = [p.strip() for p in config.get('Recognition', 'ActivationPhrases').split(',')]
        
        self.command_phrases = dict(config.items('Commands'))
        
        self.sample_rate = 44100
        self.audio_format = pyaudio.paInt16
        self.audio_channels = 1
        self.audio_chunk_size = 1024
        logger.info("Configuration loaded.")

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
            while not self.threads[0].is_stopped():
                if not self.is_saving.is_set():
                    try:
                        self.video_buffer.append(sct.grab(self.capture_monitor))
                    except mss.exception.ScreenShotError as e:
                        self.log_message(f"Video capture error: {e}", "error")
                time.sleep(1 / self.video_fps)

    def _mic_callback(self, in_data, frame_count, time_info, status):
        if not self.is_saving.is_set(): self.mic_audio_buffer.append(in_data)
        return (in_data, pyaudio.paContinue)

    def _sys_audio_callback(self, in_data, frame_count, time_info, status):
        if not self.is_saving.is_set(): self.sys_audio_buffer.append(in_data)
        return (in_data, pyaudio.paContinue)

    def start_audio_stream(self):
        try:
            self.mic_stream = self.audio_interface.open(format=self.audio_format, channels=self.audio_channels, rate=self.sample_rate, input=True, frames_per_buffer=self.audio_chunk_size, stream_callback=self._mic_callback)
            self.mic_stream.start_stream()
            self.log_message("Microphone stream started.")
        except Exception as e:
            self.log_message(f"Failed to start audio stream: {e}", "error")

        try:
            wasapi_info = self.audio_interface.get_host_api_info_by_type(pyaudio.paWASAPI)
            default_speakers_info = self.audio_interface.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
            
            loopback_device_info = None
            for i in range(self.audio_interface.get_device_count()):
                device_info = self.audio_interface.get_device_info_by_index(i)
                if (device_info["hostApi"] == wasapi_info["index"] and 
                    device_info["maxInputChannels"] > 0 and
                    'loopback' in device_info['name'].lower()):
                    if default_speakers_info['name'] in device_info['name']:
                        loopback_device_info = device_info
                        break
            
            if not loopback_device_info:
                self.log_message("Could not find a suitable WASAPI loopback device.", "warning")
                return

            self.sys_stream = self.audio_interface.open(format=self.audio_format, channels=loopback_device_info["maxInputChannels"], rate=int(loopback_device_info["defaultSampleRate"]), input=True, frames_per_buffer=self.audio_chunk_size, input_device_index=loopback_device_info["index"], stream_callback=self._sys_audio_callback)
            self.sys_stream.start_stream()
            self.log_message(f"System audio stream started on '{loopback_device_info['name']}'.")
        except Exception as e:
            self.log_message(f"Failed to start system audio stream: {e}", "error")

    def stop_audio_streams(self):
        for stream in [self.mic_stream, self.sys_stream]:
            if stream and stream.is_active():
                stream.stop_stream()
                stream.close()
        self.audio_interface.terminate()
        self.log_message("Audio streams stopped.")
        
    def save_video_clip(self):
        if self.is_saving.is_set(): return
        self.log_message("Save command received. Capturing final 30 seconds.", 'trigger')
        self.is_saving.set()

        video_frames = list(self.video_buffer)
        mic_data_bytes = b''.join(list(self.mic_audio_buffer))
        sys_data_bytes = b''.join(list(self.sys_audio_buffer))

        extra_frames_to_grab = self.video_fps * self.extra_record_seconds
        with mss.mss() as sct:
            for _ in range(extra_frames_to_grab):
                video_frames.append(sct.grab(self.capture_monitor))
                time.sleep(1 / self.video_fps)

        self.log_message("Finished recording. Now processing and saving the clip...", 'info')
        if not os.path.exists("recordings"): os.makedirs("recordings")
        
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        video_filename = f"recordings/recording_{timestamp}.mp4"
        mic_audio_filename = f"recordings/temp_mic_{timestamp}.wav"
        sys_audio_filename = f"recordings/temp_sys_{timestamp}.wav"
        mixed_audio_filename = f"recordings/temp_mixed_{timestamp}.wav"
        final_clip = None

        try:
            rgb_frames = [np.array(frame)[:,:,:3][:,:,::-1] for frame in video_frames]
            video_clip = ImageSequenceClip(rgb_frames, fps=self.video_fps)

            mic_sound = AudioSegment(data=mic_data_bytes, sample_width=self.audio_interface.get_sample_size(self.audio_format), channels=self.audio_channels, frame_rate=self.sample_rate) if mic_data_bytes else None
            sys_sound = AudioSegment(data=sys_data_bytes, sample_width=self.audio_interface.get_sample_size(self.audio_format), channels=self.audio_channels, frame_rate=self.sample_rate) if sys_data_bytes else None

            if mic_sound and sys_sound:
                mixed_sound = mic_sound.overlay(sys_sound)
                mixed_sound.export(mixed_audio_filename, format="wav")
                final_clip = AudioFileClip(mixed_audio_filename)
            elif mic_sound:
                mic_sound.export(mic_audio_filename, format="wav")
                final_clip = AudioFileClip(mic_audio_filename)
            elif sys_sound:
                sys_sound.export(sys_audio_filename, format="wav")
                final_clip = AudioFileClip(sys_audio_filename)

            if final_clip:
                video_clip = video_clip.with_audio(final_clip)
            
            video_clip.write_videofile(video_filename, codec="libx264", audio_codec="aac", logger=None)
            self.log_message(f"✅ Video saved as {video_filename}", 'trigger')

        except Exception as e:
            self.log_message(f"Failed to save video: {e}", 'error')
            logger.exception("Detailed error during video saving:")
        finally:
            if final_clip: final_clip.close()
            for f in [mic_audio_filename, sys_audio_filename, mixed_audio_filename]:
                if os.path.exists(f): os.remove(f)
            
            self.video_buffer.clear()
            self.mic_audio_buffer.clear()
            self.sys_audio_buffer.clear()
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
        self.indicator.show()
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
        finally:
            self.indicator.hide()

    def start_all_threads(self):
        self.log_message("Starting all services...")
        self.is_listening = True
        self.threads.append(RecorderThread(name="video_recorder", target=self._record_video))
        self.start_audio_stream()
        self.threads.append(RecorderThread(name="voice_listener", target=self.listen_for_activation))
        for t in self.threads: t.start()
        self.log_message("All services running.", 'info')

    def stop_all_threads(self):
        self.log_message("Stopping all services...", 'info')
        self.is_listening = False
        for t in self.threads: t.stop()
        for t in self.threads:
            if t.is_alive(): t.join()
        self.threads.clear()
        self.stop_audio_streams()
        self.log_message("All services stopped.", 'info')

def show_settings(): # Needs immediate expantion
    os.startfile(CONFIG_FILE)

def main():
    root = tk.Tk()
    root.withdraw()

    app = VoiceTriggerApp(root)
    
    def quit_app(icon: _win32.Icon, item):
        logger_root.getChild("QUIT").info("quitting.")
        root.destroy()
        app.stop_all_threads()
        icon.stop()
        logger_root.getChild("QUIT").info("quit.")

    image = Image.open("icon.ico")
    menu = (item('Settings', show_settings), item('Quit', quit_app))
    icon = Icon("VoiceTriggerApp", image, "Voice Trigger App", menu)

    threading.Thread(target=icon.run, daemon=True).start()

    app.start_all_threads()
    root.mainloop()

if __name__ == "__main__":
    main()
