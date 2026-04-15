#!/usr/bin/env python3
"""
Rogers dispatch transcriber: Partner feed → PCM → silence segmentation → faster-whisper → notes.

Requires ffmpeg on PATH (decodes MP3/AAC from stream).

Environment (secrets not committed):
  BROADCASTIFY_PARTNER_URL     Full URL, e.g. https://partner.broadcastify.com/16533?xan=YOUR_TOKEN
  Or split:
  BROADCASTIFY_PARTNER_BASE    Default https://partner.broadcastify.com
  BROADCASTIFY_FEED_ID         Default 16533
  BROADCASTIFY_XAN             Session token (same as ?xan= in Partner links)

  When playback stops with 401/403 or empty stream, refresh xan in Broadcastify Partner portal
  and update .env / environment, then restart this process.

Optional:
  WHISPER_MODEL           tiny|base|small|medium (default small)
  ROGERS_TRANSCRIBER_OUTPUT_DIR   Default ./rogers_transcriber_data
  ROGERS_TRANSCRIBER_SAVE_WAV     1 to save each segment WAV
  SILENCE_END_MS                  Default 1200
  MIN_SEGMENT_MS                  Default 400
  MAX_SEGMENT_MS                  Default 120000
  SPEECH_RMS_THRESHOLD            Default 800 (int16 PCM; tune per feed)
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import struct
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Optional, Tuple

import numpy as np
import requests

LOG = logging.getLogger("rogers_dispatch_transcriber")

DEFAULT_PARTNER_BASE = "https://partner.broadcastify.com"
DEFAULT_FEED_ID = "16533"
SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2  # s16le mono
FRAME_SAMPLES = 480  # 30 ms @ 16 kHz
FRAME_BYTES = FRAME_SAMPLES * BYTES_PER_SAMPLE


def build_partner_url() -> str:
    full = os.getenv("BROADCASTIFY_PARTNER_URL", "").strip()
    if full:
        return full
    base = os.getenv("BROADCASTIFY_PARTNER_BASE", DEFAULT_PARTNER_BASE).rstrip("/")
    feed = os.getenv("BROADCASTIFY_FEED_ID", DEFAULT_FEED_ID).strip()
    xan = os.getenv("BROADCASTIFY_XAN", "").strip()
    if not xan:
        raise SystemExit(
            "Set BROADCASTIFY_PARTNER_URL or BROADCASTIFY_XAN (and optionally "
            "BROADCASTIFY_PARTNER_BASE / BROADCASTIFY_FEED_ID)."
        )
    return f"{base}/{feed}?xan={xan}"


def _rms_int16(chunk: np.ndarray) -> float:
    if chunk.size == 0:
        return 0.0
    f = chunk.astype(np.float32)
    return float(np.sqrt(np.mean(f * f)))


@dataclass
class TranscriberConfig:
    partner_url: str
    output_dir: Path
    sqlite_path: Path
    jsonl_path: Path
    feed_id: str
    silence_end_ms: float
    min_segment_ms: float
    max_segment_ms: float
    speech_rms_threshold: float
    save_wav: bool
    whisper_model: str


def load_config() -> TranscriberConfig:
    url = build_partner_url()
    out = Path(os.getenv("ROGERS_TRANSCRIBER_OUTPUT_DIR", "rogers_transcriber_data"))
    out.mkdir(parents=True, exist_ok=True)
    sqlite_path = Path(os.getenv("ROGERS_TRANSCRIBER_SQLITE", str(out / "notes.sqlite")))
    jsonl_path = Path(os.getenv("ROGERS_TRANSCRIBER_JSONL", str(out / "notes.jsonl")))
    feed_id = os.getenv("BROADCASTIFY_FEED_ID", DEFAULT_FEED_ID).strip()
    return TranscriberConfig(
        partner_url=url,
        output_dir=out,
        sqlite_path=sqlite_path,
        jsonl_path=jsonl_path,
        feed_id=feed_id,
        silence_end_ms=float(os.getenv("SILENCE_END_MS", "1200")),
        min_segment_ms=float(os.getenv("MIN_SEGMENT_MS", "400")),
        max_segment_ms=float(os.getenv("MAX_SEGMENT_MS", "120000")),
        speech_rms_threshold=float(os.getenv("SPEECH_RMS_THRESHOLD", "800")),
        save_wav=os.getenv("ROGERS_TRANSCRIBER_SAVE_WAV", "").strip() in ("1", "true", "yes"),
        whisper_model=os.getenv("WHISPER_MODEL", "small").strip(),
    )


def init_sqlite(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS segment_notes (
                id TEXT PRIMARY KEY,
                feed_id TEXT NOT NULL,
                t_start TEXT NOT NULL,
                t_end TEXT NOT NULL,
                transcript TEXT NOT NULL,
                raw_wav_path TEXT,
                pulsepoint_incident_id INTEGER,
                match_confidence REAL,
                match_method TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        con.commit()
    finally:
        con.close()


def placeholder_match_incident(
    transcript: str,
    t_start: datetime,
    t_end: datetime,
) -> Optional[Tuple[int, float, str]]:
    """
    Future: correlate segment time/text with PulsePoint (see active_alert_listener AGENCY_ID).
    Returns (incident_id, confidence, method) or None.
    """
    _ = (transcript, t_start, t_end)
    return None


def store_note(
    cfg: TranscriberConfig,
    note_id: str,
    t_start: datetime,
    t_end: datetime,
    transcript: str,
    raw_wav_path: Optional[str],
    match: Optional[Tuple[int, float, str]],
) -> None:
    pid, conf, method = (None, None, None)
    if match:
        pid, conf, method = match[0], match[1], match[2]

    row = {
        "id": note_id,
        "feed_id": cfg.feed_id,
        "t_start": t_start.isoformat(),
        "t_end": t_end.isoformat(),
        "transcript": transcript,
        "raw_wav_path": raw_wav_path,
        "pulsepoint_incident_id": pid,
        "match_confidence": conf,
        "match_method": method,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    with open(cfg.jsonl_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

    con = sqlite3.connect(cfg.sqlite_path)
    try:
        con.execute(
            """
            INSERT INTO segment_notes (
                id, feed_id, t_start, t_end, transcript, raw_wav_path,
                pulsepoint_incident_id, match_confidence, match_method, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                note_id,
                cfg.feed_id,
                row["t_start"],
                row["t_end"],
                transcript,
                raw_wav_path,
                pid,
                conf,
                method,
                row["created_at"],
            ),
        )
        con.commit()
    finally:
        con.close()

    LOG.info("Note %s: %s", note_id, transcript[:120] + ("…" if len(transcript) > 120 else ""))


class PcmStream:
    """
    HTTP stream → ffmpeg → int16 mono PCM @ 16 kHz (generator of numpy chunks).
    """

    def __init__(self, url: str):
        self.url = url
        self._proc: Optional[subprocess.Popen] = None
        self._http_thread: Optional[threading.Thread] = None
        self._error: Optional[BaseException] = None

    def _http_writer(self, resp: requests.Response, proc: subprocess.Popen) -> None:
        try:
            assert proc.stdin is not None
            for chunk in resp.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                proc.stdin.write(chunk)
            proc.stdin.close()
        except Exception as e:
            self._error = e
            try:
                if proc.stdin:
                    proc.stdin.close()
            except Exception:
                pass

    def iter_pcm_frames(self) -> Generator[np.ndarray, None, None]:
        while True:
            self._error = None
            LOG.info("Connecting stream: %s", self.url.split("xan=")[0] + "xan=<redacted>")
            r = None
            try:
                r = requests.get(
                    self.url,
                    stream=True,
                    timeout=30,
                    headers={"User-Agent": "rogers-dispatch-transcriber/1.0"},
                )
                r.raise_for_status()
            except requests.RequestException as e:
                LOG.warning("HTTP failed: %s; retry in 5s", e)
                if r is not None:
                    try:
                        r.close()
                    except Exception:
                        pass
                time.sleep(5)
                continue

            cmd = [
                "ffmpeg",
                "-loglevel",
                "error",
                "-i",
                "pipe:0",
                "-f",
                "s16le",
                "-acodec",
                "pcm_s16le",
                "-ac",
                "1",
                "-ar",
                str(SAMPLE_RATE),
                "pipe:1",
            ]
            self._proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            assert self._proc.stdin and self._proc.stdout

            self._http_thread = threading.Thread(
                target=self._http_writer, args=(r, self._proc), daemon=True
            )
            self._http_thread.start()

            def _drain_stderr() -> None:
                assert self._proc and self._proc.stderr
                try:
                    for line in iter(self._proc.stderr.readline, b""):
                        if line:
                            LOG.debug("ffmpeg: %s", line.decode(errors="replace").strip())
                except Exception:
                    pass

            threading.Thread(target=_drain_stderr, daemon=True).start()

            buf = b""
            try:
                while True:
                    piece = self._proc.stdout.read(FRAME_BYTES * 4)
                    if not piece:
                        break
                    buf += piece
                    while len(buf) >= FRAME_BYTES:
                        frame = buf[:FRAME_BYTES]
                        buf = buf[FRAME_BYTES:]
                        samples = np.frombuffer(frame, dtype=np.int16).copy()
                        yield samples
            finally:
                if r is not None:
                    try:
                        r.close()
                    except Exception:
                        pass
                if self._proc:
                    self._proc.terminate()
                    try:
                        self._proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self._proc.kill()
                    self._proc = None

            if self._error:
                LOG.warning("HTTP writer error: %s", self._error)

            LOG.warning("Stream ended; reconnecting in 3s…")
            time.sleep(3)


@dataclass
class SegmentPayload:
    audio: np.ndarray
    t_start: datetime
    t_end: datetime


class Segmenter:
    """RMS gate + hangover; yields complete segment int16 arrays with wall-clock bounds."""

    def __init__(self, cfg: TranscriberConfig):
        self.cfg = cfg
        frame_ms = (FRAME_SAMPLES / SAMPLE_RATE) * 1000.0
        self._silence_frames = max(1, int(round(cfg.silence_end_ms / frame_ms)))
        self._min_samples = int(cfg.min_segment_ms / 1000 * SAMPLE_RATE)
        self._max_samples = int(cfg.max_segment_ms / 1000 * SAMPLE_RATE)

    def segments(
        self, frame_iter: Generator[np.ndarray, None, None]
    ) -> Generator[SegmentPayload, None, None]:
        buf: list[np.ndarray] = []
        speech = False
        silence_run = 0
        seg_wall_start: Optional[datetime] = None

        for frame in frame_iter:
            rms = _rms_int16(frame)
            if not speech:
                if rms >= self.cfg.speech_rms_threshold:
                    speech = True
                    buf = [frame]
                    silence_run = 0
                    seg_wall_start = datetime.now(timezone.utc)
                continue

            buf.append(frame)
            if rms < self.cfg.speech_rms_threshold:
                silence_run += 1
            else:
                silence_run = 0

            total = sum(len(x) for x in buf)
            if total >= self._max_samples:
                t_end = datetime.now(timezone.utc)
                audio = np.concatenate(buf)
                if seg_wall_start is None:
                    seg_wall_start = t_end
                yield SegmentPayload(audio=audio, t_start=seg_wall_start, t_end=t_end)
                speech = False
                buf = []
                silence_run = 0
                seg_wall_start = None
                continue

            if silence_run >= self._silence_frames:
                # Drop trailing silence frames from audio (hangover)
                if silence_run < len(buf):
                    kept = buf[:-silence_run]
                else:
                    kept = buf
                seg = np.concatenate(kept) if kept else np.array([], dtype=np.int16)
                t_end = datetime.now(timezone.utc)
                if len(seg) >= self._min_samples and seg_wall_start is not None:
                    yield SegmentPayload(audio=seg, t_start=seg_wall_start, t_end=t_end)
                speech = False
                buf = []
                silence_run = 0
                seg_wall_start = None


def transcribe_segment(model: Any, audio_i16: np.ndarray) -> str:
    audio_f = (audio_i16.astype(np.float32) / 32768.0).clip(-1.0, 1.0)
    segments_gen, _ = model.transcribe(
        audio_f,
        language="en",
        beam_size=5,
        vad_filter=True,
    )
    parts = [s.text.strip() for s in segments_gen]
    return " ".join(parts).strip()


def run_loop(cfg: TranscriberConfig) -> None:
    from faster_whisper import WhisperModel

    init_sqlite(cfg.sqlite_path)
    pcm = PcmStream(cfg.partner_url)
    seg = Segmenter(cfg)

    LOG.info(
        "Segmenter: silence_end=%sms min=%sms max=%sms rms>=%s",
        cfg.silence_end_ms,
        cfg.min_segment_ms,
        cfg.max_segment_ms,
        cfg.speech_rms_threshold,
    )
    LOG.info("Loading Whisper model %r (one-time)…", cfg.whisper_model)
    whisper = WhisperModel(cfg.whisper_model, device="cpu", compute_type="int8")

    for payload in seg.segments(pcm.iter_pcm_frames()):
        audio = payload.audio
        if audio.size < int(SAMPLE_RATE * 0.05):
            continue

        note_id = str(uuid.uuid4())
        t_start, t_end = payload.t_start, payload.t_end

        wav_path: Optional[str] = None
        if cfg.save_wav:
            wav_path = str(cfg.output_dir / f"{note_id}.wav")
            _write_wav(wav_path, audio)

        try:
            text = transcribe_segment(whisper, audio)
        except Exception as e:
            LOG.exception("Transcription failed: %s", e)
            text = f"[transcription error: {e}]"

        match = placeholder_match_incident(text, t_start, t_end)
        store_note(cfg, note_id, t_start, t_end, text, wav_path, match)


def _write_wav(path: str, audio_i16: np.ndarray) -> None:
    """Minimal WAV (PCM s16le mono)."""
    n = len(audio_i16)
    with open(path, "wb") as f:
        f.write(b"RIFF")
        f.write(struct.pack("<I", 36 + n * 2))
        f.write(b"WAVEfmt ")
        f.write(
            struct.pack(
                "<IHHIIHH",
                16,
                1,
                1,
                SAMPLE_RATE,
                SAMPLE_RATE * 2,
                2,
                16,
            )
        )
        f.write(b"data")
        f.write(struct.pack("<I", n * 2))
        f.write(audio_i16.astype("<i2").tobytes())


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    cfg = load_config()
    LOG.info("Output: %s", cfg.output_dir)
    LOG.info("SQLite: %s", cfg.sqlite_path)
    LOG.info("Whisper model: %s", cfg.whisper_model)
    try:
        run_loop(cfg)
    except KeyboardInterrupt:
        LOG.info("Stopped.")


if __name__ == "__main__":
    main()
