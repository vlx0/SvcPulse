"""Read and stop Win32 services. Drivers are not included."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import re
from dataclasses import dataclass

from .admin import is_admin

advapi32 = ctypes.windll.advapi32
kernel32 = ctypes.windll.kernel32

SC_MANAGER_CONNECT = 0x0001
SC_MANAGER_ENUMERATE_SERVICE = 0x0004
SERVICE_QUERY_CONFIG = 0x0001
SERVICE_QUERY_STATUS = 0x0004
SERVICE_STOP = 0x0020
SERVICE_WIN32 = 0x00000030
SERVICE_STATE_ALL = 0x00000003
SC_ENUM_PROCESS_INFO = 0
SERVICE_CONFIG_DELAYED_AUTO_START_INFO = 3
SERVICE_CONFIG_TRIGGER_INFO = 8
SERVICE_CONTROL_STOP = 0x00000001

SERVICE_STOPPED = 1
SERVICE_START_PENDING = 2
SERVICE_STOP_PENDING = 3
SERVICE_RUNNING = 4
SERVICE_ACCEPT_STOP = 0x0001

START_BOOT = 0
START_SYSTEM = 1
START_AUTO = 2
START_DEMAND = 3
START_DISABLED = 4

ERROR_MORE_DATA = 234
ERROR_INSUFFICIENT_BUFFER = 122
ERROR_ACCESS_DENIED = 5
ERROR_DEPENDENT_SERVICES_RUNNING = 1051
ERROR_SERVICE_CANNOT_ACCEPT_CTRL = 1061

# Остановка этих служб роняет вход в систему или сеть. Имени достаточно:
# флаг SERVICE_ACCEPT_STOP у части из них всё равно стоит.
NO_STOP = {
    "AppXSvc",
    "BFE",
    "BrokerInfrastructure",
    "camsvc",
    "ClipSVC",
    "CoreMessagingRegistrar",
    "CryptSvc",
    "DcomLaunch",
    "Dhcp",
    "Dnscache",
    "EventLog",
    "gpsvc",
    "KeyIso",
    "Lsa",
    "LSM",
    "mpssvc",
    "nsi",
    "PlugPlay",
    "Power",
    "ProfSvc",
    "RpcSs",
    "SamSs",
    "Schedule",
    "StateRepository",
    "SystemEventsBroker",
    "TextInputManagementService",
    "TokenBroker",
    "UserManager",
    "VaultSvc",
    "Wcmsvc",
    "Winmgmt",
}
NO_STOP_PREFIX = (
    "CDPUserSvc_",
    "OneSyncSvc_",
    "WpnUserService_",
)
_SESSION = re.compile(r"_[0-9a-f]{6,}$", re.I)

_STATE = {
    SERVICE_STOPPED: "стоит",
    SERVICE_START_PENDING: "запускается",
    SERVICE_STOP_PENDING: "останавливается",
    SERVICE_RUNNING: "работает",
    5: "продолжается",
    6: "встаёт на паузу",
    7: "на паузе",
}
_START = {
    START_BOOT: "загрузка",
    START_SYSTEM: "система",
    START_AUTO: "авто",
    START_DEMAND: "вручную",
    START_DISABLED: "отключена",
}


class SERVICE_STATUS_PROCESS(ctypes.Structure):
    _fields_ = [
        ("dwServiceType", wt.DWORD),
        ("dwCurrentState", wt.DWORD),
        ("dwControlsAccepted", wt.DWORD),
        ("dwWin32ExitCode", wt.DWORD),
        ("dwServiceSpecificExitCode", wt.DWORD),
        ("dwCheckPoint", wt.DWORD),
        ("dwWaitHint", wt.DWORD),
        ("dwProcessId", wt.DWORD),
        ("dwServiceFlags", wt.DWORD),
    ]


class ENUM_SERVICE_STATUS_PROCESSW(ctypes.Structure):
    _fields_ = [
        ("lpServiceName", wt.LPWSTR),
        ("lpDisplayName", wt.LPWSTR),
        ("ServiceStatusProcess", SERVICE_STATUS_PROCESS),
    ]


class QUERY_SERVICE_CONFIGW(ctypes.Structure):
    _fields_ = [
        ("dwServiceType", wt.DWORD),
        ("dwStartType", wt.DWORD),
        ("dwErrorControl", wt.DWORD),
        ("lpBinaryPathName", wt.LPWSTR),
        ("lpLoadOrderGroup", wt.LPWSTR),
        ("dwTagId", wt.DWORD),
        ("lpDependencies", wt.LPWSTR),
        ("lpServiceStartName", wt.LPWSTR),
        ("lpDisplayName", wt.LPWSTR),
    ]


class SERVICE_DELAYED_AUTO_START_INFO(ctypes.Structure):
    _fields_ = [("fDelayedAutostart", wt.BOOL)]


advapi32.OpenSCManagerW.argtypes = [wt.LPCWSTR, wt.LPCWSTR, wt.DWORD]
advapi32.OpenSCManagerW.restype = wt.HANDLE
advapi32.OpenServiceW.argtypes = [wt.HANDLE, wt.LPCWSTR, wt.DWORD]
advapi32.OpenServiceW.restype = wt.HANDLE
advapi32.CloseServiceHandle.argtypes = [wt.HANDLE]
advapi32.CloseServiceHandle.restype = wt.BOOL
advapi32.EnumServicesStatusExW.argtypes = [
    wt.HANDLE, wt.DWORD, wt.DWORD, wt.DWORD,
    ctypes.c_void_p, wt.DWORD,
    ctypes.POINTER(wt.DWORD), ctypes.POINTER(wt.DWORD), ctypes.POINTER(wt.DWORD),
    wt.LPCWSTR,
]
advapi32.EnumServicesStatusExW.restype = wt.BOOL
advapi32.QueryServiceConfigW.argtypes = [
    wt.HANDLE, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD),
]
advapi32.QueryServiceConfigW.restype = wt.BOOL
advapi32.QueryServiceConfig2W.argtypes = [
    wt.HANDLE, wt.DWORD, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD),
]
advapi32.QueryServiceConfig2W.restype = wt.BOOL
advapi32.ControlService.argtypes = [wt.HANDLE, wt.DWORD, ctypes.c_void_p]
advapi32.ControlService.restype = wt.BOOL


@dataclass
class Svc:
    name: str
    display: str
    state: int
    start: int
    accept_stop: bool
    delayed: bool = False
    trigger: bool = False
    pid: int = 0

    @property
    def state_text(self) -> str:
        return _STATE.get(self.state, "неизвестно")

    @property
    def start_text(self) -> str:
        text = _START.get(self.start, "неизвестно")
        if self.start == START_AUTO and self.delayed:
            return "авто, отложенный"
        return text


@dataclass
class Snap:
    admin: bool
    auto_stopped: list[Svc]
    manual_running: list[Svc]
    trigger_quiet: int = 0
    session_quiet: int = 0
    error: str = ""


def blocked_name(name: str) -> bool:
    if name in NO_STOP:
        return True
    return any(name.startswith(prefix) for prefix in NO_STOP_PREFIX)


def session_service(name: str) -> bool:
    """Per-user service of this logon, like UserDataSvc_65eea7e."""
    return bool(_SESSION.search(name))


def can_stop(svc: Svc) -> bool:
    return svc.accept_stop and svc.state == SERVICE_RUNNING and not blocked_name(svc.name)


def classify(rows: list[Svc]) -> tuple[list[Svc], list[Svc], int, int]:
    auto: list[Svc] = []
    manual: list[Svc] = []
    quiet = 0
    session = 0
    for svc in rows:
        if svc.start == START_AUTO and svc.state == SERVICE_STOPPED:
            if svc.trigger:
                quiet += 1
            else:
                auto.append(svc)
        elif svc.start == START_DEMAND and svc.state == SERVICE_RUNNING:
            if session_service(svc.name):
                session += 1
            else:
                manual.append(svc)
    auto.sort(key=lambda s: s.display.casefold())
    manual.sort(key=lambda s: s.display.casefold())
    return auto, manual, quiet, session


def sample() -> Snap:
    try:
        rows = list_services()
    except OSError as exc:
        return Snap(is_admin(), [], [], error=str(exc))
    auto, manual, quiet, session = classify(rows)
    return Snap(is_admin(), auto, manual, quiet, session)


def stop_service(name: str) -> str | None:
    if blocked_name(name):
        return "эту службу останавливать нельзя"
    if not is_admin():
        return "нужны права администратора"
    scm = advapi32.OpenSCManagerW(None, None, SC_MANAGER_CONNECT)
    if not scm:
        return _winerr(kernel32.GetLastError())
    handle = None
    try:
        handle = advapi32.OpenServiceW(scm, name, SERVICE_STOP | SERVICE_QUERY_STATUS)
        if not handle:
            return _winerr(kernel32.GetLastError())
        status = SERVICE_STATUS_PROCESS()
        if not advapi32.ControlService(handle, SERVICE_CONTROL_STOP, ctypes.byref(status)):
            return _winerr(kernel32.GetLastError())
        return None
    finally:
        if handle:
            advapi32.CloseServiceHandle(handle)
        advapi32.CloseServiceHandle(scm)


def list_services() -> list[Svc]:
    scm = advapi32.OpenSCManagerW(None, None, SC_MANAGER_CONNECT | SC_MANAGER_ENUMERATE_SERVICE)
    if not scm:
        raise OSError(_winerr(kernel32.GetLastError()) or "диспетчер служб не открылся")
    try:
        raw = _enum(scm)
        out: list[Svc] = []
        for name, display, status in raw:
            start, delayed, trigger = _config(scm, name, status.dwCurrentState)
            if start is None:
                continue
            out.append(Svc(
                name=name,
                display=display or name,
                state=int(status.dwCurrentState),
                start=start,
                accept_stop=bool(status.dwControlsAccepted & SERVICE_ACCEPT_STOP),
                delayed=delayed,
                trigger=trigger,
                pid=int(status.dwProcessId),
            ))
        return out
    finally:
        advapi32.CloseServiceHandle(scm)


def _enum(scm) -> list[tuple[str, str, SERVICE_STATUS_PROCESS]]:
    needed = wt.DWORD(0)
    count = wt.DWORD(0)
    resume = wt.DWORD(0)
    size = 64 * 1024
    out: list[tuple[str, str, SERVICE_STATUS_PROCESS]] = []
    while True:
        buf = ctypes.create_string_buffer(size)
        ok = advapi32.EnumServicesStatusExW(
            scm, SC_ENUM_PROCESS_INFO, SERVICE_WIN32, SERVICE_STATE_ALL,
            buf, size, ctypes.byref(needed), ctypes.byref(count), ctypes.byref(resume), None,
        )
        err = kernel32.GetLastError()
        if not ok and err == ERROR_MORE_DATA:
            size = max(size * 2, int(needed.value) + 4096)
            resume = wt.DWORD(0)
            continue
        if not ok:
            raise OSError(_winerr(err) or "список служб не прочитался")
        items = ctypes.cast(buf, ctypes.POINTER(ENUM_SERVICE_STATUS_PROCESSW))
        for i in range(int(count.value)):
            item = items[i]
            status = SERVICE_STATUS_PROCESS()
            ctypes.memmove(ctypes.byref(status), ctypes.byref(item.ServiceStatusProcess), ctypes.sizeof(status))
            out.append((item.lpServiceName or "", item.lpDisplayName or "", status))
        if resume.value == 0:
            return out


def _config(scm, name: str, state: int) -> tuple[int | None, bool, bool]:
    handle = advapi32.OpenServiceW(scm, name, SERVICE_QUERY_CONFIG)
    if not handle:
        return None, False, False
    try:
        needed = wt.DWORD(0)
        advapi32.QueryServiceConfigW(handle, None, 0, ctypes.byref(needed))
        if kernel32.GetLastError() != ERROR_INSUFFICIENT_BUFFER or needed.value == 0:
            return None, False, False
        buf = ctypes.create_string_buffer(int(needed.value))
        if not advapi32.QueryServiceConfigW(handle, buf, needed.value, ctypes.byref(needed)):
            return None, False, False
        cfg = ctypes.cast(buf, ctypes.POINTER(QUERY_SERVICE_CONFIGW)).contents
        start = int(cfg.dwStartType)
        delayed = False
        trigger = False
        if start == START_AUTO:
            delayed = _delayed(handle)
            if state == SERVICE_STOPPED:
                trigger = _has_trigger(handle)
        return start, delayed, trigger
    finally:
        advapi32.CloseServiceHandle(handle)


def _delayed(handle) -> bool:
    info = SERVICE_DELAYED_AUTO_START_INFO()
    needed = wt.DWORD(0)
    if not advapi32.QueryServiceConfig2W(
        handle, SERVICE_CONFIG_DELAYED_AUTO_START_INFO,
        ctypes.byref(info), ctypes.sizeof(info), ctypes.byref(needed),
    ):
        return False
    return bool(info.fDelayedAutostart)


def _has_trigger(handle) -> bool:
    needed = wt.DWORD(0)
    advapi32.QueryServiceConfig2W(handle, SERVICE_CONFIG_TRIGGER_INFO, None, 0, ctypes.byref(needed))
    if needed.value < 4:
        return False
    buf = ctypes.create_string_buffer(int(needed.value))
    if not advapi32.QueryServiceConfig2W(
        handle, SERVICE_CONFIG_TRIGGER_INFO, buf, needed.value, ctypes.byref(needed),
    ):
        return False
    return int(ctypes.cast(buf, ctypes.POINTER(wt.DWORD)).contents.value) > 0


def _winerr(code: int) -> str:
    known = {
        ERROR_ACCESS_DENIED: "нужны права администратора",
        ERROR_DEPENDENT_SERVICES_RUNNING: "её держат другие службы",
        ERROR_SERVICE_CANNOT_ACCEPT_CTRL: "служба сейчас не принимает остановку",
    }
    if code in known:
        return known[code]
    if not code:
        return "не вышло"
    buf = ctypes.create_unicode_buffer(512)
    kernel32.FormatMessageW(
        0x00001000 | 0x00000200, None, code, 0, buf, len(buf), None,
    )
    text = buf.value.strip().rstrip(".")
    return text or f"ошибка {code}"
