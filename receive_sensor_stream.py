#!/usr/bin/env python3
"""Receive and validate the agreed local IMU/Polar H10 UDP streams."""

from __future__ import annotations

import argparse
import json
import select
import socket
import sys
import time
from pathlib import Path
from typing import Any, Dict

from signal_processing_pipeline.realtime_protocol import HR_PORT, IMU_PORT, MAX_DATAGRAM_BYTES, ProtocolError, SensorStreamHub


def _bind(port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 256 * 1024)
    sock.bind(("127.0.0.1", port))
    return sock


def _write_jsonl(handle: Any, frame: Dict[str, Any]) -> None:
    handle.write(json.dumps(frame, ensure_ascii=False, separators=(",", ":")) + "\n")
    handle.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description="Receive local IMU and HR UDP feature streams")
    parser.add_argument("--imu-port", type=int, default=IMU_PORT)
    parser.add_argument("--hr-port", type=int, default=HR_PORT)
    parser.add_argument("--timeout-sec", type=float, default=3.0, help="stale stream warning threshold")
    parser.add_argument("--jsonl", type=Path, help="optional append-only frame log")
    args = parser.parse_args()

    sockets = {
        _bind(args.imu_port): "imu",
        _bind(args.hr_port): "hr",
    }
    hub = SensorStreamHub()
    log_handle = args.jsonl.open("a", encoding="utf-8") if args.jsonl else None
    print(f"Listening on 127.0.0.1:{args.imu_port} (imu) and 127.0.0.1:{args.hr_port} (hr)")
    print("Press Ctrl+C to stop.")

    try:
        while True:
            ready, _, _ = select.select(list(sockets), [], [], 1.0)
            if not ready:
                for stream in hub.stale_streams(args.timeout_sec):
                    print(f"WARN {stream}: no frame for > {args.timeout_sec:.1f}s", flush=True)
                continue
            for sock in ready:
                payload, address = sock.recvfrom(MAX_DATAGRAM_BYTES + 1)
                stream = sockets[sock]
                try:
                    frame, events = hub.ingest(payload, stream)
                except ProtocolError as exc:
                    print(f"REJECT {stream} from {address}: {exc}", flush=True)
                    continue
                for event in events:
                    print(f"EVENT {event}", flush=True)
                if log_handle:
                    _write_jsonl(log_handle, frame)
                quality = frame["quality"]
                state = "not-worn/invalid-signal" if quality == 0 else "ok"
                print(
                    f"{stream.upper()} seq={frame['seq']} session={frame['session_id']} "
                    f"quality={quality:.2f} state={state}",
                    flush=True,
                )
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        for sock in sockets:
            sock.close()
        if log_handle:
            log_handle.close()
        print(json.dumps(hub.snapshot(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
