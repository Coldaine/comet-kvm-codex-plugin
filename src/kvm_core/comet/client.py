from __future__ import annotations
import asyncio
import base64
import logging
import time
import json
from typing import Optional, Dict, List, Tuple
from urllib.parse import urlparse
import httpx
import websockets
import ssl as _ssl

LOG = logging.getLogger("kvm_core.comet")

# US key mapping
CHAR_TO_KEY: dict[str, tuple[str, bool]] = {}
def _build_keymap() -> dict[str, tuple[str, bool]]:
    m: dict[str, tuple[str, bool]] = {}
    for c in "abcdefghijklmnopqrstuvwxyz":
        m[c] = (f"Key{c.upper()}", False)
        m[c.upper()] = (f"Key{c.upper()}", True)
    digits = "0123456789"
    shift_digits = ")!@#$%^&*("
    for i, d in enumerate(digits):
        m[d] = (f"Digit{d}", False)
        m[shift_digits[i]] = (f"Digit{d}", True)
    extras = {
        " ": ("Space", False),
        "\t": ("Tab", False),
        "\n": ("Enter", False),
        "\r": ("Enter", False),
        "-": ("Minus", False), "_": ("Minus", True),
        "=": ("Equal", False), "+": ("Equal", True),
        "[": ("BracketLeft", False), "{": ("BracketLeft", True),
        "]": ("BracketRight", False), "}": ("BracketRight", True),
        "\\": ("Backslash", False), "|": ("Backslash", True),
        ";": ("Semicolon", False), ":": ("Semicolon", True),
        "'": ("Quote", False), '"': ("Quote", True),
        ",": ("Comma", False), "<": ("Comma", True),
        ".": ("Period", False), ">": ("Period", True),
        "/": ("Slash", False), "?": ("Slash", True),
        "`": ("Backquote", False), "~": ("Backquote", True),
    }
    m.update(extras)
    return m

CHAR_TO_KEY.update(_build_keymap())

KEY_ALIASES: dict[str, str] = {
    "ctrl": "ControlLeft", "control": "ControlLeft",
    "lctrl": "ControlLeft", "rctrl": "ControlRight",
    "shift": "ShiftLeft", "lshift": "ShiftLeft", "rshift": "ShiftRight",
    "alt": "AltLeft", "lalt": "AltLeft", "ralt": "AltRight",
    "altgr": "AltRight", "option": "AltLeft", "opt": "AltLeft",
    "meta": "MetaLeft", "lmeta": "MetaLeft", "rmeta": "MetaRight",
    "win": "MetaLeft", "windows": "MetaLeft",
    "cmd": "MetaLeft", "command": "MetaLeft",
    "super": "MetaLeft",
    "esc": "Escape", "escape": "Escape",
    "enter": "Enter", "return": "Enter",
    "tab": "Tab", "space": "Space", " ": "Space",
    "backspace": "Backspace", "bs": "Backspace",
    "delete": "Delete", "del": "Delete",
    "insert": "Insert", "ins": "Insert",
    "home": "Home", "end": "End",
    "pageup": "PageUp", "pgup": "PageUp",
    "pagedown": "PageDown", "pgdn": "PageDown", "pgdown": "PageDown",
    "up": "ArrowUp", "down": "ArrowDown", "left": "ArrowLeft", "right": "ArrowRight",
    "capslock": "CapsLock", "caps": "CapsLock",
    "numlock": "NumLock", "scrolllock": "ScrollLock", "scroll": "ScrollLock",
    "printscreen": "PrintScreen", "prtsc": "PrintScreen", "prtscn": "PrintScreen",
    "pause": "Pause", "break": "Pause",
    "menu": "ContextMenu", "contextmenu": "ContextMenu",
}
for i in range(1, 13):
    KEY_ALIASES[f"f{i}"] = f"F{i}"

MOUSE_BUTTONS = {"left", "right", "middle", "up", "down"}
MODIFIER_KEYS = {
    "ControlLeft", "ControlRight",
    "ShiftLeft", "ShiftRight",
    "AltLeft", "AltRight",
    "MetaLeft", "MetaRight",
}

def resolve_key_name(name: str) -> str:
    if not name:
        raise ValueError("empty key name")
    if name in CHAR_TO_KEY.values() or name.startswith(("Key", "Digit", "Numpad", "Arrow", "F")):
        return name
    return KEY_ALIASES.get(name.lower(), name)

class CometClient:
    def __init__(self, host: str, username: str = "admin", password: str = "", verify_ssl: bool = False):
        self.host = host
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.base_url = f"https://{host}" if "://" not in host else host.rstrip("/")
        self.http: Optional[httpx.AsyncClient] = None
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.held: dict[str, float] = {}  # key -> down_at (monotonic)
        self.send_lock = asyncio.Lock()
        self.watchdog_task: Optional[asyncio.Task] = None
        self.pinger_task: Optional[asyncio.Task] = None
        self._ocr_state_cache: Optional[dict] = None

        self.min_down_up_gap = 0.025
        self.inter_char_gap = 0.010
        self.mod_gap = 0.005
        self.stale_s = 0.250
        self.watchdog_period = 0.040
        self.ws_ping_period = 1.0

    async def connect(self) -> bool:
        if self.http is not None:
            await self.disconnect()

        self.http = httpx.AsyncClient(verify=self.verify_ssl, timeout=10.0, follow_redirects=True)
        try:
            login = await self.http.post(
                f"{self.base_url}/api/auth/login",
                data={"user": self.username, "passwd": self.password, "expire": "0"},
            )
            login.raise_for_status()
            token = self.http.cookies.get("auth_token")
            if not token:
                raise RuntimeError("Login succeeded but no auth_token cookie returned.")
        except Exception as e:
            if self.http:
                await self.http.aclose()
            self.http = None
            raise RuntimeError(f"login failed against {self.base_url}: {e}") from e

        parsed = urlparse(self.base_url)
        ws_scheme = "wss" if parsed.scheme == "https" else "ws"
        ws_url = f"{ws_scheme}://{parsed.netloc}/api/ws?auth_token={token}&stream=false"

        sslctx = None
        if ws_scheme == "wss" and not self.verify_ssl:
            sslctx = _ssl.create_default_context()
            sslctx.check_hostname = False
            sslctx.verify_mode = _ssl.CERT_NONE

        try:
            self.ws = await websockets.connect(
                ws_url,
                ssl=sslctx,
                max_size=8 * 1024 * 1024,
                open_timeout=10.0,
                ping_interval=None,
            )
        except Exception as e:
            if self.http:
                await self.http.aclose()
            self.http = None
            self.ws = None
            raise RuntimeError(f"WebSocket connection failed: {e}") from e

        self.watchdog_task = asyncio.create_task(self._watchdog_loop(), name="comet-watchdog")
        self.pinger_task = asyncio.create_task(self._pinger_loop(), name="comet-pinger")
        LOG.info("Connected to Comet KVM at %s", self.base_url)
        return True

    async def disconnect(self):
        # Release held keys first
        try:
            async with self.send_lock:
                for k in list(self.held.keys()):
                    try:
                        await self._ws_send_key(k, state=False, finish=True)
                    except Exception:
                        pass
        except Exception:
            pass

        self.held.clear()

        for t in (self.watchdog_task, self.pinger_task):
            if t:
                t.cancel()
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass

        self.watchdog_task = None
        self.pinger_task = None

        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
            self.ws = None

        if self.http:
            try:
                await self.http.aclose()
            except Exception:
                pass
            self.http = None
        self._ocr_state_cache = None
        LOG.info("Disconnected from Comet KVM")

    async def get_screenshot(self, preview: bool = True, max_width: int = 1024, quality: int = 60) -> bytes:
        if not self.http:
            raise RuntimeError("Not connected")
        params = {"allow_offline": "true"}
        if preview:
            params["preview"] = "true"
            params["preview_max_width"] = str(int(max_width))
            params["preview_quality"] = str(max(1, min(100, int(quality))))
        r = await self.http.get(f"{self.base_url}/api/streamer/snapshot", params=params)
        r.raise_for_status()
        return r.content

    async def get_ocr_state(self, refresh: bool = False) -> dict:
        """Return the Comet/PiKVM native OCR capability state."""
        if not self.http:
            raise RuntimeError("Not connected")
        if self._ocr_state_cache is not None and not refresh:
            return dict(self._ocr_state_cache)
        response = await self.http.get(f"{self.base_url}/api/streamer/ocr")
        response.raise_for_status()
        payload = response.json()
        state = payload.get("result", {}).get("ocr")
        if not isinstance(state, dict):
            raise RuntimeError("Native OCR status response did not contain result.ocr")
        self._ocr_state_cache = dict(state)
        return dict(state)

    async def get_native_ocr_text(
        self,
        languages: str = "",
        crop: tuple[int, int, int, int] | None = None,
    ) -> str:
        """Run the device's native OCR endpoint and return its plain text result."""
        if not self.http:
            raise RuntimeError("Not connected")

        params = {"allow_offline": "true", "ocr": "true"}
        if languages.strip():
            params["ocr_langs"] = languages.strip()
        if crop is not None:
            left, top, right, bottom = crop
            params.update({
                "ocr_left": str(left),
                "ocr_top": str(top),
                "ocr_right": str(right),
                "ocr_bottom": str(bottom),
            })

        response = await self.http.get(f"{self.base_url}/api/streamer/snapshot", params=params)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "").lower()
        if "json" not in content_type:
            return response.text

        payload = response.json()
        result = payload.get("result")
        if isinstance(result, str):
            return result
        if isinstance(result, dict) and isinstance(result.get("text"), str):
            return result["text"]
        raise RuntimeError("Native OCR response did not contain recognized text")

    async def send_key_event(self, key: str, state: bool, finish: bool = False):
        async with self.send_lock:
            await self._ws_send_key(key, state, finish)

    async def _ws_send_key(self, key: str, state: bool, finish: bool = False):
        if not self.ws:
            raise RuntimeError("WS disconnected")
        payload = json.dumps({
            "event_type": "key",
            "event": {"key": key, "state": bool(state), "finish": bool(finish)},
        })
        await self.ws.send(payload)
        if state:
            self.held[key] = time.monotonic()
        else:
            self.held.pop(key, None)

    async def send_text(self, text: str, wpm: int = 200) -> dict:
        inter = max(0.0, 60.0 / max(1, wpm) / 5.0) if wpm > 0 else 0.0
        start = time.monotonic()
        sent = 0
        skipped: list[str] = []
        async with self.send_lock:
            for ch in text:
                mapping = CHAR_TO_KEY.get(ch)
                if mapping is None:
                    skipped.append(ch)
                    continue
                key, needs_shift = mapping
                mods = ["ShiftLeft"] if needs_shift else []
                await self._press_with_modifiers(key, mods)
                sent += 1
                await asyncio.sleep(inter + self.inter_char_gap)
        return {"chars": sent, "skipped": skipped, "elapsed_s": round(time.monotonic() - start, 3)}

    async def send_combo(self, combo: str) -> dict:
        parts = [p.strip() for p in combo.split("+") if p.strip()]
        if not parts:
            raise ValueError("empty combo")

        if len(parts) == 1:
            key = resolve_key_name(parts[0])
            async with self.send_lock:
                await self._atomic_press(key)
            return {"sent": combo, "modifiers": [], "key": key}

        *mod_tokens, main_token = parts
        modifiers = [resolve_key_name(m) for m in mod_tokens]
        key = resolve_key_name(main_token)
        async with self.send_lock:
            await self._press_with_modifiers(key, modifiers)
        return {"sent": combo, "modifiers": modifiers, "key": key}

    async def hold_key(self, key: str, duration_ms: int) -> dict:
        duration_ms = max(1, min(5000, int(duration_ms)))
        canonical = resolve_key_name(key)
        async with self.send_lock:
            await self._ws_send_key(canonical, state=True, finish=False)
        try:
            await asyncio.sleep(duration_ms / 1000.0)
        finally:
            async with self.send_lock:
                await self._ws_send_key(canonical, state=False, finish=True)
        return {"key": canonical, "duration_ms": duration_ms}

    async def release_all(self) -> dict:
        released: list[str] = []
        async with self.send_lock:
            for k in list(self.held.keys()):
                try:
                    await self._ws_send_key(k, state=False, finish=True)
                    released.append(k)
                except Exception as e:
                    LOG.error("Failed to release key %s: %s", k, e)
        return {"released": released}

    async def mouse_move_pct(self, x_pct: float, y_pct: float) -> dict:
        x = int(round((max(0.0, min(100.0, x_pct)) / 100.0) * 65535 - 32768))
        y = int(round((max(0.0, min(100.0, y_pct)) / 100.0) * 65535 - 32768))
        async with self.send_lock:
            await self._ws_send_mouse_move(x, y)
        return {"x": x, "y": y, "x_pct": x_pct, "y_pct": y_pct}

    async def mouse_click(self, button: str = "left", count: int = 1) -> dict:
        count = max(1, min(5, int(count)))
        async with self.send_lock:
            for _ in range(count):
                await self._ws_send_mouse_button(button, True)
                await asyncio.sleep(self.min_down_up_gap)
                await self._ws_send_mouse_button(button, False)
                await asyncio.sleep(0.030)
        return {"button": button, "count": count}

    async def mouse_scroll(self, dx: int = 0, dy: int = 0) -> dict:
        async with self.send_lock:
            await self._ws_send_mouse_wheel(dx, dy)
        return {"dx": dx, "dy": dy}

    async def _ws_send_mouse_button(self, button: str, state: bool):
        if not self.ws:
            raise RuntimeError("WS disconnected")
        if button not in MOUSE_BUTTONS:
            raise ValueError(f"unknown mouse button: {button}")
        await self.ws.send(json.dumps({
            "event_type": "mouse_button",
            "event": {"button": button, "state": bool(state)},
        }))

    async def _ws_send_mouse_move(self, x: int, y: int):
        if not self.ws:
            raise RuntimeError("WS disconnected")
        x = max(-32768, min(32767, int(x)))
        y = max(-32768, min(32767, int(y)))
        await self.ws.send(json.dumps({
            "event_type": "mouse_move",
            "event": {"to": {"x": x, "y": y}},
        }))

    async def _ws_send_mouse_wheel(self, dx: int, dy: int):
        if not self.ws:
            raise RuntimeError("WS disconnected")
        dx = max(-127, min(127, int(dx)))
        dy = max(-127, min(127, int(dy)))
        await self.ws.send(json.dumps({
            "event_type": "mouse_wheel",
            "event": {"delta": {"x": dx, "y": dy}, "squash": False},
        }))

    async def _atomic_press(self, key: str, hold_s: float = 0.025):
        await self._ws_send_key(key, state=True, finish=False)
        await asyncio.sleep(max(hold_s, self.min_down_up_gap))
        await self._ws_send_key(key, state=False, finish=True)

    async def _press_with_modifiers(self, key: str, modifiers: list[str]):
        for m in modifiers:
            await self._ws_send_key(m, state=True, finish=False)
            await asyncio.sleep(self.mod_gap)
        await self._atomic_press(key)
        for m in reversed(modifiers):
            await self._ws_send_key(m, state=False, finish=True)
            await asyncio.sleep(self.mod_gap)

    async def _watchdog_loop(self):
        try:
            while True:
                await asyncio.sleep(self.watchdog_period)
                now = time.monotonic()
                stale = [k for k, t in self.held.items() if now - t > self.stale_s]
                for k in stale:
                    LOG.warning("watchdog releasing stale key %s", k)
                    try:
                        async with self.send_lock:
                            await self._ws_send_key(k, state=False, finish=True)
                    except Exception as e:
                        LOG.error("watchdog send failed for %s: %s", k, e)
                    self.held.pop(k, None)
        except asyncio.CancelledError:
            return

    async def _pinger_loop(self):
        try:
            while True:
                await asyncio.sleep(self.ws_ping_period)
                if self.ws:
                    try:
                        await self.ws.send(json.dumps({"event_type": "ping"}))
                    except Exception:
                        return
        except asyncio.CancelledError:
            return

    def is_connected(self) -> bool:
        if self.http is None or self.ws is None:
            return False
        if hasattr(self.ws, "state"):
            return self.ws.state.name == "OPEN"
        return not self.ws.closed

    # ── ATX Power Control ──────────────────────────────────────────

    async def atx_power(self, action: str) -> dict:
        """Power on/off/reset the target via ATX board. Requires ATX hardware."""
        if not self.http:
            raise RuntimeError("Not connected")
        valid = {"on", "off", "reset"}
        if action not in valid:
            raise ValueError(f"Invalid ATX action '{action}'. Use: {valid}")
        r = await self.http.post(
            f"{self.base_url}/api/atx/power",
            json={"action": action},
        )
        if not r.is_success:
            body = r.text
            if "ATX" in body or "not connected" in body or "not available" in body:
                raise RuntimeError(f"ATX board not detected or not connected: {body}")
            r.raise_for_status()
        return {"action": action, "status": r.status_code}

    async def atx_click(self, button: str) -> dict:
        """
        Momentary press of power/reset button (~200ms pulse).
        Preferred over atx_power for clean reboots.
        """
        if not self.http:
            raise RuntimeError("Not connected")
        valid = {"power", "reset"}
        if button not in valid:
            raise ValueError(f"Invalid ATX button '{button}'. Use: {valid}")
        r = await self.http.post(
            f"{self.base_url}/api/atx/click",
            json={"button": button},
        )
        if not r.is_success:
            r.raise_for_status()
        return {"button": button, "status": r.status_code}

    # ── System Info ────────────────────────────────────────────────

    async def get_sysinfo(self) -> dict:
        """Retrieve device metadata: model, firmware version, capabilities."""
        if not self.http:
            raise RuntimeError("Not connected")
        r = await self.http.get(f"{self.base_url}/api/info")
        r.raise_for_status()
        return r.json()

    # ── Mass Storage (on-device file persistence) ──────────────────

    async def msd_upload(self, remote_path: str, data: bytes) -> dict:
        """
        Upload a file to the Comet's /userdata/media/ partition.
        Used for persisting BIOS maps and state databases on-device.

        remote_path: relative path under /userdata/media/
        """
        if not self.http:
            raise RuntimeError("Not connected")
        # Normalize: strip leading slash, prepend userdata/media base
        remote_path = remote_path.lstrip("/")
        if not remote_path.startswith("userdata/media/"):
            remote_path = f"userdata/media/{remote_path}"

        r = await self.http.post(
            f"{self.base_url}/api/msd/write",
            data={"path": remote_path},
            files={"file": ("blob", data, "application/octet-stream")},
        )
        if not r.is_success:
            r.raise_for_status()
        return {"path": remote_path, "size": len(data), "status": r.status_code}
