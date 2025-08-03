import speech_recognition as sr, threading, winsound, os, logging, time
import tkinter as tk, configparser, sys, shutil, dxcam
from PIL import Image
from datetime import datetime
from thefuzz import fuzz
from moviepy import VideoFileClip, concatenate_videoclips, AudioFileClip, ImageSequenceClip
from pystray import MenuItem as item, Icon, _win32
from scipy.io.wavfile import write as write_wav

CONFIG_FILE = 'config.ini'
TEMP_DIR = "temp_capture"

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
            self.geometry(f"+{mouse_x + 20}+{mouse_y + 20}")
        except Exception:
            self.geometry(f"+{self.master.winfo_screenwidth() - 200}+20")

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
        self.validate_monitor_index()

        self.recorder_thread = None
        self.stop_recorder_event = threading.Event()
       
        self.recognizer.energy_threshold = 3000
        self.recognizer.dynamic_energy_threshold = True

        try:
            with sr.Microphone() as source:
                logger.info("Adjusting for ambient noise...")
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
                logger.info("Ambient noise adjustment complete.")
        except Exception as e:
            logger.error(f"Could not adjust for ambient noise: {e}")

    def create_default_config(self):
        config = configparser.ConfigParser()
        config['General'] = {
            'Monitor': '1',
            'VideoFPS': '30',
            'BufferSeconds': '60',
            'ExtraRecordSeconds': '30'
        }
        config['Recognition'] = {
            'Recognizer': 'google',
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
        
        self.monitor_index = config.getint('General', 'Monitor')
        self.video_fps = config.getint('General', 'VideoFPS')
        self.buffer_seconds = config.getint('General', 'BufferSeconds')
        self.extra_record_seconds = config.getint('General', 'ExtraRecordSeconds')
        
        self.recognizer_service = config.get('Recognition', 'Recognizer', fallback='google').lower()
        self.recognizer.pause_threshold = config.getfloat('Recognition', 'PauseThreshold')
        self.recognizer.non_speaking_duration = config.getfloat('Recognition', 'NonSpeakingDuration')
        self.match_confidence_threshold = config.getint('Recognition', 'MatchConfidence')
        self.activation_phrases = [p.strip() for p in config.get('Recognition', 'ActivationPhrases').split(',')]
        self.command_phrases = dict(config.items('Commands'))
        
        logger.info(f"Configuration loaded. Using '{self.recognizer_service}' recognizer.")

    def validate_monitor_index(self):
        """Checks if the configured monitor index is valid and defaults to 0 if not."""
        try:
            devices = [line for line in dxcam.output_info().split("\n") if line.strip()]
            if not (0 <= self.monitor_index < len(devices)):
                self.log_message(f"Monitor index {self.monitor_index} is invalid. Available monitors: {len(devices)}. Defaulting to monitor 0.", 'warning')
                self.monitor_index = 0
        except Exception as e:
            self.log_message(f"Could not validate monitor index: {e}. Defaulting to 0.", 'error')
            self.monitor_index = 0

    def refresh_config(self, icon=None, item=None):
        self.log_message("Refreshing configuration...", 'info')
        self.stop_recording()
        self.load_config()
        self.validate_monitor_index()
        self.start_recording()
        self.log_message("Configuration reloaded and recorder restarted.", 'info')

    def log_message(self, message, level='info'):
        if level == 'error': logger.error(message)
        elif level == 'trigger': logger.info(f"[TRIGGER] {message}")
        elif level == 'user': logger.info(f"[USER] {message}")
        else: logger.info(message)

    def play_activation_sound(self):
        threading.Thread(target=lambda: winsound.Beep(1000, 200), daemon=True).start()

    def play_confirmation_sound(self):
        threading.Thread(target=lambda: [winsound.Beep(1200, 75) for _ in range(3)], daemon=True).start()

    def start_recording(self):
        self.log_message("Starting recorder thread...", 'info')
        self.stop_recorder_event.clear()
        self.recorder_thread = threading.Thread(target=self.record_loop, daemon=True)
        self.recorder_thread.start()

    def stop_recording(self):
        self.log_message("Stopping recorder thread...", 'info')
        self.stop_recorder_event.set()
        if self.recorder_thread and self.recorder_thread.is_alive():
            self.recorder_thread.join()
        self.log_message("Recorder thread stopped.", 'info')

    def record_loop(self):
        """Continuously captures video and audio to a file-based circular buffer."""
        if os.path.exists(TEMP_DIR):
            shutil.rmtree(TEMP_DIR)
        os.makedirs(TEMP_DIR)

        camera = dxcam.create(output_color="RGB", output_idx=self.monitor_index)
        camera.start(target_fps=self.video_fps, video_mode=True)
        
        segment_duration = 1 # seconds
        max_segments = self.buffer_seconds // segment_duration
        
        segment_files = []

        while not self.stop_recorder_event.is_set():
            if self.is_saving.is_set():
                time.sleep(0.1)
                continue

            start_time = time.time()
            frames = []
            
            while time.time() - start_time < segment_duration:
                frame = camera.get_latest_frame()
                if frame is not None:
                    frames.append(frame)
                time.sleep(1 / (self.video_fps * 2)) 

            if frames:
                segment_name = f"segment_{int(start_time)}.mp4"
                segment_path = os.path.join(TEMP_DIR, segment_name)
                
                try:
                    clip = ImageSequenceClip(frames, fps=self.video_fps)
                    clip.write_videofile(segment_path, codec="libx264", logger=None)
                    clip.close()
                    segment_files.append(segment_path)
                except Exception as e:
                    self.log_message(f"Error creating video segment: {e}", "error")

            while len(segment_files) > max_segments:
                oldest_segment = segment_files.pop(0)
                if os.path.exists(oldest_segment):
                    os.remove(oldest_segment)
        
        camera.stop()
        
    def save_video_clip(self):
        if self.is_saving.is_set(): return
        self.log_message("Save command received...", 'trigger')
        self.is_saving.set()

        try:
            post_event_frames = []
            camera = dxcam.create(output_color="RGB", output_idx=self.monitor_index)
            camera.start(target_fps=self.video_fps, video_mode=True)
            
            start_time = time.time()
            while time.time() - start_time < self.extra_record_seconds:
                frame = camera.get_latest_frame()
                if frame is not None:
                    post_event_frames.append(frame)
                time.sleep(1 / (self.video_fps * 2))
            camera.stop()

            post_event_path = os.path.join(TEMP_DIR, "post_event.mp4")
            if post_event_frames:
                clip = ImageSequenceClip(post_event_frames, fps=self.video_fps)
                clip.write_videofile(post_event_path, codec="libx264", logger=None)
                clip.close()

            self.log_message("Combining video clips...", 'info')
            if not os.path.exists("recordings"): os.makedirs("recordings")
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            final_filename = f"recordings/recording_{timestamp}.mp4"

            
            buffer_files = sorted([os.path.join(TEMP_DIR, f) for f in os.listdir(TEMP_DIR) if f.startswith("segment")])
            
            clips_to_combine = [VideoFileClip(f) for f in buffer_files]
            if os.path.exists(post_event_path):
                clips_to_combine.append(VideoFileClip(post_event_path))

            if clips_to_combine:
                final_clip = concatenate_videoclips(clips_to_combine)
                # TODO: Add audio mixing here before writing the final file
                final_clip.write_videofile(final_filename, codec="libx264", audio_codec="aac", logger=None)
                final_clip.close()
                for clip in clips_to_combine:
                    clip.close()
                self.log_message(f"✅ Video saved as {final_filename}", 'trigger')
            else:
                self.log_message("No video segments to save.", "warning")

        except Exception as e:
            self.log_message(f"Failed to save video: {e}", 'error')
            logger.exception("Detailed error during video saving:")
        finally:
            if os.path.exists(TEMP_DIR):
                shutil.rmtree(TEMP_DIR)
            self.is_saving.clear()
            self.log_message("Ready to capture again.", 'info')

    def recognize(self, audio, language='en-US'):
        """Dispatcher for different speech recognition services."""
        try:
            if self.recognizer_service == "google":
                return self.recognizer.recognize_google(audio, language=language).lower()
            elif self.recognizer_service == "amazon":
                return self.recognizer.recognize_amazon(audio).lower()
            elif self.recognizer_service == "lex":
                return self.recognizer.recognize_lex(audio, language=language).lower()
            #elif self.recognizer_service == "tensorflow":
                #return self.recognizer.recognize_tensorflow(audio, language=language).lower() Model required
            #elif self.recognizer_service == "vosk":
                #return self.recognizer.recognize_vosk(audio, language=language).lower() 
            else:
                self.log_message(f"Recognizer '{self.recognizer_service}' not supported, defaulting to Google.", 'warning')
                return self.recognizer.recognize_google(audio, language=language).lower()
        except (sr.UnknownValueError, sr.RequestError) as e:
            if not str(e):
                return None
            self.log_message(f"Recognition error: {e}", "error")
            return None

    def listen_for_activation(self):
        while self.is_listening:
            with sr.Microphone() as source:
                try:
                    audio = self.recognizer.listen(source, phrase_time_limit=5)
                    transcript = self.recognize(audio)
                    if transcript:
                        self.log_message(f"Heard: \"{transcript}\"", 'user')
                        for phrase in self.activation_phrases:
                            if fuzz.partial_ratio(phrase, transcript) > self.match_confidence_threshold:
                                self.log_message(f"Activation phrase '{phrase.title()}' detected!", 'trigger')
                                self.handle_activation()
                                break
                except Exception as e:
                    self.log_message(f"Error in listening loop: {e}", "error")


    def handle_activation(self):
        self.play_activation_sound()
        self.indicator.show()
        try:
            with sr.Microphone() as source:
                self.log_message("Listening for command...", 'info')
                command_audio = self.recognizer.listen(source, timeout=10, phrase_time_limit=5)
            
            for lang_code, phrase in self.command_phrases.items():
                recognized_text = self.recognize(command_audio, language=lang_code)
                if recognized_text:
                    self.log_message(f"Heard: \"{recognized_text}\" (checking against {lang_code})", 'user')
                    if fuzz.partial_ratio(phrase, recognized_text) > self.match_confidence_threshold:
                        self.play_confirmation_sound()
                        threading.Thread(target=self.save_video_clip, daemon=True).start()
                        return
            
            self.log_message("Command not recognized.", 'error')
        except sr.WaitTimeoutError:
            self.log_message("No command heard within 10 seconds.", 'error')
        finally:
            self.indicator.hide()

    def start_all_threads(self):
        self.log_message("Starting all services...")
        self.is_listening = True
        self.start_recording()
        self.listener_thread = threading.Thread(name="voice_listener", target=self.listen_for_activation, daemon=True)
        self.listener_thread.start()
        self.log_message("All services running.", 'info')

    def stop_all_threads(self):
        self.log_message("Stopping all services...", 'info')
        self.is_listening = False
        self.stop_recording()
        self.log_message("All services stopped.", 'info')

def show_settings():
    os.startfile(CONFIG_FILE)

def main():
    root = tk.Tk()
    root.withdraw()

    app = VoiceTriggerApp(root)
    
    def quit_app(icon: _win32.Icon, item):
        logger.info("Quit command received. Shutting down.")
        app.stop_all_threads()
        icon.stop()
        root.destroy()
        logger.info("Exiting.")
        sys.exit(0)

    try:
        image = Image.open("icon.ico")
    except FileNotFoundError:
        image = Image.open("_internal/icon.ico")
    menu = (item('Settings', show_settings), item('Refresh Config', app.refresh_config), item('Quit', quit_app))
    icon = Icon("VoiceTriggerApp", image, "Voice Trigger App", menu)

    threading.Thread(target=icon.run, daemon=True).start()

    app.start_all_threads()
    root.mainloop()

if __name__ == "__main__":
    main()
