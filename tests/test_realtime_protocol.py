import json
import unittest

from signal_processing_pipeline.realtime_protocol import ProtocolError, SensorStreamHub, decode_frame


def imu_frame(seq=1, session_id="imu-test"):
    return {
        "type": "imu",
        "session_id": session_id,
        "seq": seq,
        "timestamp_ms": 1757246400123 + seq,
        "quality": 0.94,
        "cadence_hz": 1.72,
        "step_length_m": 0.52,
        "step_time_cv": 0.084,
        "stride_symmetry": 0.91,
        "trunk_sway_deg": 3.4,
        "is_walking": True,
    }


class RealtimeProtocolTests(unittest.TestCase):
    def test_valid_frame_preserves_nulls(self):
        frame = imu_frame()
        frame["cadence_hz"] = None
        decoded = decode_frame(json.dumps(frame).encode(), "imu")
        self.assertIsNone(decoded["cadence_hz"])

    def test_missing_field_is_rejected(self):
        frame = imu_frame()
        del frame["step_time_cv"]
        with self.assertRaises(ProtocolError):
            decode_frame(json.dumps(frame).encode(), "imu")

    def test_quality_range_is_rejected(self):
        frame = imu_frame()
        frame["quality"] = 1.1
        with self.assertRaises(ProtocolError):
            decode_frame(json.dumps(frame).encode(), "imu")

    def test_zero_quality_requires_null_sensor_fields(self):
        frame = imu_frame()
        frame["quality"] = 0.0
        with self.assertRaises(ProtocolError):
            decode_frame(json.dumps(frame).encode(), "imu")

    def test_sequence_gap_and_session_change_are_tracked(self):
        hub = SensorStreamHub()
        hub.ingest(json.dumps(imu_frame(seq=1)).encode(), "imu")
        _, events = hub.ingest(json.dumps(imu_frame(seq=3)).encode(), "imu")
        self.assertEqual(hub.streams["imu"].dropped, 1)
        self.assertTrue(any("dropped 1" in event for event in events))
        hub.ingest(json.dumps(imu_frame(seq=1, session_id="imu-new")).encode(), "imu")
        self.assertEqual(hub.streams["imu"].session_id, "imu-new")
        self.assertEqual(hub.streams["imu"].dropped, 1)


if __name__ == "__main__":
    unittest.main()
