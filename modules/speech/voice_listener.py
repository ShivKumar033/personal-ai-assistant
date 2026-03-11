"""
JARVIS AI — Voice Listener (Phase 5)

Listens for audio input and converts to text using speech_recognition.
Supports Hindi and English.
"""

from __future__ import annotations

import asyncio
import sys
import os
from typing import Optional, Any
from loguru import logger
import speech_recognition as sr


class VoiceListener:
    """Listens for audio input and converts to text."""

    def __init__(self, engine: str = "whisper", timeout: int = 5, energy_threshold: int = 250) -> None:
        self.engine = engine.lower()
        self.timeout = timeout
        
        # Initialize recognizer
        self._recognizer = sr.Recognizer()
        self._recognizer.energy_threshold = energy_threshold
        self._recognizer.dynamic_energy_threshold = False # Disable auto-climbing threshold
        self._recognizer.pause_threshold = 0.6  # Even faster detection
        self._recognizer.non_speaking_duration = 0.3

        # Store microphone instance
        self._mic: Optional[sr.Microphone] = None
        self._is_listening = False

    def initialize(self) -> bool:
        """Initialize audio sources and calibrates for ambient noise."""
        try:
            self._mic = sr.Microphone()
            logger.info("Calibrating microphone for ambient noise...")
            
            # Store the requested threshold from config
            base_threshold = self._recognizer.energy_threshold
            
            with self._mic as source:
                # Short calibration
                self._recognizer.adjust_for_ambient_noise(source, duration=0.8)
            
            # If calibration made it way noisier than user wanted, compromise
            if self._recognizer.energy_threshold > base_threshold * 2:
                logger.warning(f"Ambient noise is high ({int(self._recognizer.energy_threshold)}). Adjusting closer to your setting.")
                self._recognizer.energy_threshold = (self._recognizer.energy_threshold + base_threshold) / 2
            
            # Extreme safety caps for noisy environments (Kali/Laptops)
            if self._recognizer.energy_threshold > 300:
                logger.warning(f"Extreme noise detected ({int(self._recognizer.energy_threshold)}). Force-capping sensitivity to 300.")
                self._recognizer.energy_threshold = 300
            elif self._recognizer.energy_threshold < 50:
                self._recognizer.energy_threshold = 100
                
            logger.info(f"Microphone ready. Final Sensitivity (Energy Threshold): {int(self._recognizer.energy_threshold)}")
            return True
        except Exception as e:
            logger.error(f"Mic initialization failed: {e}")
            return False

    async def listen_for_command(self) -> Optional[str]:
        """Listen for a single command and transcribe it."""
        if not self._mic:
            return None

        import sys
        import os
        from contextlib import contextmanager

        @contextmanager
        def ignore_stderr():
            devnull = os.open(os.devnull, os.O_WRONLY)
            old_stderr = os.dup(sys.stderr.fileno())
            try:
                os.dup2(devnull, sys.stderr.fileno())
                yield
            finally:
                os.dup2(old_stderr, sys.stderr.fileno())
                os.close(old_stderr)
                os.close(devnull)

        # Visual indicator
        sys.stdout.write("\r   [cyan]👂 Listening...[/cyan]          ")
        sys.stdout.flush()
        
        loop = asyncio.get_running_loop()
        
        try:
            # We run the blocking listen in a separate thread to keep event loop alive
            with ignore_stderr():
                audio_data = await loop.run_in_executor(None, self._listen_blocking)
            
            if audio_data:
                sys.stdout.write("\r   [yellow]⚙️  Processing...[/yellow]          ")
                sys.stdout.flush()
                
                # Transcribe in separate thread
                with ignore_stderr():
                    text = await loop.run_in_executor(None, self._transcribe_blocking, audio_data)
                
                # Clear line and print what we heard
                sys.stdout.write("\r" + " " * 50 + "\r")
                sys.stdout.flush()
                
                if text:
                    logger.info(f"User said: '{text}'")
                return text
            else:
                # No audio caught
                sys.stdout.write("\r" + " " * 50 + "\r")
                sys.stdout.flush()
                return None
                
        except Exception as e:
            sys.stdout.write("\r" + " " * 50 + "\r")
            sys.stdout.flush()
            logger.debug(f"Listening cycle ended: {e}")
            
        return None

    def _listen_blocking(self) -> Optional[sr.AudioData]:
        """Block and listen for a phrase."""
        try:
            with self._mic as source:
                return self._recognizer.listen(
                    source, 
                    timeout=self.timeout, 
                    phrase_time_limit=12
                )
        except sr.WaitTimeoutError:
            return None
        except Exception as e:
            logger.error(f"Mic error: {e}")
            return None

    def _transcribe_blocking(self, audio: sr.AudioData) -> Optional[str]:
        """Transcribe audio using the configured engine."""
        text = None
        
        # We try Google FIRST because it's much faster and supports Hindi perfectly
        # Whisper can be very slow on CPUs without optimization.
        try:
            # Try Hindi first
            try:
                text = self._recognizer.recognize_google(audio, language="hi-IN")
            except:
                # Fallback to English
                text = self._recognizer.recognize_google(audio, language="en-IN")
            
            if text:
                return text.strip()
        except sr.UnknownValueError:
            pass
        except Exception as e:
            logger.debug(f"Google STT failed: {e}")

        # If Google failed or it's forced whisper, try Whisper
        if self.engine == "whisper":
            try:
                text = self._recognizer.recognize_whisper(audio, model="base")
                if text:
                    return text.strip()
            except Exception as e:
                logger.error(f"Whisper STT failed: {e}")

        return None
