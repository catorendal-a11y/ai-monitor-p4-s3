# AI Monitor P4 host - feeds the panel with REAL provider usage.
#
# Sources:
#   codex : ChatGPT backend usage endpoint, authenticated with the local
#           Codex CLI login (~/.codex/auth.json). Same data the Codex CLI
#           shows in /status (5h primary window + weekly secondary window).
#   zcode : Z.AI GLM coding plan quota (api.z.ai/api/monitor/usage/quota/limit),
#           enabled with ZAI_API_KEY or aim_host.json ("zai_key").
#           ZCode encrypts its own credentials at rest, so the
#           key must come from the Z.AI console.
#
# Output: esp32-ai-monitor protocol frames (AIM1 framing) over the panel's
# USB CDC port. Default poll interval 240 s, auto re-detects the COM port.
#
# Usage:  python aim_host.py   (config file next to this script)

import json
import math
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from token_activity import TokenReporter, TokenSampler
from host_status import HostStatus, OPTIONS, FLAGS, validate_options
from provider_catalog import selected_providers
from board_profiles import configured_board, get_board, matches_info
from codex_support import codex_command, codex_home, read_rate_limits
from host_security import open_provider_request, read_local_json, safe_text, serial_port
import queue
import subprocess
import threading
from process_runtime import ChildCleanupError, start_child, stop_child
from project_version import HOST_VERSION, numeric_version

import serial
from serial.tools import list_ports

HERE = Path(sys.executable).resolve().parent / "tools" if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
CONFIG_PATH = HERE / "aim_host.json"
CODEX_AUTH = codex_home() / 'auth.json'
MAX_FRAME_BYTES = 4095
HEARTBEAT_SECONDS = 10
MAX_RESPONSE_BYTES = 65536


class CredentialError(ValueError):
    pass


def credential(value, optional=False):
    if not isinstance(value, str):
        raise CredentialError("Invalid credential format")
    value = value.strip()
    if not value and optional:
        return ""
    if not value or any(not 33 <= ord(character) <= 126 for character in value):
        raise CredentialError("Credentials must be a single printable token")
    return value


def read_json_response(response):
    raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("API response exceeds size limit")
    data = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("API response must be an object")
    return data


def window_minutes(seconds):
    if seconds is None:
        return 0
    if isinstance(seconds, bool):
        raise ValueError("Invalid window duration")
    seconds = float(seconds)
    if not math.isfinite(seconds) or seconds < 0 or seconds / 60 > 0xffffffff:
        raise ValueError("Invalid window duration")
    return int(seconds // 60)


def provider_failure(provider, error):
    # Header/JSON exceptions may contain credentials or server response text.
    # Return a category without copying exception details to the display/log.
    if isinstance(error, CredentialError):
        return f"{provider}: invalid login or API key"
    if isinstance(error, FileNotFoundError):
        return f"{provider}: login file not found"
    if isinstance(error, (ValueError, TypeError, KeyError, AttributeError)):
        return f"{provider}: invalid response data"
    if isinstance(error, OSError):
        return f"{provider}: connection failed; retrying"
    return f"{provider}: request failed; retrying"


LOG_PATH = HERE / "aim_host.log"


def LOG(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {safe_text(msg)}"
    if sys.stdout is not None:
        print(line, flush=True)
    try:
        if LOG_PATH.exists() and LOG_PATH.stat().st_size >= 1_000_000:
            os.replace(LOG_PATH, LOG_PATH.with_suffix(".log.1"))
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass

DEFAULT_CONFIG = {
    "board": "",          # First-time setup requires an explicit hardware choice.
    "providers": [],      # First-time setup requires an explicit selection.
    "port": "auto",       # "auto" = detect Espressif USB CDC, or e.g. "COM6"
    # 240 s: usage endpoints are free status endpoints (no model quota
    # consumed), but polling stays polite; the panel's LIVE badge tolerates
    # up to 5 min between frames.
    "interval_s": 240,
    "zai_key": "",        # paste a Z.AI coding plan API key here to enable Z CODE
    "zai_provider": "zcode"
}
DEFAULT_CONFIG.update({key: value[2] for key, value in OPTIONS.items()})
DEFAULT_CONFIG.update(FLAGS)


LOCK_PATH = HERE / "aim_host.lock"
_lock_handle = None


def acquire_lock():
    """OS-owned lock: atomic between processes and released automatically on exit."""
    global _lock_handle
    if _lock_handle is not None:
        return False
    handle = LOCK_PATH.open("a+b")
    handle.seek(0, 2)
    if handle.tell() == 0:
        handle.write(b" ")
        handle.flush()
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return False
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()).encode("ascii"))
    handle.flush()
    _lock_handle = handle
    return True


def release_lock():
    global _lock_handle
    if _lock_handle is not None:
        _lock_handle.close()
        _lock_handle = None
    # Keep the file: unlinking it could let another process lock a different inode.


def zcode_key(config):
    source = 'ZAI_API_KEY environment variable' if 'ZAI_API_KEY' in os.environ else 'saved zai_key in tools/aim_host.json'
    try:
        return credential(os.environ.get('ZAI_API_KEY', config.get('zai_key', '')), optional=True)
    except ValueError:
        raise ValueError('Invalid ZCode credential format in ' + source + '. Use a single printable API key.') from None


def load_config():
    if CONFIG_PATH.exists():
        try:
            cfg = read_local_json(CONFIG_PATH)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {CONFIG_PATH.name}: line {exc.lineno}") from exc
    else:
        cfg = {}
    if not isinstance(cfg, dict):
        raise ValueError("aim_host.json must contain a JSON object")
    out = dict(DEFAULT_CONFIG)
    out.update(cfg)
    out["providers"] = selected_providers(cfg, legacy=CONFIG_PATH.exists())
    out["board"] = configured_board(cfg, legacy=CONFIG_PATH.exists())
    out["port"] = serial_port(out["port"])
    validate_options(out)
    if not isinstance(out["interval_s"], int) or isinstance(out["interval_s"], bool):
        raise ValueError("interval_s must be an integer")
    if not 15 <= out["interval_s"] <= 240:
        raise ValueError("interval_s must be between 15 and 240 (panel freshness limit)")
    if out["zai_provider"] != "zcode":
        raise ValueError("zai_provider must be 'zcode'")
    if not isinstance(out["zai_key"], str):
        raise ValueError("zai_key must be a string")
    out["zai_key"] = zcode_key(out)
    # Keep existing configuration and credentials untouched at startup.
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")
    return out


def now_iso_epoch(epoch_s):
    return datetime.fromtimestamp(epoch_s, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def percent_value(value):
    if value is None or isinstance(value, bool):
        raise ValueError("Missing usage percentage")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError("Invalid usage percentage")
    return number


class ProviderNotice(str):
    def __new__(cls, message, retry_after=0):
        value = super().__new__(cls, message)
        value.retry_after = retry_after
        return value


def retry_after_seconds(headers):
    value = headers.get("Retry-After") if headers else None
    if not isinstance(value, str):
        return 0
    try:
        seconds = int(value) if value.strip().isdigit() else math.ceil(parsedate_to_datetime(value).timestamp() - time.time())
        return max(0, min(86400, seconds))
    except (ValueError, TypeError, OverflowError, OSError):
        return 0


def http_notice(provider, error):
    delay = retry_after_seconds(error.headers)
    if error.code in (401, 403):
        return ProviderNotice(f"{provider}: check login or API key", delay)
    if error.code == 429:
        return ProviderNotice(f"{provider}: rate limited; retrying", delay)
    return ProviderNotice(f"{provider}: HTTP {error.code}; retrying", delay)


class ProviderRetries:
    """Monotonic, independent cooldowns survive USB reconnections."""
    def __init__(self, interval=240):
        self.interval = interval
        self.states = {}

    def remaining(self, provider):
        state = self.states.get(provider)
        return max(0, math.ceil(state[1] - time.monotonic())) if state else 0

    def deferred_notice(self, provider):
        return f"{provider}: retry in {self.remaining(provider)} s. {self.states[provider][2]}"

    def failed(self, provider, notice):
        failures = min(9, self.states.get(provider, (0, 0, ""))[0] + 1)
        delay = max(min(3600, max(15, self.interval) * 2 ** (failures - 1)),
                    getattr(notice, "retry_after", 0))
        self.states[provider] = (failures, time.monotonic() + delay, str(notice))

    def succeeded(self, provider):
        self.states.pop(provider, None)


def reset_display(value, minutes=0):
    """Use the PC's local timezone, retaining dates for long quota windows."""
    if not value:
        return ""
    try:
        reset = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone()
    except (ValueError, TypeError, AttributeError):
        return str(value)[:19]
    return reset.strftime("%d %b %H:%M" if minutes >= 1440 else "%H:%M")


def zai_reset_iso(value):
    if not value:
        return ""
    try:
        milliseconds = float(value)
    except (ValueError, TypeError):
        return str(value)
    try:
        return now_iso_epoch(milliseconds / 1000.0)
    except (ValueError, OverflowError, OSError):
        return ""


def clock_fields():
    local = datetime.now().astimezone()
    return {
        "time": local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "displayTime": local.strftime("%H:%M"),
        "displaySeconds": local.second,
        "tzOffsetMinutes": int(local.utcoffset().total_seconds() // 60),
    }


def reset_seconds(value, epoch_now=None):
    if not isinstance(value, str) or "T" not in value:
        return None
    try:
        reset = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if reset.tzinfo is None:
            return None
        remaining = math.ceil(reset.timestamp() - (time.time() if epoch_now is None else epoch_now))
        return max(0, min(0xffffffff - 60, remaining))
    except (ValueError, OverflowError, OSError):
        return None


# ───────────────────────────────────────────────────────────────────────────────
# PROVIDER FETCHES - each returns (rows, notice) or None on failure
# ───────────────────────────────────────────────────────────────────────────────


def fetch_codex():
    """Codex (ChatGPT plan) usage via the local Codex CLI login token."""
    command = codex_command()
    if command:
        try:
            data = read_rate_limits(command)
            buckets = data.get('rateLimitsByLimitId')
            limit = buckets.get('codex') if isinstance(buckets, dict) else None
            if limit is None: limit = data.get('rateLimits')
            if not isinstance(limit, dict) or limit.get('limitId') not in (None, 'codex'):
                raise ValueError('No supported Codex quota bucket')
            rows = []
            for key, title in [('primary','Session'),('secondary','Secondary')]:
                window = limit.get(key)
                if window is None: continue
                if not isinstance(window, dict): raise ValueError('Invalid Codex window')
                minutes = window.get('windowDurationMins')
                if minutes is None: minutes = 0
                if type(minutes) is not int or not 0 <= minutes <= 0xffffffff: raise ValueError('Invalid window duration')
                reset = window.get('resetsAt')
                percent = min(100.0, percent_value(window.get('usedPercent')))
                rows.append({'title':'Week' if key == 'secondary' and minutes == 10080 else title,
                             'usedPercent':percent,
                             'windowMinutes':minutes, 'resetsAt':now_iso_epoch(reset) if reset is not None else ''})
            if not rows: return None, 'Codex: no plan quota; sign in to CLI with ChatGPT'
            return rows, None
        except Exception:
            return None, 'Codex: quota unavailable; retry setup or update the official CLI'
    try:
        auth = read_local_json(CODEX_AUTH)
        access = (auth.get("tokens") or {}).get("access_token")
        if not access:
            return None, "Codex: no access_token in auth.json"
        access = credential(access)
        req = urllib.request.Request("https://chatgpt.com/backend-api/wham/usage")
        req.add_header("Authorization", "Bearer " + access)
        req.add_header("User-Agent", "AI-Monitor/" + numeric_version(HOST_VERSION))
        with open_provider_request(req) as r:
            data = read_json_response(r)
        rl = data.get("rate_limit") or {}
        rows = []
        pw = rl.get("primary_window") or {}
        if pw:
            rows.append({
                "title": "Session",
                "usedPercent": percent_value(pw.get("used_percent")),
                "resetsAt": now_iso_epoch(pw["reset_at"]) if pw.get("reset_at") else "",
                "windowMinutes": window_minutes(pw.get("limit_window_seconds")),
            })
        sw = rl.get("secondary_window") or {}
        if sw:
            minutes = window_minutes(sw.get("limit_window_seconds"))
            rows.append({
                "title": "Week" if minutes == 10080 else "Secondary",
                "usedPercent": percent_value(sw.get("used_percent")),
                "resetsAt": now_iso_epoch(sw["reset_at"]) if sw.get("reset_at") else "",
                "windowMinutes": minutes,
            })
        if not rows:
            return None, "Codex: no rate_limit windows in response"
        return rows, None
    except urllib.error.HTTPError as error:
        return None, http_notice("Codex", error)
    except Exception as e:
        return None, provider_failure("Codex", e)


def fetch_zcode(api_key):
    """Z.AI GLM coding plan quota. Auth: raw key, NO Bearer prefix."""
    try:
        api_key = credential(api_key)
        req = urllib.request.Request("https://api.z.ai/api/monitor/usage/quota/limit")
        req.add_header("Authorization", api_key.strip())
        req.add_header("Accept-Language", "en-US,en")
        with open_provider_request(req) as r:
            data = read_json_response(r)
        success, code = data.get("success"), data.get("code")
        if success is not None and type(success) is not bool:
            raise ValueError("Invalid success flag")
        accepted_code = type(code) is int and code in (0, 200)
        accepted = success is not False and (success is True or accepted_code) and (code is None or accepted_code)
        if not accepted:
            code = data.get("code")
            if type(code) is int and code in (401, 403):
                return None, "Z.AI: check login or API key"
            if type(code) is int and code == 429:
                return None, "Z.AI: rate limited; retrying"
            return None, "Z.AI: request rejected"
        limits = ((data.get("data") or {}).get("limits")) or []
        rows = []
        for lim in limits:
            quota_type = lim.get("type")
            if quota_type not in ("CREDIT_LIMIT", "TOKENS_LIMIT", "TIME_LIMIT"):
                continue
            unit = lim.get("unit")
            # The provider's official usage plugin distinguishes monthly MCP
            # calls (TIME_LIMIT) from model quotas. Unit 6 is a weekly model
            # window, not a month; unit 3 is hours (normally number=5).
            if quota_type == "TIME_LIMIT":
                title, minutes = "Monthly MCP", 43200
            elif type(unit) is int and unit in (3, 6):
                number = lim.get("number", 5 if unit == 3 else 1)
                if type(number) is not int or number < 1:
                    raise ValueError("Invalid quota window length")
                minutes = number * (60 if unit == 3 else 10080)
                if minutes > 0xffffffff:
                    raise ValueError("Invalid quota window length")
                title = "Session" if minutes == 300 else "Week" if minutes == 10080 else "Quota"
            elif quota_type == "TOKENS_LIMIT" and unit is None:
                title, minutes = "Session", 300  # legacy official plugin format
            else:
                title, minutes = "Quota", 0
            percentage = lim.get("percentage")
            if percentage is None and quota_type == "TIME_LIMIT":
                used, total = lim.get("currentValue"), lim.get("usage")
                if (type(used) not in (int, float) or type(total) not in (int, float)
                        or not math.isfinite(used) or not math.isfinite(total)
                        or used < 0 or total <= 0):
                    raise ValueError("Invalid MCP quota counts")
                percentage = 100 * used / total
            reset = lim.get("nextResetTime") or lim.get("resetAt")
            reset_iso = zai_reset_iso(reset)
            rows.append({
                "title": title,
                "usedPercent": percent_value(percentage),
                "resetsAt": reset_iso,
                "windowMinutes": minutes,
            })
        if not rows:
            return None, "Z.AI: no quota entries"
        return rows, None
    except urllib.error.HTTPError as error:
        return None, http_notice("Z.AI", error)
    except Exception as e:
        return None, provider_failure("Z.AI", e)


# ───────────────────────────────────────────────────────────────────────────────
# PANEL LINK (esp32-ai-monitor protocol)
# ───────────────────────────────────────────────────────────────────────────────
def find_port(preferred, board_id='guition-p4'):
    if preferred and preferred != "auto":
        return preferred
    try:
        board = get_board(board_id)
        ports = sorted({port.device for port in list_ports.comports() if port.vid in board.usb_vids})
        if len(ports) > 1:
            LOG("Multiple candidate ports found; choose an explicit port: " + ", ".join(ports))
            return None
        return ports[0] if ports else None
    except Exception as e:
        LOG(f"port scan failed: {e}")
        return None


class Panel:
    def __init__(self, port_name):
        self.ser = serial.Serial(port_name, 115200, timeout=0.2, write_timeout=2)
        self.name = port_name
        self._rx = bytearray()
        self.boot_id = None
        self.last_uptime = None
        self.refresh_request_id = None
        self.last_poll_success = True
        self.retries = ProviderRetries()
        self.cycle_active = False
        self.active_refresh_id = None
        self.cycle_deadline = None
        self.activity_supported = False
        self.tokens_supported = False
        self.provider_selection_supported = False
        self.sessions_supported = False
        self.token_reporter = None
        self.info = {}
        self.expected_board = None
        self.hardware_pending = False
        self.live_client = None
        self.live_retry_at = 0
        self.permission_runtime = None  # Explicit validated setup only; never auto-enable from USB.
        self.mirror_service = None
        self.companion_service = None

    def attach_permission_runtime(self, runtime):
        from permission_runtime import PermissionRuntime
        if not isinstance(runtime, PermissionRuntime):
            raise ValueError('A locally validated permission runtime is required')
        previous = getattr(self, 'permission_runtime', None)
        if previous is not None and previous is not runtime:
            previous.close()
        self.permission_runtime = runtime
        return runtime.attach(self)

    def close(self):
        try:
            runtime = getattr(self, 'permission_runtime', None)
            if runtime is not None: runtime.close()
        finally:
            mirror = getattr(self, "mirror_service", None)
            if mirror is not None: mirror.close()
            companion=getattr(self,'companion_service',None)
            if companion is not None:companion.detach()
            self.ser.close()

    def refresh_status(self, request_id, state, message):
        self.send_line(json.dumps({"cmd": "refresh_status", "requestId": request_id, "state": state, "message": message}))

    def take_refresh_request(self):
        request_id = self.refresh_request_id
        self.refresh_request_id = None
        return request_id

    def activity(self, state, message):
        if self.activity_supported:
            self.send_line(json.dumps({"cmd": "host_activity", "state": state, "message": message}))

    def handle_event(self, message):
        runtime = getattr(self, 'permission_runtime', None)
        if runtime is not None and runtime.handle_event(message):
            return True
        if message.get('type') == 'hardware':
            health = getattr(self, 'health', None)
            if not getattr(self, 'hardware_pending', False) or self.expected_board is None or not isinstance(health, HostStatus):
                return True
            try:
                from hardware_baseline import validate_hardware
                data = validate_hardware(message, self.expected_board.id)
                if self.boot_id is not None and data['bootId'] != self.boot_id:
                    return True
                health.data['hardware'] = data
                health.data['hardware_at'] = time.time()
                self.hardware_pending = False
                health.update()
            except ValueError:
                pass  # Invalid optional diagnostics never break quota/USB monitoring.
            return True
        request_id = message.get("requestId")
        if message.get("type") != "refresh_request" or type(request_id) is not int or not 0 < request_id <= 0xffffffff:
            return False
        if self.cycle_active:
            self.active_refresh_id = request_id
            self.refresh_status(request_id, "updating", "Joining the current provider update")
        else:
            self.refresh_request_id = request_id
            self.refresh_status(request_id, "waiting", "Queued; API polling cooldown is 15 s")
        return True

    def collect_requests(self):
        while self.ser.in_waiting:
            self._rx.extend(self.ser.read(min(512, self.ser.in_waiting)))
            if len(self._rx) > 16384:
                raise RuntimeError("Panel reply exceeds receive buffer")
        while b"\n" in self._rx:
            line, _, rest = self._rx.partition(b"\n")
            self._rx = bytearray(rest)
            try:
                message = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                continue
            if isinstance(message, dict):
                self.handle_event(message)

    def heartbeat(self):
        fields = dict(clock_fields(), cmd="get_info", heartbeat=True, manualRefresh=True)
        self.send_line(json.dumps(fields))
        info = self.wait_for("info")
        if self.expected_board is not None and not matches_info(self.expected_board, info):
            raise RuntimeError('Connected display does not match the selected board. Open First-time setup.')
        self.info = info
        self.activity_supported = info.get("hostActivity") is True
        self.tokens_supported = info.get("tokenActivity") is True
        self.provider_selection_supported = info.get('providerSelection') is True
        self.sessions_supported = info.get('sessionActivity') is True
        boot_id, uptime = info.get("bootId"), info.get("uptime")
        if self.boot_id is not None and boot_id != self.boot_id:
            raise ConnectionResetError("Panel restarted; restoring views")
        if self.boot_id is None and self.last_uptime is not None and uptime is not None and uptime < self.last_uptime:
            raise ConnectionResetError("Panel uptime reset; restoring views")
        self.boot_id, self.last_uptime = boot_id, uptime
        status = getattr(self, 'health', None)
        if isinstance(status, HostStatus):
            source_mask=info.get('tokenSources')
            if type(source_mask) is int and 0<=source_mask<=255:
                age=info.get('tokenAgeSeconds')
                status.data['display_sources']=source_mask if info.get('tokenKnown') is True and type(age) is int and 0<=age<35 else 0
                status.data['display_sources_at']=time.time()
            history=getattr(self,'history',None)
            if history is not None:
                status.data['history']={'enabled':history.enabled,'error':history.last_error}
            if isinstance(self.token_reporter, TokenSampler):
                state=self.token_reporter.read_state()
                if state=='stalled' and status.data.get('local_reader')!='stalled':
                    LOG('Local token read exceeded 15 seconds; USB continues. Restart host if activity does not resume.')
                status.data['local_reader']=state
            status.update('connected', self.name)

    def report_tokens(self):
        message = None
        mirror = getattr(self, "mirror_service", None)
        if mirror is not None: mirror.pump(self)
        companion=getattr(self,'companion_service',None)
        if companion is not None:
            companion.pump(self)
            health=getattr(self,'health',None)
            if health is not None:health.data['companion']=companion.snapshot()
        runtime = getattr(self, 'permission_runtime', None)
        if runtime is not None: runtime.pump()
        sampler=getattr(self,'history_sampler',None)
        if sampler is not None and type(self.info.get('historyProtocol')) is int and self.info['historyProtocol'] in (1,2,3):
            summary=sampler.take()
            if summary is not None:
                from usb_history import UsbHistoryClient
                try:
                    if getattr(self,'history_client',None) is None:self.history_client=UsbHistoryClient(self)
                    self.history_client.send(summary)
                except (ValueError,TimeoutError,RuntimeError):self.history_client=None
                # Actual serial errors retain the normal reconnect path; optional history cannot block quota.
        if self.tokens_supported and isinstance(self.token_reporter, (TokenReporter, TokenSampler)):
            message = self.token_reporter.poll()
            if message is not None:
                sessions = message.get('sessions')
                self.send_line(json.dumps({key:value for key,value in message.items() if key not in ('sessions','deltas','live_agents','live_sampled_at')}))
                if sessions is not None:
                    if self.sessions_supported: self.send_line(json.dumps(sessions))
                    health = getattr(self, 'health', None)
                    if isinstance(health, HostStatus):
                        health.data['sessions'] = sessions
                        health.data['sessions_at'] = time.time()
        sampler=getattr(self,'live_sampler',None)
        # Dedicated production reader; keep compatibility with an older injected sampler.
        live_message=sampler.poll() if sampler is not None else message
        if not (isinstance(live_message,dict) and 'live_agents' in live_message):return
        supported=(type(self.info.get('liveProtocol')) is int and self.info['liveProtocol']==1
                   and self.info.get('livePermissions') is False)
        if not supported:
            self.live_health('unsupported',0);return
        if time.monotonic()<getattr(self,'live_retry_at',0):return
        from usb_live import UsbLiveClient
        try:
            if getattr(self,'live_client',None) is None:
                self.live_client=UsbLiveClient(self);self.live_client.open()
            sampled=live_message.get('live_sampled_at')
            fresh_sample=type(sampled) in (int,float) and 0<=time.monotonic()-sampled<=10
            agents=live_message['live_agents'] if fresh_sample else []
            self.live_client.send(agents)
            self.live_health('acknowledged' if fresh_sample else 'stale',len(agents))
        except (ValueError,TimeoutError,RuntimeError):
            # Optional telemetry failure is visible but never takes down quota monitoring.
            self.live_client=None;self.live_retry_at=time.monotonic()+30
            self.live_health('error',0)
        # Serial I/O errors still propagate to the existing reconnect path.

    def live_health(self,state,count):
        health=getattr(self,'health',None)
        if isinstance(health,HostStatus):
            health.data['live']={'state':state,'agent_count':count,'updated_at':time.time()}
            health.update()

    def _write(self, data):
        if self.ser.write(data) != len(data):
            raise serial.SerialTimeoutException("Incomplete serial write")

    def send_line(self, line):
        self._write(line.encode("utf-8") + b"\n")

    def send_frame(self, payload, frame_id):
        raw = payload.encode("utf-8")
        if not 0 < len(raw) <= MAX_FRAME_BYTES:
            raise ValueError(f"Frame must contain 1..{MAX_FRAME_BYTES} bytes")
        self._write(b"AIM1 %d %d\n" % (len(raw), frame_id) + raw + b"\n")

    def wait_for(self, message_type, seconds=2.0, frame_id=None, command=None):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            while b"\n" in self._rx:
                line, _, rest = self._rx.partition(b"\n")
                self._rx = bytearray(rest)
                try:
                    message = json.loads(line)
                except (ValueError, UnicodeDecodeError):
                    continue  # boot messages and debug logs
                if not isinstance(message, dict):
                    continue
                # A development collector explicitly waits for hardware. Only
                # unsolicited diagnostics belong to the asynchronous host path.
                if not (message_type == 'hardware' and message.get('type') == 'hardware') and self.handle_event(message):
                    continue
                if frame_id is not None and message.get("frameId") != frame_id:
                    continue
                if message.get("type") == "error":
                    if frame_id is None and "frameId" in message:
                        continue
                    raise RuntimeError("Panel rejected request")
                if command is not None and message.get("cmd") != command:
                    continue
                if message.get("type") == message_type:
                    return message
            available = getattr(self.ser, "in_waiting", 0)
            # Blocking read(512) waits for the full count even when a short JSON
            # reply is already complete. Wait for one byte, then drain available bytes.
            count = min(512, available) if type(available) is int and available > 0 else 1
            chunk = self.ser.read(count)
            if chunk:
                self._rx.extend(chunk)
                if len(self._rx) > 16384:
                    raise RuntimeError("Panel reply exceeds receive buffer")
        raise TimeoutError(f"{self.name}: no {message_type} reply")


def connect_panel(port_name, views, board_id='guition-p4'):
    panel = Panel(port_name)
    try:
        panel.expected_board = get_board(board_id)
        time.sleep(0.5)
        panel.heartbeat()
        if any(provider not in ('codex', 'zcode') for provider in views) and not panel.provider_selection_supported:
            raise RuntimeError('Update display firmware to v1.11.0+ for additional AI providers.')
        panel.send_line(json.dumps({"cmd": "set_views", "views": views, "mode": "manual",
                                    "interval": 10, "active": 0}))
        panel.wait_for("ok", command="set_views")
        return panel
    except BaseException:
        panel.close()
        raise


class FetchPool:
    """Bounded quota subprocesses: deadlines reap the transport before retrying.

    No credential is placed in an argument, log or file. Workers cannot access
    USB; the calling thread remains its sole owner while pumping heartbeats.
    """
    def __init__(self):
        self.process = None
        self.cleanup_failed = False
        self.request_seconds = 25

    @staticmethod
    def command(provider):
        if provider not in ('codex', 'zcode'): raise ValueError('Unsupported quota worker')
        if getattr(sys, 'frozen', False):
            helper = HERE.parent / 'AI-Monitor-Console.exe'
            if not helper.is_file(): raise FileNotFoundError('Console helper missing')
            return [str(helper), '--quota-worker', provider]
        return [sys.executable, '-u', str(Path(__file__).resolve()), '--quota-worker', provider]

    def close(self):
        if self.process is not None:
            stop_child(self.process)
            self.process = None

    def fetch(self, provider, key, panel):
        if self.cleanup_failed or self.process is not None:
            raise RuntimeError('Previous quota worker cleanup is unconfirmed; retry blocked.')
        started = last_heartbeat = time.monotonic()
        cycle_deadline = getattr(panel, 'cycle_deadline', None)
        deadline = started + self.request_seconds
        if type(cycle_deadline) in (int, float): deadline = min(deadline, cycle_deadline)
        if started >= deadline: return None, f'{provider}: request timed out; retrying'
        try:
            payload = json.dumps({'key':credential(key, optional=True)}).encode() + b'\n'
            if len(payload) > MAX_RESPONSE_BYTES: raise ValueError('Invalid credential length')
        except ValueError as error:
            return None, provider_failure(provider, error)
        environment = dict(os.environ)
        environment['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
        try:
            process = start_child(self.command(provider), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, env=environment,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        except ChildCleanupError:
            self.cleanup_failed=True
            raise
        self.process = process
        replies = queue.Queue(maxsize=1)
        def read():
            try:
                raw = process.stdout.read(MAX_RESPONSE_BYTES + 1)
            except (ValueError, OSError): raw = b''
            replies.put_nowait(raw)
        reader = threading.Thread(target=read, daemon=True, name='aim-quota-output')
        reader.start()
        def write():
            try:
                process.stdin.write(payload)
                process.stdin.close()
            except (OSError, ValueError):
                try: process.stdin.close()
                except (OSError, ValueError): pass
        writer = threading.Thread(target=write, daemon=True, name='aim-quota-input')
        writer.start()
        try:
            while True:
                if time.monotonic() >= deadline:
                    return None, f'{provider}: request timed out; retrying'
                try:
                    raw = replies.get(timeout=0.1)
                except queue.Empty:
                    panel.collect_requests()
                    if isinstance(panel, Panel): panel.report_tokens()
                    now = time.monotonic()
                    if now - last_heartbeat >= HEARTBEAT_SECONDS:
                        panel.heartbeat(); last_heartbeat = now
                    continue
                if len(raw) > MAX_RESPONSE_BYTES or process.poll() not in (None, 0):
                    raise ValueError('Invalid quota worker reply')
                result = json.loads(raw)
                if not isinstance(result, dict) or set(result) != {'rows', 'notice', 'retry_after'}:
                    raise ValueError('Invalid quota worker envelope')
                rows, notice, delay = result['rows'], result['notice'], result['retry_after']
                if rows is not None and not isinstance(rows, list): raise ValueError('Invalid quota rows')
                if notice is not None and not isinstance(notice, str): raise ValueError('Invalid quota notice')
                if type(delay) is not int or not 0 <= delay <= 3600: raise ValueError('Invalid retry delay')
                return rows, ProviderNotice(notice, delay) if notice else None
        except (ValueError, OSError, RecursionError) as error:
            return None, provider_failure(provider, error)
        finally:
            # Never allow a new worker to start until this exact tree is reaped.
            try:
                self.close()
                reader.join(timeout=1)
                writer.join(timeout=1)
                if reader.is_alive() or writer.is_alive(): raise RuntimeError('Quota pipe cleanup failed; retry blocked.')
            except BaseException:
                self.cleanup_failed = True
                raise
            process.stdout.close()
            if not process.stdin.closed: process.stdin.close()


def quota_worker(provider):
    """Internal allowlisted numeric-only worker; never dispatch remote commands."""
    try:
        raw = sys.stdin.buffer.read(MAX_RESPONSE_BYTES + 1)
        if provider not in ('codex', 'zcode') or len(raw) > MAX_RESPONSE_BYTES: return 1
        data = json.loads(raw)
        if not isinstance(data, dict) or set(data) != {'key'}: return 1
        key = credential(data['key'], optional=True)
        rows, notice = fetch_codex() if provider == 'codex' else fetch_zcode(key)
        reply = json.dumps({'rows':rows, 'notice':str(notice) if notice else None,
                            'retry_after':min(3600, max(0, int(getattr(notice, 'retry_after', 0))))}, allow_nan=False)
        if len(reply.encode()) > MAX_RESPONSE_BYTES: return 1
        sys.stdout.write(reply); sys.stdout.flush()
        return 0
    except Exception:
        return 1  # Provider/credential exceptions never leave the private worker.


class ConfigWatcher:
    def __init__(self):
        self.signature = self.fingerprint()
        self.pending = None
        self.failed_signature = None
        self.retry_at = 0

    @staticmethod
    def fingerprint():
        try:
            stat = CONFIG_PATH.stat()
            return stat.st_mtime_ns, stat.st_size
        except OSError:
            return None

    def check(self):
        signature = self.fingerprint()
        if signature == self.signature:
            return
        now = time.monotonic()
        if signature == self.failed_signature and now < self.retry_at:
            return
        self.failed_signature = signature
        self.retry_at = now + 2
        if signature is None:
            LOG("Configuration file unavailable; keeping previous settings")
            return
        try:
            config = load_config()
        except (ValueError, OSError):
            LOG("Configuration reload rejected; keeping previous settings")
            return
        self.pending = config
        self.signature = signature
        self.failed_signature = None
        self.retry_at = 0

    def take(self):
        value, self.pending = self.pending, None
        return value


def wait_connected(panel, seconds, minimum_wait=0):
    from mirror_service import MirrorService
    deadline = time.monotonic() + seconds
    refresh_after = time.monotonic() + minimum_wait
    next_heartbeat = time.monotonic() + HEARTBEAT_SECONDS
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        mirror = getattr(panel, "mirror_service", None)
        capture_active = isinstance(mirror, MirrorService) and mirror.client is not None
        companion=getattr(panel,'companion_service',None)
        pack_active=companion is not None and companion.client is not None and not companion.client.done
        time.sleep(min(.05 if capture_active or pack_active else 1, remaining))
        panel.collect_requests()
        if isinstance(panel, Panel): panel.report_tokens()
        watcher = getattr(panel, "config_watcher", None)
        if isinstance(watcher, ConfigWatcher):
            watcher.check()
            if watcher.pending is not None and time.monotonic() >= refresh_after:
                return
        if type(panel.refresh_request_id) is int and time.monotonic() >= refresh_after:
            return
        if time.monotonic() >= next_heartbeat and time.monotonic() < deadline:
            panel.heartbeat()
            next_heartbeat = time.monotonic() + HEARTBEAT_SECONDS


def frame_payload(provider, view_index, rows, notice=None):
    data0 = {"source": "aim-host", "provider": provider, "fetching": False, "viewIndex": view_index}
    if notice:
        data0["notice"] = notice
    else:
        # The panel shows how much quota is LEFT (the user finds remaining
        # more convenient than used). percentMode "remaining" tells the
        # device the numbers are complements: 95 means 95% left.
        shown = []
        for row in rows[:3]:
            used = percent_value(row["usedPercent"])
            shown.append(dict(row, usedPercent=max(0.0, min(100.0, 100.0 - used)),
                              resetsAt=reset_display(row.get("resetsAt"), row.get("windowMinutes", 0))))
            countdown = reset_seconds(row.get("resetsAt"))
            if countdown is not None:
                shown[-1]["resetSeconds"] = countdown
        data0["usage"] = {"rows": shown, "percentMode": "remaining"}
    envelope = {
        "schemaVersion": 1,
        "frameId": 0,  # replaced by caller
        **clock_fields(),
        "data": [data0],
    }
    return json.dumps(envelope, allow_nan=False)


def run(cfg):
    interval = cfg["interval_s"]
    zai_key = cfg.get("zai_key", "")
    views = selected_providers(cfg)
    if not views:
        raise ValueError('No providers selected. Open First-time setup.')
    get_board(cfg.get('board', 'guition-p4'))

    try:
        _run_loop(cfg, interval, zai_key, views)
    except KeyboardInterrupt:
        LOG("Host stopped")


def _run_loop(cfg, interval, zai_key, views):
    panel = None
    frame_id = 100
    retries = ProviderRetries(interval)
    fetcher = FetchPool()
    watcher = ConfigWatcher()
    health = HostStatus(HERE)
    health.data['board'] = cfg.get('board', '')
    health.update('starting')
    from usage_history import HistoryRecorder
    history = HistoryRecorder(HERE / 'activity', cfg.get('usage_history',False),policy_path=CONFIG_PATH)
    from device_history import HistorySampler
    history_sampler=HistorySampler(HERE/'activity',views,cfg.get('usage_history',False))
    from permission_runtime import PermissionRuntime
    from permission_policy import selected as permission_selected, release_ready
    permissions=PermissionRuntime(HERE.parent,release_ready)
    permissions.configure(permission_selected(cfg))
    tokens = TokenSampler(providers=views, activity_dir=HERE / 'activity', history=history, include_live=False)
    from live_events import LiveSampler
    live_sampler=LiveSampler(HERE/'activity',views)
    from companion_service import CompanionService
    companions=CompanionService(HERE.parent)
    tokens.poll_seconds = cfg.get('token_poll_s', 2)
    try:
        while True:
            watcher.check()
            changed_config = watcher.take()
            if changed_config is not None:
                previous = cfg
                cfg = changed_config
                permissions.configure(permission_selected(cfg))
                history.configure(cfg.get('usage_history',False))
                health.data['board'] = cfg.get('board', '')
                interval = cfg["interval_s"]
                zai_key = cfg.get("zai_key", "")
                changed_views = selected_providers(cfg)
                if not changed_views:
                    LOG('No providers selected; stopping host. Open First-time setup.')
                    return
                history_sampler.configure(cfg.get('usage_history',False),changed_views)
                if changed_views != views:
                    tokens.configure(changed_views)
                    live_sampler.configure(changed_views)
                retries.interval = interval
                tokens.poll_seconds = cfg.get('token_poll_s', 2)
                health.data['providers'] = {key: value for key, value in health.data['providers'].items() if key in changed_views}
                if previous.get("zai_key") != zai_key:
                    retries.succeeded("zcode")
                    # A success from the old credential cannot verify the
                    # newly saved key while its first request is pending.
                    health.data['providers'].pop('zcode', None)
                    health.update()
                if (cfg["port"] != previous["port"] or cfg.get('board') != previous.get('board') or changed_views != views
                        or cfg.get('usb_permissions',False)!=previous.get('usb_permissions',False)):
                    if panel is not None: panel.close()
                    panel = None
                views = changed_views
                LOG("Validated configuration changes applied")
            if panel is None:
                port_name = find_port(cfg["port"], cfg.get('board', 'guition-p4'))
                if not port_name:
                    health.update('waiting_usb', '')
                    LOG('USB selection unresolved. Choose an explicit port if several devices are connected.')
                    wait_for_config(watcher, cfg.get('reconnect_s', 5), tokens if cfg.get('usage_history') else None)
                    continue
                try:
                    health.update('connecting', port_name)
                    panel = connect_panel(port_name, views, cfg.get('board', 'guition-p4'))
                    panel.health = health
                    health.update('connected', port_name)
                    panel.retries = retries
                    panel.fetcher = fetcher
                    panel.config_watcher = watcher
                    panel.token_reporter = tokens
                    panel.live_sampler=live_sampler
                    health.data.pop('live',None)
                    panel.history = history
                    panel.history_sampler=history_sampler
                    from mirror_service import MirrorService
                    panel.mirror_service=MirrorService(HERE.parent)
                    panel.companion_service=companions
                    companions.reconnect()
                    panel.attach_permission_runtime(permissions)
                    health.data.pop('hardware', None)
                    health.data.pop('hardware_at', None)
                    if panel.info.get('hardwareDiagnostics') is True:
                        panel.hardware_pending = True
                        panel.send_line('{"cmd":"get_hardware"}')
                    panel.report_tokens()
                    LOG(f"connected to {port_name}, views={views}")
                except Exception as exc:
                    LOG(f"open {port_name} failed: {type(exc).__name__}")
                    # Handshake can succeed before optional runtime setup or a
                    # diagnostics write fails. Release that owner before retry.
                    if panel is not None:
                        panel.close()
                        panel = None
                    health.update('reconnecting', port_name)
                    wait_for_config(watcher, cfg.get('reconnect_s', 5), tokens if cfg.get('usage_history') else None)
                    continue
            try:
                cycle_started = time.monotonic()
                panel.cycle_deadline = cycle_started + 45
                request_id = panel.take_refresh_request()
                if type(request_id) is not int:
                    request_id = None
                panel.cycle_active = True
                panel.active_refresh_id = request_id
                panel.activity("fetching", "Fetching provider data")
                if request_id is not None:
                    panel.refresh_status(request_id, "updating", "Fetching latest provider data")
                frame_id = poll_cycle(cfg, zai_key, views, frame_id, panel)
                panel.collect_requests()
                panel.cycle_active = False
                panel.activity("updated" if panel.last_poll_success is True else "failed",
                               "Usage status updated" if panel.last_poll_success is True else "Check provider details")
                request_id = panel.active_refresh_id
                if type(request_id) is not int: request_id = None
                if request_id is not None:
                    successful = panel.last_poll_success is True
                    panel.refresh_status(request_id, "complete" if successful else "failed",
                                         "Data updated" if successful else "A provider is unavailable; check its card")
                delay = max(1, interval - (time.monotonic() - cycle_started))
                cooldown = max(0, 15 - (time.monotonic() - cycle_started))
                wait_connected(panel, delay, minimum_wait=cooldown)
            except Exception as exc:
                LOG(f"panel link failed: {type(exc).__name__}; reconnecting")
                panel.close()
                panel = None
                health.update('reconnecting')
                wait_for_config(watcher, cfg.get('reconnect_s', 5), tokens if cfg.get('usage_history') else None)
    finally:
        health.update('stopped')
        tokens.close()
        live_sampler.close()
        history.close()
        history_sampler.close()
        permissions.close()
        fetcher.close()
        if panel is not None:
            panel.close()
        companions.close()


def wait_for_config(watcher, seconds, sampler=None):
    """Apply a saved USB change promptly even while the display is unplugged."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if sampler is not None: sampler.poll()
        time.sleep(min(0.5, max(0, deadline - time.monotonic())))
        watcher.check()
        if watcher.pending is not None: return


def poll_cycle(cfg, zai_key, views, frame_id, panel):
    panel.last_poll_success = True
    if not isinstance(getattr(panel, "retries", None), ProviderRetries):
        panel.retries = ProviderRetries(cfg["interval_s"])
    for idx, provider in enumerate(views):
        informational = False
        deferred = panel.retries.remaining(provider) > 0
        fetcher = getattr(panel, "fetcher", None)
        if provider == 'zcode' and not zai_key:
            rows, notice = None, 'Local token activity; add a Z.AI key for quota'
            informational = True
            panel.retries.succeeded(provider)
        elif deferred:
            rows, notice = None, panel.retries.deferred_notice(provider)
        elif provider == "codex":
            rows, notice = fetcher.fetch(provider, '', panel) if isinstance(fetcher, FetchPool) else fetch_codex()
        elif provider == cfg["zai_provider"] and zai_key:
            callback = lambda: fetch_zcode(zai_key)
            rows, notice = fetcher.fetch(provider, zai_key, panel) if isinstance(fetcher, FetchPool) else callback()
        elif provider not in ('codex', 'zcode'):
            from telemetry_bridge import read_claude_quota, read_counters
            reported = read_claude_quota(HERE / 'activity') if provider == 'claude' else None
            rows = [dict(title=row['title'], usedPercent=percent_value(row['usedPercent']),
                         resetsAt=now_iso_epoch(row['reset_epoch']), windowMinutes=row['windowMinutes']) for row in reported] if reported else None
            notice = None if rows else ('Local token activity; quota bridge optional' if provider == 'claude' else
                                       'Local token activity; quota unavailable' if provider in ('gemini', 'opencode') else
                                       'Numeric telemetry bridge required; see provider guide')
            if not rows and provider not in ('claude', 'gemini', 'opencode') and read_counters(HERE / 'activity', provider) is not None:
                notice = 'External token activity; quota unavailable'
            informational = not rows
        else:
            rows, notice = None, f"{provider} not configured"
        if not rows and not informational:
            panel.last_poll_success = False
            notice = notice or f"{provider} unavailable"
            if not deferred:
                panel.retries.failed(provider, notice)
            LOG(notice)
        # Send every cycle to keep the panel's freshness indication current.
        frame_id = (frame_id % 999999) + 1
        try:
            payload = frame_payload(provider, idx, rows, notice)
        except (ValueError, TypeError, KeyError):
            panel.last_poll_success = False
            notice = f"{provider}: invalid usage data"
            panel.retries.failed(provider, notice)
            payload = frame_payload(provider, idx, None, notice)
        else:
            if rows and not notice:
                panel.retries.succeeded(provider)
        payload = json.loads(payload)
        if informational:
            payload['data'][0]['informational'] = True
        payload["frameId"] = frame_id
        panel.send_frame(json.dumps(payload, allow_nan=False), frame_id)
        panel.wait_for("ack", seconds=2, frame_id=frame_id)
        health = getattr(panel, 'health', None)
        if isinstance(health, HostStatus):
            health.provider(provider, 'activity_only' if informational else 'ready' if rows and not notice else 'unavailable')
        history = getattr(panel, 'history', None)
        if history is not None and rows and not notice: history.record_quota(provider, rows)
        LOG(f"{provider}: frame {frame_id} ACK")
    return frame_id


def main():
    if not acquire_lock():
        LOG("another aim_host instance is already running - exiting")
        return 0
    try:
        try:
            cfg = load_config()
        except (ValueError, OSError) as exc:
            LOG(f"Configuration error: {exc}")
            return 1
        if not cfg['providers']:
            LOG('Choose AI providers in First-time setup before starting the host.')
            return 1
        if not cfg['board']:
            LOG('Choose a display board in First-time setup before starting the host.')
            return 1
        run(cfg)
    finally:
        release_lock()
    return 0


if __name__ == "__main__":
    sys.exit(quota_worker(sys.argv[2]) if len(sys.argv) == 3 and sys.argv[1] == '--quota-worker' else main())
