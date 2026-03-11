"""
JARVIS AI — Text-to-Speech Engine (Phase 5)

Converts JARVIS text responses into natural-sounding speech
using Microsoft Edge neural TTS (edge-tts).
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import tempfile
import subprocess
from typing import Optional

from loguru import logger
import edge_tts


class TTSEngine:
    """Natural voice Text-to-Speech generator."""

    def __init__(
        self,
        voice: str = "en-GB-RyanNeural",
        rate: str = "+0%",
        volume: str = "+0%",
    ) -> None:
        self.voice = voice
        self.rate = rate
        self.volume = volume
        self._is_speaking = False

    def initialize(self) -> bool:
        """Verify TTS engine initialization and dependencies."""
        # Check if python playsound or ffplay or aplay is installed for audio playback
        import shutil
        players = ["paplay", "mpg123", "ffplay", "mpv", "cvlc", "pw-play", "play"]


        self.player = next((p for p in players if shutil.which(p)), None)
        
        if not self.player:
            logger.warning(
                "No audio player found installed (e.g. ffplay, aplay, mpv, afplay). "
                "TTS will generate audio but won't be able to play it."
            )
            return False
        
        logger.info(f"TTS Engine initialized using voice '{self.voice}' and player '{self.player}'.")
        return True

    @property
    def is_speaking(self) -> bool:
        """Returns True if the engine is currently speaking."""
        return self._is_speaking

    async def speak(self, text: str) -> bool:
        """Convert text to speech and play the audio asynchronously."""
        if not text:
            return False

        # Clean up Markdown/emojis from the text before speaking
        clean_text = self._clean_text_for_speech(text)
        if not clean_text:
            return False

        self._is_speaking = True
        logger.debug(f"Speaking: '{clean_text[:50]}...'")

        # Generate temp output path
        fd, temp_path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)

        try:
            # 1. Generate audio using Edge-TTS
            communicate = edge_tts.Communicate(
                text=clean_text,
                voice=self.voice,
                rate=self.rate,
                volume=self.volume,
            )
            
            await communicate.save(temp_path)
            
            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                logger.debug(f"TTS audio file generated: {temp_path} ({os.path.getsize(temp_path)} bytes)")
            else:
                logger.error("TTS generation failed: Empty or missing file.")
                return False

            # 2. Play audio file natively in a separate subprocess
            if self.player:
                player_params = self._get_player_params(self.player, temp_path)
                logger.debug(f"Executing audio player: {' '.join(player_params)}")
                
                proc = await asyncio.create_subprocess_exec(
                    *player_params,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    logger.warning(f"Audio player {self.player} failed with code {proc.returncode}")
                    if stderr:
                        logger.debug(f"Player error output: {stderr.decode().strip()}")
                return proc.returncode == 0
            
            return False

        except Exception as e:
            logger.error(f"TTS Engine failure: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return False

        finally:
            self._is_speaking = False
            # Clean up temp file
            if os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except Exception as cleanup_error:
                    logger.debug(f"Failed to cleanly sweep TTS temp file: {cleanup_error}")

    def _get_player_params(self, player: str, file_path: str) -> list[str]:
        """Return the correct CLI args for the detected audio player."""
        if player == "paplay":
            return ["paplay", file_path]
        elif player == "mpg123":
            return ["mpg123", "-q", file_path]
        elif player == "cvlc":
            return ["cvlc", "--play-and-exit", "--quiet", file_path]
        elif player == "pw-play":
            return ["pw-play", file_path]
        elif player == "ffplay":
            return ["ffplay", "-nodisp", "-autoexit", "-quiet", file_path]
        elif player == "mpv":
            return ["mpv", "--no-video", "--really-quiet", file_path]
        elif player == "play":
            return ["play", "-q", file_path]
        else:
            return [player, file_path]

    def _clean_text_for_speech(self, text: str) -> str:
        """Remove markdown artifacts and structure not suitable for reading aloud."""
        import re
        
        # Remove bold/italic markdown
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
        text = re.sub(r'\*(.*?)\*', r'\1', text)
        
        # Remove code blocks
        text = re.sub(r'```.*?```', ' I have provided a code block in the terminal.', text, flags=re.DOTALL)
        
        # Remove inline code marks
        text = re.sub(r'`(.*?)`', r'\1', text)
        
        # Remove links but keep text
        text = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', text)
        
        # Remove empty lines
        text = " ".join([line.strip() for line in text.splitlines() if line.strip()])
        
        return text
