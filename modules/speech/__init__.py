"""
JARVIS AI — Speech System (Phase 5)

Modules for Voice Interface, including wake word detection,
continuous audio streaming, speech-to-text, and text-to-speech.
"""

from .wake_word_detector import WakeWordDetector
from .voice_listener import VoiceListener
from .tts_engine import TTSEngine
from .audio_stream import AudioStreamPipeline

__all__ = [
    "WakeWordDetector",
    "VoiceListener",
    "TTSEngine",
    "AudioStreamPipeline",
]
