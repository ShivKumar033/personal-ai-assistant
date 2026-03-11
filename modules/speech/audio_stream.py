"""
JARVIS AI — Audio Stream Pipeline (Phase 5)

Orchestrates the entire voice interaction flow:
Mic → Wake Word → STT → Processor (Interpreter) → TTS
"""

from __future__ import annotations

import asyncio
from typing import Callable, Optional

from loguru import logger

from .wake_word_detector import WakeWordDetector
from .voice_listener import VoiceListener
from .tts_engine import TTSEngine


class AudioStreamPipeline:
    """Manages continuous background voice interaction."""

    def __init__(
        self,
        wake_word_detector: WakeWordDetector,
        voice_listener: VoiceListener,
        tts_engine: TTSEngine,
        process_command_callback: Callable[[str], asyncio.Future],
        on_wake_callback: Optional[Callable] = None,
    ) -> None:
        self.wake_detector = wake_word_detector
        self.listener = voice_listener
        self.tts = tts_engine
        
        self.process_command = process_command_callback
        self.on_wake = on_wake_callback
        
        self._is_running = False
        self._stream_task: Optional[asyncio.Task] = None

    def initialize(self) -> bool:
        """Initialize all audio components."""
        ww_ok = self.wake_detector.initialize()
        vl_ok = self.listener.initialize()
        tts_ok = self.tts.initialize()

        if not vl_ok:
            logger.error("Microphone (VoiceListener) failed to initialize. Voice pipeline will be disabled.")
            return False

        if not ww_ok:
            logger.warning("Wake Word Detector (Porcupine) failed (likely missing Access Key). Hands-free detection disabled.")

        if not tts_ok:
            logger.warning("TTS failed to initialize. JARVIS will be muted.")

        logger.info("Voice Pipeline components initialized.")
        return True

    async def start(self) -> None:
        """Start the background listening loop."""
        if self._is_running:
            return

        self._is_running = True
        self._stream_task = asyncio.create_task(self._audio_loop())
        logger.info("Background Voice Pipeline started.")

    async def stop(self) -> None:
        """Stop background listening."""
        self._is_running = False
        if self._stream_task:
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass
        
        self.wake_detector.close()
        logger.info("Background Voice Pipeline stopped.")

    async def trigger_once(self) -> None:
        """Manually trigger a single voice command capture."""
        logger.info("Manual voice trigger activated.")
        await self.tts.speak("Listening, sir.")
        await self._handle_voice_command()

    async def _handle_voice_command(self) -> None:
        """Handle capturing, transcribing, processing, and speaking a single command."""
        logger.info("Starting voice command capture...")
        command_text = await self.listener.listen_for_command()
        
        if command_text:
            try:
                # Emit command to JARVIS orchestrator
                response_text = await self.process_command(command_text)
                
                # Speak response
                if response_text:
                    await self.tts.speak(response_text)
                    
            except Exception as e:
                logger.error(f"Error processing transcribed command: {e}")
        else:
            await self.tts.speak("I didn't catch that.")

    async def _audio_loop(self) -> None:
        """
        The main interaction loop:
        1. Capture continuous stream from mic
        2. Feed 512 length PCM chunks to Porcupine
        3. If Wake Word triggers -> Stop continuous raw capture, Switch to SpeechRecognition for phrase capture
        4. Transcribe Phrase
        5. Pass phrase to JARVIS
        6. Return to step 1
        """
        import sounddevice as sd
        import numpy as np

        frame_length = self.wake_detector.frame_length
        sample_rate = self.wake_detector.sample_rate

        try:
            logger.info(f"Listening for wake word '{self.wake_detector.keyword}'...")
            
            # sounddevice non-blocking stream
            # We use a Queue to transport audio frames from the stream callback to the event loop
            q = asyncio.Queue()

            def _callback(indata, frames, time, status):
                if status:
                    logger.debug(f"Audio stream status: {status}")
                # Provide standard Python int lists as expected by PvPorcupine
                pcm = indata[:, 0].tolist() 
                try:
                    q.put_nowait(pcm)
                except asyncio.QueueFull:
                    pass

            with sd.InputStream(
                samplerate=sample_rate,
                blocksize=frame_length,
                dtype=np.int16,
                channels=1,
                callback=_callback,
            ):
                while self._is_running:
                    # Skip frame processing if wake detector isn't initialized
                    if not self.wake_detector.is_active:
                        await asyncio.sleep(1)
                        continue

                    pcm_chunk = await q.get()
                    
                    # 1. Process Wake Word
                    if self.wake_detector.process_frame(pcm_chunk):
                        logger.info("Wake word detected!")
                        
                        # 2. Trigger on_wake callback
                        if self.on_wake:
                            if asyncio.iscoroutinefunction(self.on_wake):
                                await self.on_wake()
                            else:
                                self.on_wake()
                                
                        # Play acknowledgement tone or TTS
                        await self.tts.speak("Yes, sir?")
                        
                        # 3. Capture & Transcribe command using _handle_voice_command
                        await self._handle_voice_command()
                        
                        # Flush the queue to prevent immediate re-triggering on stale audio
                        while not q.empty():
                            q.get_nowait()
                            
                        logger.info("Resuming wake word detection...")

        except asyncio.CancelledError:
            logger.debug("Audio loop cancelled.")
        except ImportError as e:
            logger.error(f"Audio library missing: {e}. 'pip install sounddevice numpy'")
        except Exception as e:
            logger.error(f"Voice Pipeline error: {e}")
            self._is_running = False
