"""Versioned atomic pixel/result envelope. No image codec or board dependency."""
import json
import math
import re
import struct
import threading
import time
from collections import deque

MAX_META = 64 * 1024
MAX_PIXELS = 8 * 1024 * 1024
MAX_PACKET = 4 + MAX_META + MAX_PIXELS


def decimal(value):
    if not isinstance(value, str) or not re.fullmatch(r"0|[1-9][0-9]{0,19}", value) or int(value) >= 2**64:
        raise ValueError("Expected uint64 decimal string")
    return value


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("Integer outside bounds")
    return value


def pack(meta, pixels):
    header = json.dumps(meta, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
    if len(header) > MAX_META:
        raise ValueError("Metadata too large")
    return struct.pack("!I", len(header)) + header + pixels


def unpack(packet):
    if len(packet) < 5:
        raise ValueError("Truncated packet")
    length = struct.unpack_from("!I", packet)[0]
    if not 1 <= length <= MAX_META or 4 + length > len(packet):
        raise ValueError("Invalid metadata length")
    meta = json.loads(packet[4:4+length])
    if not isinstance(meta, dict) or type(meta.get("schema_version")) is not int or meta.get("schema_version") != 1:
        raise ValueError("Unsupported schema")
    if not isinstance(meta.get("stream_id"), str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", meta["stream_id"]):
        raise ValueError("Invalid stream id")
    decimal(meta.get("frame_id")); decimal(meta.get("timestamp_us"))
    if meta.get("timestamp_basis") != "ps_dma_done_monotonic":
        raise ValueError("Unsupported time basis")
    if meta.get("source") not in ("camera", "demo", "unverified"):
        raise ValueError("Invalid source")
    if meta.get("pixel_format") != "RGB565LE":
        raise ValueError("Unsupported pixel format; add an adapter")
    width = integer(meta.get("width"), 1, 4096)
    height = integer(meta.get("height"), 1, 4096)
    stride = integer(meta.get("stride_bytes"), width * 2, width * 2 + 4096)
    pixels = packet[4+length:]
    if len(pixels) != stride * height or len(pixels) > MAX_PIXELS:
        raise ValueError("Pixel length/stride mismatch")
    incoming = meta
    meta = {key: incoming[key] for key in ("schema_version", "stream_id", "frame_id", "timestamp_us",
            "timestamp_basis", "source", "pixel_format", "width", "height", "stride_bytes")}
    meta.update(faces=[], subtitles=[], models={"face": "not_connected", "voice": "not_connected"})
    # A CPU coordinator may deliver an already matched frame/result atomically.
    if any(key in incoming for key in ("faces", "subtitles", "models")):
        meta.update(validate_results(incoming, meta))
    return meta, pixels


def validate_results(result, meta):
    if not isinstance(result, dict) or type(result.get("schema_version")) is not int or result.get("schema_version") != 1:
        raise ValueError("Unsupported result schema")
    if result.get("stream_id") != meta["stream_id"] or result.get("frame_id") != meta["frame_id"]:
        raise LookupError("Result does not belong to latest frame")
    faces, subtitles = result.get("faces", []), result.get("subtitles", [])
    if not isinstance(faces, list) or len(faces) > 100 or not isinstance(subtitles, list) or len(subtitles) > 20:
        raise ValueError("Too many results")
    out_faces, out_subtitles = [], []
    for face in faces:
        box = face.get("box")
        name, confidence = face.get("name", ""), face.get("confidence")
        if not isinstance(box, list) or len(box) != 4 or any(type(n) not in (int, float) or not math.isfinite(n) for n in box):
            raise ValueError("Expected normalized x,y,width,height box")
        x, y, w, h = box
        if min(x, y) < 0 or min(w, h) <= 0 or x+w > 1.000001 or y+h > 1.000001:
            raise ValueError("Box outside frame")
        if not isinstance(name, str) or len(name) > 128 or type(confidence) not in (int, float) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("Invalid face label/confidence")
        out_faces.append(dict(box=box, name=name, confidence=confidence))
    for sub in subtitles:
        start, end = decimal(sub.get("start_us")), decimal(sub.get("end_us"))
        text = sub.get("text")
        if int(start) > int(end) or not isinstance(text, str) or len(text) > 2048:
            raise ValueError("Invalid subtitle interval/text")
        if int(start) <= int(meta["timestamp_us"]) <= int(end):
            out_subtitles.append(dict(start_us=start, end_us=end, text=text))
    models = result.get("models", {})
    if not isinstance(models, dict) or any(models.get(k, "not_connected") not in ("ready", "not_connected", "error") for k in ("face", "voice")):
        raise ValueError("Invalid model status")
    return dict(faces=out_faces, subtitles=out_subtitles,
                models={k: models.get(k, "not_connected") for k in ("face", "voice")})


class RawHub:
    def __init__(self, stale_seconds=2):
        self.lock = threading.Lock()
        self.meta = self.pixels = None
        self.arrival = 0
        self.revision = self.frames = 0
        self.arrivals = deque(maxlen=120)
        self.stale_seconds = stale_seconds
        self.retired = deque(maxlen=32)

    def publish(self, packet):
        meta, pixels = unpack(packet)
        with self.lock:
            if meta["stream_id"] in self.retired:
                raise LookupError("Retired stream")
            if self.meta:
                if meta["stream_id"] == self.meta["stream_id"]:
                    if int(meta["frame_id"]) <= int(self.meta["frame_id"]) or int(meta["timestamp_us"]) < int(self.meta["timestamp_us"]):
                        raise LookupError("Non-increasing frame/time")
                else:
                    self.retired.append(self.meta["stream_id"])
            self.meta, self.pixels = meta, pixels
            self.arrival = time.monotonic()
            self.arrivals.append(self.arrival)
            self.frames += 1
            self.revision += 1

    def results(self, result):
        with self.lock:
            if not self.meta or time.monotonic() - self.arrival > self.stale_seconds:
                raise LookupError("No live frame")
            updated = validate_results(result, self.meta)
            self.meta = dict(self.meta, **updated)
            self.revision += 1

    def snapshot(self, after):
        with self.lock:
            if not self.meta or time.monotonic() - self.arrival > self.stale_seconds:
                return 503, b""
            if after == self.revision:
                return 204, b""
            window = [t for t in self.arrivals if time.monotonic()-t < 3]
            elapsed = window[-1] - window[0] if len(window) > 1 else 0
            fps = (len(window)-1)/elapsed if elapsed > 0 else 0
            return 200, pack(dict(self.meta, revision=self.revision, receive_fps=round(fps, 1)), self.pixels)

    def status(self):
        with self.lock:
            window = [t for t in self.arrivals if time.monotonic() - t < 3]
            elapsed = window[-1] - window[0] if len(window) > 1 else 0
            fps = (len(window)-1)/elapsed if elapsed > 0 else 0
            return dict(live=bool(self.meta) and time.monotonic()-self.arrival <= self.stale_seconds,
                        frames_received=self.frames, receive_fps=round(fps, 1), revision=self.revision)
