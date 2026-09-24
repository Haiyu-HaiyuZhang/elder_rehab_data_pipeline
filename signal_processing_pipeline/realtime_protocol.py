"""Validation and state tracking for the local sensor UDP protocol."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
import time
from typing import Any, Dict, List, Optional, Tuple


MAX_DATAGRAM_BYTES = 1200
IMU_PORT = 9101
HR_PORT = 9102

COMMON_FIELDS = {
    "type": str,
    "session_id": str,
    "seq": int,
    "timestamp_ms": int,
    "quality": (int, float),
}
IMU_FIELDS = {
    "cadence_hz": (int, float, type(None)),
    "step_length_m": (int, float, type(None)),
    "step_time_cv": (int, float, type(None)),
    "stride_symmetry": (int, float, type(None)),
    "trunk_sway_deg": (int, float, type(None)),
    "is_walking": (bool, type(None)),
}
HR_FIELDS = {
    "hr_bpm": (int, float, type(None)),
    "rr_interval_ms": (int, float, type(None)),
    "rmssd_ms": (int, float, type(None)),
}


class ProtocolError(ValueError):
    """Raised when a datagram does not satisfy the agreed protocol."""


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _require_number(frame: Dict[str, Any], name: str, minimum: float = 0.0, maximum: Optional[float] = None) -> None:
    value = frame[name]
    if value is None:
        return
    if not _is_number(value) or value < minimum or (maximum is not None and value > maximum):
        bound = f" in [{minimum}, {maximum}]" if maximum is not None else f" >= {minimum}"
        raise ProtocolError(f"{name} must be a finite number{bound} or null")


def decode_frame(payload: bytes, expected_type: str) -> Dict[str, Any]:
    """Decode and validate one UDP payload, returning a plain dictionary."""
    if len(payload) > MAX_DATAGRAM_BYTES:
        raise ProtocolError(f"datagram exceeds {MAX_DATAGRAM_BYTES} bytes")
    try:
        frame = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("payload must be one UTF-8 JSON object") from exc
    if not isinstance(frame, dict):
        raise ProtocolError("payload must be a JSON object")

    required = set(COMMON_FIELDS) | (set(IMU_FIELDS) if expected_type == "imu" else set(HR_FIELDS))
    missing = sorted(required - frame.keys())
    if missing:
        raise ProtocolError(f"missing fields: {', '.join(missing)}")
    if frame.get("type") != expected_type:
        raise ProtocolError(f"expected type {expected_type!r}")

    for name, expected in COMMON_FIELDS.items():
        value = frame[name]
        if not isinstance(value, expected) or (name in {"seq", "timestamp_ms"} and isinstance(value, bool)):
            raise ProtocolError(f"{name} has invalid type")
    if not frame["session_id"]:
        raise ProtocolError("session_id must not be empty")
    if frame["seq"] < 1:
        raise ProtocolError("seq must start at 1")
    if frame["timestamp_ms"] < 0:
        raise ProtocolError("timestamp_ms must be non-negative")
    _require_number(frame, "quality", 0.0, 1.0)

    fields = IMU_FIELDS if expected_type == "imu" else HR_FIELDS
    for name, expected in fields.items():
        if not isinstance(frame[name], expected):
            raise ProtocolError(f"{name} has invalid type")
    if expected_type == "imu":
        _require_number(frame, "cadence_hz")
        _require_number(frame, "step_length_m")
        _require_number(frame, "step_time_cv")
        _require_number(frame, "stride_symmetry", 0.0, 1.0)
        _require_number(frame, "trunk_sway_deg")
    else:
        _require_number(frame, "hr_bpm")
        _require_number(frame, "rr_interval_ms")
        _require_number(frame, "rmssd_ms")
    if frame["quality"] == 0.0:
        if any(frame[name] is not None for name in fields):
            raise ProtocolError("quality=0 requires all sensor fields to be null")
    return frame


@dataclass
class StreamState:
    """Session and delivery statistics for one stream."""

    stream_type: str
    session_id: Optional[str] = None
    last_seq: Optional[int] = None
    last_timestamp_ms: Optional[int] = None
    received: int = 0
    dropped: int = 0
    out_of_order: int = 0
    invalid: int = 0
    last_received_monotonic: Optional[float] = None
    latest_frame: Optional[Dict[str, Any]] = None
    events: List[str] = field(default_factory=list)

    def accept(self, frame: Dict[str, Any]) -> None:
        session_id = frame["session_id"]
        seq = frame["seq"]
        if self.session_id != session_id:
            if self.session_id is not None:
                self.events.append(f"{self.stream_type}: session changed {self.session_id} -> {session_id}")
            self.session_id = session_id
            self.last_seq = None
            self.last_timestamp_ms = None

        if self.last_seq is not None:
            if seq > self.last_seq + 1:
                self.dropped += seq - self.last_seq - 1
                self.events.append(f"{self.stream_type}: dropped {seq - self.last_seq - 1} frame(s)")
            elif seq <= self.last_seq:
                self.out_of_order += 1
                self.events.append(f"{self.stream_type}: out-of-order seq {seq}")
        if self.last_timestamp_ms is not None and frame["timestamp_ms"] < self.last_timestamp_ms:
            self.events.append(f"{self.stream_type}: timestamp moved backwards")

        self.last_seq = max(self.last_seq or seq, seq)
        self.last_timestamp_ms = max(self.last_timestamp_ms or frame["timestamp_ms"], frame["timestamp_ms"])
        self.received += 1
        self.last_received_monotonic = time.monotonic()
        self.latest_frame = frame

    def snapshot(self) -> Dict[str, Any]:
        return {
            "stream": self.stream_type,
            "session_id": self.session_id,
            "received": self.received,
            "dropped": self.dropped,
            "out_of_order": self.out_of_order,
            "invalid": self.invalid,
            "latest_frame": self.latest_frame,
        }


class SensorStreamHub:
    """Validate frames and expose the latest frame from each sensor stream."""

    def __init__(self) -> None:
        self.streams = {"imu": StreamState("imu"), "hr": StreamState("hr")}

    def ingest(self, payload: bytes, expected_type: str) -> Tuple[Dict[str, Any], List[str]]:
        state = self.streams[expected_type]
        try:
            frame = decode_frame(payload, expected_type)
        except ProtocolError:
            state.invalid += 1
            raise
        before = len(state.events)
        state.accept(frame)
        return frame, state.events[before:]

    def snapshot(self) -> Dict[str, Any]:
        return {name: state.snapshot() for name, state in self.streams.items()}

    def stale_streams(self, timeout_sec: float) -> List[str]:
        now = time.monotonic()
        return [
            name
            for name, state in self.streams.items()
            if state.last_received_monotonic is None
            or now - state.last_received_monotonic > timeout_sec
        ]
