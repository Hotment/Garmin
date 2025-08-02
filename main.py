import speech_recognition as sr, threading, winsound, os, logging, logging.handlers
from PIL import ImageGrab
from datetime import datetime
from thefuzz import fuzz

if not os.path.exists('logs'):
    os.mkdir('logs')

class CustomFormatter(logging.Formatter):
    LEVEL_COLORS = {
        logging.DEBUG: "\033[34m",
        logging.INFO: "\033[0m",
        logging.WARNING: "\033[33m",
        logging.ERROR: "\033[31m",
        logging.CRITICAL: "\033[37;41m",
    }

    def format(self, record):
        log_color = self.LEVEL_COLORS.get(record.levelno, "\033[0m")
        log_message = super().format(record)
        return f"{log_color}{log_message.encode(errors='replace').decode()}\033[0m"

log_format = '[%(asctime)s | %(levelname)s | %(name)s]: %(message)s'

logger_root = logging.getLogger()
logger_root.setLevel(logging.DEBUG)

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(CustomFormatter(log_format))
stream_handler.setLevel(logging.INFO)
logger_root.addHandler(stream_handler)

app_handler = logging.handlers.RotatingFileHandler("logs/app.log", maxBytes=5242880, backupCount=5, encoding="utf-8")
app_handler.setLevel(logging.INFO)
app_handler.setFormatter(logging.Formatter(log_format))
logger_root.addHandler(app_handler)

debug_handler = logging.handlers.RotatingFileHandler("logs/debug.log", maxBytes=5242880, backupCount=5, encoding="utf-8")
debug_handler.setLevel(logging.DEBUG)
debug_handler.setFormatter(logging.Formatter(log_format))
logger_root.addHandler(debug_handler)

logger = logger_root.getChild("main")

class VoiceTriggerApp:
    def __init__(self):
        self.is_listening = False
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()

        self.activation_phrases = ["ok garmin", "ok google"]
        self.command_phrases = {
            "en-US": "save video",
            "pl-PL": "zapisz wideo",
            "de-DE": "video speichern"
        }

        self.match_confidence_threshold = 85

        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=1)
        
        self.recognizer.energy_threshold = 3000 
        self.recognizer.dynamic_energy_threshold = True


    def log_message(self, message, tag=None):
        match tag:
            case "error":
                logger.error(message)
            case "trigger":
                logger.info("[TRIGGER] "+message)
            case "user":
                logger.info("[USER] "+message)
            case "info":
                logger.info(message)
            case _:
                logger.warning(message)

    def play_activation_sound(self):
        """Plays a beep sound to indicate activation."""
        try:
            winsound.Beep(1000, 200)
        except Exception as e:
            self.log_message(f"Could not play beep sound: {e}", "error")

    def play_confirmation_sound(self):
        """Plays three short beeps to confirm a command without blocking."""
        def beep_thread():
            try:
                for _ in range(3):
                    winsound.Beep(1200, 75)
            except Exception as e:
                self.log_message(f"Could not play confirmation sound: {e}", "error")
        
        threading.Thread(target=beep_thread, daemon=True).start()

    def save_video(self):
        """Records and saves the last 1m and next 30s"""
        try:
            if not os.path.exists("recordings"):
                os.makedirs("recordings")

            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"recordings/recording_{timestamp}.png"

            

            self.log_message(f"✅ Video saved as {filename}", "trigger")
        except Exception as e:
            self.log_message(f"Failed to take video: {e}", "error")

    def start_listening_thread(self):
        self.is_listening = True
        self.listen_thread = threading.Thread(target=self.listen_for_activation, daemon=True)
        self.listen_thread.start()

    def stop_listening(self):
        self.is_listening = False

    def listen_for_activation(self):
        """Main loop to listen for the activation phrase."""
        while self.is_listening:
            try:
                with self.microphone as source:
                    audio = self.recognizer.listen(source, phrase_time_limit=5)
                
                transcript = self.recognizer.recognize_google(audio, language="en-US").lower()
                self.log_message(f"Heard: \"{transcript}\"", 'user')
                
                for phrase in self.activation_phrases:
                    ratio = fuzz.partial_ratio(phrase, transcript)
                    if ratio > self.match_confidence_threshold:
                        self.log_message(f"✅ Activation phrase '{phrase.title()}' detected with {ratio}% confidence!", "trigger")
                        self.handle_activation()
                        break

            except sr.UnknownValueError:
                continue 
            except sr.RequestError as e:
                self.log_message(f"API Error: {e}", 'error')
                self.stop_listening()
                break
    
    def handle_activation(self):
        """Handles the logic after the activation phrase is detected."""
        self.play_activation_sound()
        
        try:
            with self.microphone as source:
                self.log_message("Listening for command...", "info")
                command_audio = self.recognizer.listen(source, timeout=10, phrase_time_limit=5)

            command_recognized = False
            for lang_code, phrase in self.command_phrases.items():
                try:
                    recognized_text = self.recognizer.recognize_google(command_audio, language=lang_code).lower()
                    self.log_message(f"Heard: \"{recognized_text}\" (checking against {lang_code})", "user")
                    
                    ratio = fuzz.partial_ratio(phrase, recognized_text)
                    if ratio > self.match_confidence_threshold:
                        self.log_message(f"✅ Command '{phrase.title()}' recognized with {ratio}% confidence!", "trigger")
                        self.play_confirmation_sound()
                        self.save_video()
                        command_recognized = True
                        break 
                except sr.UnknownValueError:
                    continue 
            
            if not command_recognized:
                self.log_message("Command not recognized.", "error")

        except sr.WaitTimeoutError:
            self.log_message("No command heard within 10 seconds.", "error")
        except sr.RequestError as e:
            self.log_message(f"API Error during command recognition: {e}", "error")


if __name__ == "__main__":
    app = VoiceTriggerApp()