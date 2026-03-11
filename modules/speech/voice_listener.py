"""
JARVIS AI — Voice Listener (Phase 5)

Listens for spoken commands and transcribes them using speech recognition
(Whisper or Vosk fallback).
"""

from __future__ import annotations

import os
from typing import Optional

from loguru import logger
import speech_recognition as sr


class VoiceListener:
    """Listens for audio input and converts to text."""

    def __init__(self, engine: str = "whisper", timeout: int = 5, energy_threshold: int = 1000) -> None:
        self.engine = engine.lower()
        self.timeout = timeout
        
        # Initialize recognizer
        self._recognizer = sr.Recognizer()
        self._recognizer.energy_threshold = energy_threshold
        self._recognizer.dynamic_energy_threshold = True

        # Store microphone instance
        self._mic: Optional[sr.Microphone] = None
        self._is_listening = False

    def initialize(self) -> bool:
        """Initialize audio sources and calibrates for ambient noise."""
        try:
            # We try to initialize the default microphone
            self._mic = sr.Microphone()
            logger.info("Calibrating microphone for ambient noise... (1 second)")
            with self._mic as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=1.0)
            logger.info(f"Microphone calibrated. Energy threshold: {self._recognizer.energy_threshold}")
            return True
        except OSError as e:
            logger.error(f"Cannot initialize microphone. Ensure hardware is connected: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error initializing voice listener: {e}")
            return False

    async def listen_for_command(self) -> Optional[str]:
        """
        Listen for a single command and transcribe it.
        This blocks the thread while listening (use in executor or async wrapper).
        """
        if not self._mic:
            logger.warning("Microphone not initialized.")
            return None

        import asyncio
        loop = asyncio.get_running_loop()
        
        # We run the blocking listen in a separate thread
        try:
            audio_data = await loop.run_in_executor(
                None, 
                self._listen_blocking
            )
            
            if audio_data:
                # Transcribe in separate thread
                text = await loop.run_in_executor(
                    None, 
                    self._transcribe_blocking, 
                    audio_data
                )
                return text
                
        except Exception as e:
            logger.error(f"Error during listening/transcribing: {e}")
            
        return None

    def _listen_blocking(self) -> Optional[sr.AudioData]:
        """Block and listen for a phrase."""
        self._is_listening = True
        try:
            logger.debug("Listening for command...")
            with self._mic as source:
                return self._recognizer.listen(
                    source, 
                    timeout=self.timeout, 
                    phrase_time_limit=15
                )
        except sr.WaitTimeoutError:
            logger.debug("Listening timed out (no speech detected).")
            return None
        except Exception as e:
            logger.error(f"Microphone listen error: {e}")
            return None
        finally:
            self._is_listening = False

    def _transcribe_blocking(self, audio: sr.AudioData) -> Optional[str]:
        """Transcribe audio using the configured engine."""
        logger.debug(f"Transcribing audio using {self.engine} engine...")
        
        text = None
        try:
            if self.engine == "whisper":
                # Uses local Whisper model via OpenAI API format, 
                # or built-in speech_recognition whisper integration
                try:
                    # SpeechRecognition latest has local whisper support if 'openai-whisper' is installed
                    text = self._recognizer.recognize_whisper(
                        audio, language="english", model="base"
                    )
                except Exception as e:
                    logger.warning(f"Whisper failed, attempting Google fallback: {e}")
                    text = self._recognizer.recognize_google(audio)
            
            elif self.engine == "vosk":
                # Vosk offline processing
                text = self._recognizer.recognize_vosk(audio)
                # Vosk returns JSON string, we should parse it if valid
                import json
                try:
                    res = json.loads(text)
                    text = res.get("text", "")
                except json.JSONDecodeError:
                    pass
            
            else:
                # Fallback to free Google API
                text = self._recognizer.recognize_google(audio)
                
            if text:
                text = text.strip()
                logger.info(f"Transcription: '{text}'")
                
            return text
            
        except sr.UnknownValueError:
            logger.debug("Speech was unintelligible")
            return None
        except sr.RequestError as e:
            logger.error(f"Could not request results from STT service: {e}")
            return None
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return None
