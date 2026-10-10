"""Send directional swipes to any Android device (BlueStacks, emulator, or phone).

Touches go through scrcpy-server over adb: one persistent control socket, so no
per-swipe process launch. The server is pinned to one scrcpy release because
its wire protocol changes between versions.
"""

import argparse
import hashlib
import os
import re
import shutil
import socket
import struct
import subprocess
import time
import urllib.request
from pathlib import Path

SCRCPY_VERSION = "5.0.1"
SERVER_URL = (
    "https://github.com/Genymobile/scrcpy/releases/download/"
    f"v{SCRCPY_VERSION}/scrcpy-server-v{SCRCPY_VERSION}"
)
SERVER_SHA256 = "764eb6f79811d5211fe9df341120882ba9994c7a61b897d7bf3fb662e53bc536"
SERVER_LOCAL = (
    Path(__file__).resolve().parent / ".android-tools" / f"scrcpy-server-v{SCRCPY_VERSION}"
)
SERVER_REMOTE = "/data/local/tmp/body-controller-scrcpy-server.jar"
SCID = 0x0B0D7C01  # fixed session id so we never collide with a normal scrcpy session
PORT = 27183

TYPE_INJECT_TOUCH_EVENT = 2
ACTION_DOWN, ACTION_UP, ACTION_MOVE = 0, 1, 2
POINTER_ID = -2  # scrcpy's generic finger

DIRECTIONS = {"LEFT": (-1, 0), "RIGHT": (1, 0), "UP": (0, -1), "DOWN": (0, 1)}
SWIPE_FRACTION = 0.2  # swipe length as a fraction of screen width/height
SWIPE_STEPS = 4
STEP_DELAY = 0.008  # seconds between touch points (~32 ms per swipe)


def find_adb() -> str:
    exe = "adb.exe" if os.name == "nt" else "adb"
    for root in (
        os.environ.get("ANDROID_HOME"),
        os.environ.get("ANDROID_SDK_ROOT"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk"),
    ):
        if root and (Path(root) / "platform-tools" / exe).exists():
            return str(Path(root) / "platform-tools" / exe)
    found = shutil.which("adb")
    if found:
        return found
    raise RuntimeError("adb not found. Install Android platform-tools or set ANDROID_HOME.")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ensure_server() -> Path:
    """Download the pinned scrcpy-server once and verify its checksum."""
    if SERVER_LOCAL.exists() and _sha256(SERVER_LOCAL) == SERVER_SHA256:
        return SERVER_LOCAL
    SERVER_LOCAL.parent.mkdir(exist_ok=True)
    partial = SERVER_LOCAL.with_suffix(".part")
    print(f"Downloading scrcpy-server v{SCRCPY_VERSION}...")
    urllib.request.urlretrieve(SERVER_URL, partial)
    if _sha256(partial) != SERVER_SHA256:
        partial.unlink()
        raise RuntimeError("Downloaded scrcpy-server failed its checksum")
    partial.replace(SERVER_LOCAL)
    return SERVER_LOCAL


def touch_message(action: int, x: int, y: int, width: int, height: int) -> bytes:
    """scrcpy v5 INJECT_TOUCH_EVENT: 32 bytes, big-endian."""
    pressure = 0 if action == ACTION_UP else 0xFFFF
    return struct.pack(
        ">BBqiiHHHii", TYPE_INJECT_TOUCH_EVENT, action, POINTER_ID,
        x, y, width, height, pressure, 0, 0,
    )


def swipe_points(direction: str, width: int, height: int) -> list[tuple[int, int]]:
    """Touch points from screen center along ``direction``, first to last."""
    dx, dy = DIRECTIONS[direction]
    x0, y0 = width / 2, height / 2
    return [
        (round(x0 + dx * width * SWIPE_FRACTION * i / SWIPE_STEPS),
         round(y0 + dy * height * SWIPE_FRACTION * i / SWIPE_STEPS))
        for i in range(SWIPE_STEPS + 1)
    ]


class AndroidSwipeClient:
    """One scrcpy-server session; a failed swipe is never replayed."""

    def __init__(self, serial="127.0.0.1:5555", port=PORT):
        self.serial = serial
        self.port = port
        self.adb_path = find_adb()
        self.server = None
        self.sock = None
        self.size = None

    def adb(self, *args, serial=True, timeout=15) -> str:
        cmd = [self.adb_path, *(["-s", self.serial] if serial else []), *args]
        result = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            raise RuntimeError(f"adb {' '.join(args)} failed: {result.stderr.strip() or result.stdout.strip()}")
        return result.stdout

    def screen_size(self) -> tuple[int, int]:
        """Current display size, honoring rotation (e.g. a portrait game on a landscape instance)."""
        out = self.adb("shell", "dumpsys window displays")
        match = re.search(r"\bcur=(\d+)x(\d+)", out)
        if not match:
            match = re.search(r"(\d+)x(\d+)", self.adb("shell", "wm size"))
        if not match:
            raise RuntimeError("Could not read the Android screen size")
        return int(match.group(1)), int(match.group(2))

    def start(self):
        if ":" in self.serial:
            self.adb("connect", self.serial, serial=False)
        self.adb("push", str(ensure_server()), SERVER_REMOTE, timeout=60)
        self.size = self.screen_size()
        socket_name = f"localabstract:scrcpy_{SCID:08x}"
        self.adb("forward", f"tcp:{self.port}", socket_name)
        server_cmd = (
            f"CLASSPATH={SERVER_REMOTE} app_process / com.genymobile.scrcpy.Server "
            f"{SCRCPY_VERSION} scid={SCID:08x} log_level=warn tunnel_forward=true "
            "video=false audio=false control=true send_device_meta=false "
            "send_dummy_byte=true cleanup=false clipboard_autosync=false power_on=false"
        )
        self.server = subprocess.Popen(
            [self.adb_path, "-s", self.serial, "shell", server_cmd],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if self.server.poll() is not None:
                raise RuntimeError("scrcpy-server exited during startup")
            sock = socket.create_connection(("127.0.0.1", self.port), timeout=2)
            try:
                if sock.recv(1) == b"\x00":  # server's ready byte; empty means not listening yet
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    sock.settimeout(None)
                    self.sock = sock
                    return
            except OSError:
                pass
            sock.close()
            time.sleep(0.1)
        raise RuntimeError("Timed out waiting for scrcpy-server")

    def native_swipe(self, direction: str) -> float:
        """Send one swipe; returns milliseconds spent sending it."""
        direction = direction.upper()
        if direction not in DIRECTIONS:
            raise ValueError("Expected LEFT, RIGHT, UP, or DOWN")
        if self.sock is None:
            raise RuntimeError("Start the Android client before sending swipes")
        width, height = self.size
        points = swipe_points(direction, width, height)
        started = time.perf_counter()
        self.sock.sendall(touch_message(ACTION_DOWN, *points[0], width, height))
        for x, y in points[1:]:
            time.sleep(STEP_DELAY)
            self.sock.sendall(touch_message(ACTION_MOVE, x, y, width, height))
        self.sock.sendall(touch_message(ACTION_UP, *points[-1], width, height))
        return (time.perf_counter() - started) * 1000

    def close(self):
        if self.sock is not None:
            self.sock.close()
            self.sock = None
        if self.server is not None:
            self.server.terminate()
            self.server = None
        try:
            self.adb("forward", "--remove", f"tcp:{self.port}")
        except (RuntimeError, subprocess.TimeoutExpired):
            pass


def main():
    parser = argparse.ArgumentParser(description="Send test swipes to Android")
    parser.add_argument("directions", nargs="+", choices=sorted(DIRECTIONS))
    parser.add_argument("--serial", default="127.0.0.1:5555")
    args = parser.parse_args()
    client = AndroidSwipeClient(args.serial)
    try:
        client.start()
        print(f"Connected to {args.serial}, screen {client.size[0]}x{client.size[1]}")
        for direction in args.directions:
            print(f"{direction}: sent in {client.native_swipe(direction):.0f} ms")
            time.sleep(0.5)
    finally:
        client.close()


if __name__ == "__main__":
    main()
