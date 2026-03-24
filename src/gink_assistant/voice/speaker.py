import platform
import logging

# Set up logging for debugging platform shifts
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("GinkSpeaker")


class GinkSpeaker:
    def __init__(self):
        self.os_type = platform.system()
        self.engine = None
        self._initialize_engine()

    def _initialize_engine(self):
        logger.info(f"🌐 Detecting Platform: {self.os_type}")

        if self.os_type in ["Darwin", "Windows", "Linux"]:
            import pyttsx3
            self.engine = pyttsx3.init()

            # macOS specific driver check
            if self.os_type == "Darwin":
                logger.info("🍎 Using macOS NSSS Driver")

        elif self.os_type == "Android":
            logger.info("🤖 Android detected - Preparing Kivy/Pyjnius Bridge")
            # We will implement the Java bridge here later
            pass

        elif self.os_type == "iOS":
            logger.info("📱 iOS detected - Preparing AVFoundation Bridge")
            # We will implement the Swift/Objective-C bridge here later
            pass

    def say(self, text):
        if self.os_type in ["Darwin", "Windows", "Linux"] and self.engine:
            self.engine.say(text)
            self.engine.runAndWait()
        else:
            print(f"[Speaker Simulation]: {text}")


if __name__ == "__main__":
    speaker = GinkSpeaker()
    speaker.say("Gink Assistant system initialized for cross platform support.")