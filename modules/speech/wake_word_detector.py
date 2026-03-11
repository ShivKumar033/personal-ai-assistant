"""
JARVIS AI — Wake Word Detector (Phase 5)

Uses Picovoice Porcupine to detect the "Jarvis" wake word.
"""

from __future__ import annotations

import struct
from typing import Optional

from loguru import logger
import pvporcupine


class WakeWordDetector:
    """Listens for the wake word using Porcupine."""

    def __init__(
        self,
        access_key: str,
        keyword: str = "jarvis",
        sensitivity: float = 0.5,
    ) -> None:
        self.access_key = access_key
        self.keyword = keyword
        self.sensitivity = sensitivity
        self._porcupine: Optional[pvporcupine.Porcupine] = None

    def initialize(self) -> bool:
        """Initialize the Porcupine engine."""
        if not self.access_key:
            logger.warning(
                "No Porcupine access key provided in settings. "
                "Wake word detection will be disabled."
            )
            return False

        try:
            self._porcupine = pvporcupine.create(
                access_key=self.access_key,
                keywords=[self.keyword],
                sensitivities=[self.sensitivity],
            )
            logger.info(f"Wake word '{self.keyword}' detector initialized.")
            return True
        except pvporcupine.PorcupineError as e:
            logger.error(f"Failed to initialize Porcupine: {e}")
            return False

    @property
    def sample_rate(self) -> int:
        """Required audio sample rate for Porcupine."""
        if self._porcupine:
            return self._porcupine.sample_rate
        return 16000

    @property
    def frame_length(self) -> int:
        """Required audio frame length for Porcupine."""
        if self._porcupine:
            return self._porcupine.frame_length
        return 512

    def process_frame(self, pcm: list[int]) -> bool:
        """
        Process a frame of audio.
        Returns True if the wake word was detected.
        """
        if not self._porcupine:
            return False

        try:
            # The Porcupine engine process() returns >= 0 if keyword detected
            keyword_index = self._porcupine.process(pcm)
            return keyword_index >= 0
        except Exception as e:
            logger.error(f"Error processing audio frame for wake word: {e}")
            return False

    def close(self) -> None:
        """Clean up Porcupine resources."""
        if self._porcupine:
            self._porcupine.delete()
            self._porcupine = None
            logger.debug("Wake word detector closed.")
