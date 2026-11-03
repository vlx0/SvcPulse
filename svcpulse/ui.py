"""SvcPulse GUI."""

from __future__ import annotations

import ctypes
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from . import __version__
from .admin import relaunch_as_admin
from .instance import WINDOW_TITLE
from .settings import INTERVALS, load_interval, save_interval
from .svc import Snap, Svc, can_stop, sample, stop_service

BG = "#111111"
FG = "#ffffff"
MUTED = "#999999"
CARD = "#1a1a1a"
BTN = "#333333"
ACCENT = "#93c5fd"
OK = "#86efac"
HOT = "#fde68a"
BAD = "#fca5a5"


def _headline(snap: Snap) -> tuple[str, str]:
    if snap.error:
        return snap.error, BAD
    auto = len(snap.auto_stopped)
    manual = len(snap.manual_running)
    if auto:
        return f"Авто и стоят: {auto}. Вручную работают: {manual}.", HOT
    if manual:
        return f"Автозапуск на месте. Вручную работают: {manual}.", ACCENT
    return "Странных служб нет.", OK


def _quiet(snap: Snap) -> str:
    parts: list[str] = []
    if snap.trigger_quiet:
        parts.append(f"По событию и молчат: {snap.trigger_quiet}. Так и задумано.")
    if snap.session_quiet:
        parts.append(f"Службы сеанса: {snap.session_quiet}. Они и должны работать.")
    return " ".join(parts)


class SvcPulseApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(WINDOW_TITLE)
        self.geometry("560x640")
        self.minsize(460, 420)
        self.configure(bg=BG)
        self._sec = load_interval()
        self._job: str | None = None
        self._busy = False
        self._asking = False
        self._sig: tuple | None = None
        self._admin_shown = False

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Dark.TCombobox",
            fieldbackground=CARD, background=BTN, foreground=FG, arrowcolor=FG,
            darkcolor=CARD, lightcolor=CARD, bordercolor=BTN,
        )
        style.map(
            "Dark.TCombobox",
            fieldbackground=[("readonly", CARD)],
            foreground=[("readonly", FG)],
            background=[("readonly", BTN)],
        )

        pad = tk.Frame(self, bg=BG)
        pad.pack(fill="both", expand=True, padx=22, pady=16)

        foot = tk.Frame(pad, bg=BG)
        foot.pack(fill="x", side="bottom", pady=(8, 0))
        tk.Label(foot, text="неделя 11 · день 72", bg=BG, fg=MUTED, font=("Segoe UI", 8)).pack(side="left")
        tk.Label(foot, text=f"v{__version__} · darkshade", bg=BG, fg=MUTED, font=("Segoe UI", 8)).pack(side="right")
        labels = [lab for _, lab in INTERVALS]
        self._iv_var = tk.StringVar(value=next((lab for sec, lab in INTERVALS if sec == self._sec), "5 с"))
        self._iv = ttk.Combobox(
            foot, textvariable=self._iv_var, values=labels, state="readonly",
            width=6, style="Dark.TCombobox", font=("Segoe UI", 8),
        )
        self._iv.pack(side="right", padx=(0, 10))
        self._iv.bind("<<ComboboxSelected>>", lambda _e: self._on_interval())
        tk.Label(foot, text="обновление", bg=BG, fg=MUTED, font=("Segoe UI", 8)).pack(side="right", padx=(0, 6))

        self._note = tk.Label(
            pad,
            text="Драйверы ядра не показываю. Остановка спрашивает подтверждение.",
            bg=BG, fg=MUTED, font=("Segoe UI", 8),
            wraplength=500, justify="left",
        )
        self._note.pack(fill="x", side="bottom", pady=(6, 0))

        head = tk.Frame(pad, bg=BG)
        head.pack(fill="x")
        tk.Label(head, text="SvcPulse", bg=BG, fg=FG, font=("Segoe UI Semibold", 20)).pack(side="left")

        self._status = tk.Label(
            pad, text="читаю…", bg=BG, fg=FG, font=("Segoe UI", 12),
            wraplength=500, justify="left",
        )
        self._status.pack(anchor="w", pady=(8, 2))

        self._ctx = tk.Label(
            pad, text="", bg=BG, fg=MUTED, font=("Segoe UI", 9),
            wraplength=500, justify="left",
        )
        self._ctx.pack(anchor="w", pady=(0, 8))

        self._admin = tk.Button(
            pad, text="Остановка — от администратора", command=self._elevate,
            bg=CARD, fg=FG, relief="flat", bd=0, cursor="hand2",
            font=("Segoe UI", 10), activebackground=BTN, activeforeground=FG,
            padx=12, pady=8,
        )

        self._canvas = tk.Canvas(pad, bg=BG, highlightthickness=0, bd=0)
        self._canvas.pack(fill="both", expand=True)
        self._list = tk.Frame(self._canvas, bg=BG)
        self._win = self._canvas.create_window((0, 0), window=self._list, anchor="nw")
        self._canvas.bind("<Configure>", self._on_canvas)
        self._list.bind("<Configure>", lambda _e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self.bind_all("<MouseWheel>", self._wheel)

        self.bind("<Configure>", self._on_resize)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(20, self._place)
        self._job = self.after(150, self._tick)

    def _on_canvas(self, event: tk.Event) -> None:
        self._canvas.itemconfigure(self._win, width=event.width)

    def _wheel(self, event: tk.Event) -> None:
        if self._asking:
            return
        self._canvas.yview_scroll(int(-event.delta / 120), "units")

    def _on_interval(self) -> None:
        lab = self._iv_var.get()
        for sec, name in INTERVALS:
            if name == lab:
                self._sec = sec
                save_interval(sec)
                self._schedule(0)
                return

    def _on_resize(self, event: tk.Event) -> None:
        if event.widget is not self:
            return
        width = max(280, event.width - 48)
        self._status.configure(wraplength=width)
        self._ctx.configure(wraplength=width)
        self._note.configure(wraplength=width)

    def _place(self) -> None:
        self.update_idletasks()
        w, h = self.winfo_width() or 560, self.winfo_height() or 640
        sw = ctypes.windll.user32.GetSystemMetrics(0)
        sh = ctypes.windll.user32.GetSystemMetrics(1)
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 6}")

    def _alive(self) -> bool:
        try:
            return bool(self.winfo_exists())
        except tk.TclError:
            return False

    def _close(self) -> None:
        if self._job:
            try:
                self.after_cancel(self._job)
            except tk.TclError:
                pass
        self.destroy()

    def _schedule(self, delay_ms: int | None = None) -> None:
        if self._job:
            try:
                self.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None
        ms = int(self._sec * 1000) if delay_ms is None else delay_ms
        self._job = self.after(max(0, ms), self._tick)

    def _elevate(self) -> None:
        try:
            relaunch_as_admin()
        except OSError as exc:
            self._status.configure(text=str(exc), fg=BAD)

    def _tick(self) -> None:
        if not self._alive() or self._asking:
            self._schedule()
            return
        if self._busy:
            self._schedule()
            return
        self._busy = True
        threading.Thread(target=self._work, daemon=True).start()

    def _work(self) -> None:
        try:
            snap = sample()
        except Exception:
            snap = Snap(False, [], [], error="Не удалось прочитать службы.")
        try:
            self.after(0, lambda s=snap: self._apply(s))
        except tk.TclError:
            pass

    def _apply(self, snap: Snap) -> None:
        self._busy = False
        if not self._alive():
            return
        text, color = _headline(snap)
        self._status.configure(text=text, fg=color)
        self._ctx.configure(text=_quiet(snap))
        if snap.admin:
            if self._admin_shown:
                self._admin.pack_forget()
                self._admin_shown = False
        elif not self._admin_shown:
            self._admin.pack(fill="x", pady=(0, 10), before=self._canvas)
            self._admin_shown = True
        sig = (
            snap.admin,
            snap.error,
            snap.trigger_quiet,
            snap.session_quiet,
            tuple((s.name, s.display, s.state, s.start, s.delayed, s.accept_stop) for s in snap.auto_stopped),
            tuple((s.name, s.display, s.state, s.start, s.accept_stop) for s in snap.manual_running),
        )
        if sig != self._sig:
            self._sig = sig
            self._render(snap)
        self._schedule()

    def _render(self, snap: Snap) -> None:
        for child in self._list.winfo_children():
            child.destroy()
        if snap.error and not snap.auto_stopped and not snap.manual_running:
            self._muted(snap.error)
            return
        self._section("Авто и стоят", snap.auto_stopped, "Таких нет.", snap.admin)
        self._section("Запущены вручную", snap.manual_running, "Таких нет.", snap.admin)

    def _section(self, title: str, rows: list[Svc], empty: str, admin: bool) -> None:
        tk.Label(self._list, text=title, bg=BG, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", pady=(8, 4))
        if not rows:
            self._muted(empty)
            return
        for svc in rows:
            self._card(svc, admin)

    def _muted(self, text: str) -> None:
        tk.Label(
            self._list, text=text, bg=BG, fg=MUTED, font=("Segoe UI", 10),
            wraplength=480, justify="left",
        ).pack(anchor="w", pady=(0, 4))

    def _card(self, svc: Svc, admin: bool) -> None:
        box = tk.Frame(self._list, bg=CARD)
        box.pack(fill="x", pady=(0, 8))
        inner = tk.Frame(box, bg=CARD)
        inner.pack(fill="x", padx=12, pady=10)
        top = tk.Frame(inner, bg=CARD)
        top.pack(fill="x")
        if admin and can_stop(svc):
            tk.Button(
                top, text="Остановить", command=lambda name=svc.name, title=svc.display: self._stop(name, title),
                bg=BTN, fg=FG, relief="flat", bd=0, cursor="hand2",
                font=("Segoe UI", 8), activebackground=CARD, activeforeground=FG,
                padx=8, pady=4,
            ).pack(side="right", padx=(8, 0))
        tk.Label(
            top, text=svc.display, bg=CARD, fg=FG, font=("Segoe UI Semibold", 11),
            wraplength=340, justify="left", anchor="w",
        ).pack(side="left", fill="x", expand=True)
        meta = svc.start_text + " · " + svc.state_text
        if svc.display != svc.name:
            meta = svc.name + " · " + meta
        tk.Label(
            inner, text=meta, bg=CARD, fg=MUTED, font=("Segoe UI", 8),
            wraplength=460, justify="left", anchor="w",
        ).pack(fill="x", anchor="w", pady=(4, 0))

    def _stop(self, name: str, title: str) -> None:
        self._asking = True
        try:
            ok = messagebox.askyesno(WINDOW_TITLE, f"Остановить «{title}»?", parent=self)
        finally:
            self._asking = False
        if not ok:
            return
        err = stop_service(name)
        if err:
            self._status.configure(text=err, fg=BAD)
            return
        self._sig = None
        self._schedule(400)


def run() -> None:
    SvcPulseApp().mainloop()
