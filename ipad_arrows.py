"""Focused Windows keyboard window for the running iPad swipe helper."""

import argparse
import queue
import threading
import tkinter as tk

from devicekit_swipe import DeviceKitSwipeClient, FastDeviceKitSwipeClient
from ios_swipe import WdaSwipeClient


class ArrowController:
    def __init__(
        self, root, url, dry_run=False, client_factory=FastDeviceKitSwipeClient
    ):
        self.root = root
        self.url = url
        self.dry_run = dry_run
        self.client_factory = client_factory
        self.results = queue.Queue()
        self.commands = queue.Queue(maxsize=1)
        self.stopped = threading.Event()
        self.held = set()
        self.ready = False
        self.busy = False
        root.title("iPad arrow controller")
        root.geometry("540x340")
        root.configure(bg="#142030")
        self.status = tk.StringVar(value="Connecting to iPad…")
        for text, size in [
            ("Arrow keys → iPad swipes", 22),
            ("↑ Jump    ↓ Roll    ← Left    → Right", 16),
            ("Keep this window selected. Esc stops the bridge.", 11),
            ("One swipe per press. Inputs while busy are skipped.", 11),
        ]:
            tk.Label(
                root,
                text=text,
                font=("Segoe UI", size),
                bg="#142030",
                fg="white",
                pady=9,
            ).pack()
        tk.Label(
            root,
            text="One iPad gesture per press.",
            font=("Segoe UI", 10),
            bg="#142030",
            fg="white",
        ).pack()
        tk.Label(
            root,
            textvariable=self.status,
            font=("Segoe UI", 12),
            bg="#142030",
            fg="#72e2ba",
            wraplength=510,
        ).pack(pady=12)
        root.bind("<KeyPress>", self.key_down)
        root.bind("<KeyRelease>", lambda event: self.held.discard(event.keysym))
        root.bind("<FocusOut>", lambda event: self.held.clear())
        root.protocol("WM_DELETE_WINDOW", self.close)
        threading.Thread(target=self.worker, daemon=True).start()
        root.after(30, self.poll)

    def worker(self):
        client = self.client_factory(self.url)
        try:
            if not self.dry_run:
                client.start()
            self.results.put(
                (
                    "ready",
                    "Ready — press an arrow key."
                    + (" DRY RUN: no touches." if self.dry_run else ""),
                )
            )
            while not self.stopped.is_set():
                try:
                    direction = self.commands.get(timeout=0.1)
                except queue.Empty:
                    continue
                if self.stopped.is_set():
                    break
                elapsed = 0 if self.dry_run else client.native_swipe(direction)
                self.results.put(
                    ("done", f"{direction} acknowledged ({elapsed:.0f} ms). Ready.")
                )
        except Exception as exc:  # noqa: BLE001 - Report any worker failure to the UI.
            self.results.put(
                ("error", f"Connection stopped: {exc}. Close and reopen to reconnect.")
            )
        finally:
            client.close()

    def key_down(self, event):
        if event.keysym == "Escape":
            self.close()
            return "break"
        if event.keysym not in ("Left", "Right", "Up", "Down"):
            return
        if event.keysym in self.held:
            return "break"
        self.held.add(event.keysym)
        if self.ready and not self.busy:
            self.busy = True
            self.status.set(f"Sending {event.keysym.upper()}…")
            self.commands.put_nowait(event.keysym.upper())
        return "break"

    def poll(self):
        while True:
            try:
                kind, message = self.results.get_nowait()
            except queue.Empty:
                break
            self.ready = kind != "error"
            self.busy = False
            self.status.set(message)
        if not self.stopped.is_set():
            self.root.after(30, self.poll)

    def close(self):
        self.stopped.set()
        self.ready = False
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backend", choices=("fast", "devicekit", "wda"), default="fast"
    )
    parser.add_argument("--url", help="Override the selected helper's localhost URL")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    root = tk.Tk()
    client_factory = {
        "devicekit": DeviceKitSwipeClient,
        "fast": FastDeviceKitSwipeClient,
        "wda": WdaSwipeClient,
    }[args.backend]
    url = args.url or (
        "http://127.0.0.1:12004" if args.backend != "wda" else "http://127.0.0.1:8100"
    )
    ArrowController(root, url, args.dry_run, client_factory)
    root.mainloop()


if __name__ == "__main__":
    main()
