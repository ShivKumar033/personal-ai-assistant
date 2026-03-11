"""
JARVIS AI — Tests for Phase 5: Voice Interface & Speech Pipeline
"""

import asyncio
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from modules.speech.wake_word_detector import WakeWordDetector
from modules.speech.voice_listener import VoiceListener
from modules.speech.tts_engine import TTSEngine
from modules.speech.audio_stream import AudioStreamPipeline


# ── Fixtures ──────────────────────────────────────────────

@pytest.fixture
def mock_porcupine():
    with patch("pvporcupine.create") as mock_create:
        mock_instance = MagicMock()
        mock_instance.sample_rate = 16000
        mock_instance.frame_length = 512
        mock_instance.process.return_value = 0 # Detected
        mock_create.return_value = mock_instance
        yield mock_create


@pytest.fixture
def mock_speech_recognition():
    with patch("speech_recognition.Recognizer") as mock_sr:
        mock_inst = MagicMock()
        mock_inst.energy_threshold = 1000
        mock_inst.recognize_google.return_value = "hello jarvis"
        mock_sr.return_value = mock_inst
        yield mock_sr


@pytest.fixture
def mock_edge_tts():
    with patch("edge_tts.Communicate") as mock_comm:
        mock_inst = AsyncMock()
        mock_inst.save = AsyncMock()
        mock_comm.return_value = mock_inst
        yield mock_comm


# ═════════════════════════════════════════════════════════════
#  Wake Word Detector Tests
# ═════════════════════════════════════════════════════════════

class TestWakeWordDetector:

    def test_init_no_key(self):
        detector = WakeWordDetector("")
        assert detector.initialize() is False

    @patch("pvporcupine.create")
    def test_init_with_key(self, mock_create):
        detector = WakeWordDetector("fake_key")
        assert detector.initialize() is True
        mock_create.assert_called_once_with(
            access_key="fake_key", 
            keywords=["jarvis"], 
            sensitivities=[0.5]
        )

    def test_process_frame(self, mock_porcupine):
        detector = WakeWordDetector("fake_key")
        detector.initialize()
        
        pcm = [0] * 512
        assert detector.process_frame(pcm) is True
        
        # Test close
        detector.close()
        assert detector._porcupine is None


# ═════════════════════════════════════════════════════════════
#  Voice Listener Tests
# ═════════════════════════════════════════════════════════════

class TestVoiceListener:

    @patch("speech_recognition.Microphone")
    def test_initialize(self, mock_mic, mock_speech_recognition):
        listener = VoiceListener(engine="google")
        assert listener.initialize() is True
        
    @pytest.mark.asyncio
    @patch("speech_recognition.Microphone")
    async def test_listen_and_transcribe(self, mock_mic, mock_speech_recognition):
        listener = VoiceListener(engine="google")
        listener.initialize()
        
        # Mock the blocking listen
        listener._listen_blocking = MagicMock(return_value="audio_data")
        listener._transcribe_blocking = MagicMock(return_value="command")
        
        text = await listener.listen_for_command()
        
        assert text == "command"
        listener._listen_blocking.assert_called_once()
        listener._transcribe_blocking.assert_called_once_with("audio_data")

    def test_transcribe_blocking(self, mock_speech_recognition):
        listener = VoiceListener(engine="google")
        listener.initialize()
        
        # Get the mocked recognizer instance
        recognizer = listener._recognizer
        
        text = listener._transcribe_blocking("audio")
        assert text == "hello jarvis"
        recognizer.recognize_google.assert_called_once()


# ═════════════════════════════════════════════════════════════
#  TTS Engine Tests
# ═════════════════════════════════════════════════════════════

class TestTTSEngine:

    @patch("shutil.which")
    def test_initialize(self, mock_which):
        # Pretend ffplay exists
        mock_which.return_value = "/usr/bin/ffplay"
        
        tts = TTSEngine()
        assert tts.initialize() is True
        assert tts.player == "ffplay"
        
    def test_clean_text(self):
        tts = TTSEngine()
        assert tts._clean_text_for_speech("**Bold**") == "Bold"
        assert tts._clean_text_for_speech("`code`") == "code"
        assert tts._clean_text_for_speech("[Link](http)") == "Link"

    @pytest.mark.asyncio
    @patch("asyncio.create_subprocess_exec")
    @patch("shutil.which")
    async def test_speak(self, mock_which, mock_exec, mock_edge_tts):
        mock_which.return_value = "/usr/bin/ffplay"
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.wait = AsyncMock()
        mock_exec.return_value = mock_proc
        
        tts = TTSEngine()
        tts.initialize()
        
        result = await tts.speak("hello")
        
        assert result is True
        mock_exec.assert_called_once()


# ═════════════════════════════════════════════════════════════
#  Pipeline Tests
# ═════════════════════════════════════════════════════════════

class TestAudioPipeline:

    def test_pipeline_init(self):
        wake = MagicMock()
        wake.initialize.return_value = True
        
        listener = MagicMock()
        listener.initialize.return_value = True
        
        tts = MagicMock()
        tts.initialize.return_value = True
        
        pipeline = AudioStreamPipeline(wake, listener, tts, MagicMock())
        assert pipeline.initialize() is True
        
    @pytest.mark.asyncio
    async def test_pipeline_start_stop(self):
        pipeline = AudioStreamPipeline(MagicMock(), MagicMock(), MagicMock(), MagicMock())
        
        # Mock the internal loop so it doesn't block
        pipeline._audio_loop = AsyncMock()
        
        await pipeline.start()
        assert pipeline._is_running is True
        assert pipeline._stream_task is not None
        
        await pipeline.stop()
        assert pipeline._is_running is False
