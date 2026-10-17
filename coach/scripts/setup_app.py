#!/usr/bin/env python3
"""The Prompt Coach setup program (built into PromptCoachSetup.exe).

Double-click it: one window, one Install button. It installs the coach (no
Python needed), connects it to the Claude desktop app's chat and Cowork, adds it
to the Code tab, and reopens Claude. The steps themselves are in installer.py.

For testing and for IT departments it also runs without a window:

    PromptCoachSetup.exe --silent [--close-claude] [--log FILE]
        [--install-dir DIR] [--claude-config FILE] [--claude-home DIR] [--claude-cli FILE]
        [--no-chat] [--no-code] [--no-shortcuts] [--no-registry] [--no-reopen]
    PromptCoachSetup.exe --silent --uninstall [...]
"""

import argparse
import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import installer  # noqa: E402
from pcoach import __version__  # noqa: E402

INK, MUTED, ACCENT, PAPER, LINE = "#1d1d1f", "#6e6e73", "#2b59c3", "#ffffff", "#e5e5ea"
GOOD, WARN, BAD = "#1f7a4d", "#8a6d1a", "#b3261e"
MARK = {installer.OK: ("✓", GOOD), installer.SKIPPED: ("–", WARN), installer.FAILED: ("✕", BAD)}


def bundled_payload():
    base = getattr(sys, "_MEIPASS", None)
    return os.path.join(base, "payload.zip") if base else None


def default_log():
    return os.path.join(tempfile.gettempdir(), "PromptCoachSetup.log")


class Log:
    def __init__(self, path, echo=False):
        self.path, self.echo = path, echo
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("Prompt Coach setup %s, %s\n" % (__version__, time.strftime("%Y-%m-%d %H:%M:%S")))
        except OSError:
            self.path = None

    def __call__(self, text):
        if self.path:
            try:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(text + "\n")
            except OSError:
                pass
        if self.echo and sys.stdout is not None:
            try:
                print(text)
                sys.stdout.flush()
            except (OSError, ValueError):
                pass


def parse(argv):
    ap = argparse.ArgumentParser(prog="PromptCoachSetup", description="Install Prompt Coach for Claude.")
    ap.add_argument("--silent", action="store_true", help="no window")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--close-claude", action="store_true", help="with --silent: quit Claude if it is running")
    ap.add_argument("--delete-data", action="store_true", help="with --uninstall: also delete scores and history")
    ap.add_argument("--payload")
    ap.add_argument("--install-dir")
    ap.add_argument("--claude-config")
    ap.add_argument("--claude-home")
    ap.add_argument("--claude-cli")
    ap.add_argument("--no-chat", action="store_true")
    ap.add_argument("--no-code", action="store_true")
    ap.add_argument("--no-shortcuts", action="store_true")
    ap.add_argument("--no-registry", action="store_true")
    ap.add_argument("--no-reopen", action="store_true")
    ap.add_argument("--log")
    ap.add_argument("--selftest-gui", action="store_true", help=argparse.SUPPRESS)
    return ap.parse_args(argv)


def options(args):
    kw = {"payload": args.payload or bundled_payload(), "chat": not args.no_chat, "code": not args.no_code,
          "shortcuts": not args.no_shortcuts, "registry": not args.no_registry, "reopen": not args.no_reopen}
    for name in ("install_dir", "claude_config", "claude_home", "claude_cli"):
        value = getattr(args, name)
        if value:
            kw[name] = os.path.abspath(value)
    return installer.Options(**kw)


def summary(result, uninstalling=False):
    """(headline, plain-language lines) for the last page."""
    if not result.ok:
        return ("Setup didn't finish" if not uninstalling else "Prompt Coach could not be removed completely",
                ["%s: %s" % (s, d) for s, st, d in result.steps if st == installer.FAILED])
    if uninstalling:
        return "Prompt Coach was removed", ["Your scores and history were kept."]
    lines = []
    if result.status("Connect Claude chat and Cowork") == installer.OK:
        lines.append("Chat and Cowork: connected. Start a new chat and choose Always allow when Claude asks.")
    code = result.status("Add to the Code tab")
    if code == installer.OK:
        lines.append("Code tab: added. It starts by itself in every new session.")
    elif code == installer.SKIPPED:
        lines.append("Code tab: %s." % next(d for s, _st, d in result.steps if s == "Add to the Code tab"))
    return "Prompt Coach is installed", lines


# --- the window ---------------------------------------------------------------------------------

class Window:
    def __init__(self, opts, log, uninstalling=False):
        import tkinter as tk
        from tkinter import font as tkfont
        self.tk, self.opts, self.log, self.uninstalling = tk, opts, log, uninstalling
        self.result = None
        root = self.root = tk.Tk()
        root.title("Prompt Coach Setup")
        root.configure(bg=PAPER)
        root.resizable(False, False)
        w, h = 600, 470
        root.geometry("%dx%d+%d+%d" % (w, h, (root.winfo_screenwidth() - w) // 2,
                                       max(40, (root.winfo_screenheight() - h) // 3)))
        base = "Segoe UI" if "Segoe UI" in tkfont.families() else "TkDefaultFont"
        self.f_title = (base, 20, "bold")
        self.f_body = (base, 11)
        self.f_small = (base, 9)
        self.f_button = (base, 11, "bold")
        self.page = None
        self.welcome()

    # -- building blocks
    def fresh(self):
        if self.page is not None:
            self.page.destroy()
        self.page = self.tk.Frame(self.root, bg=PAPER, padx=36, pady=28)
        self.page.pack(fill="both", expand=True)
        return self.page

    def label(self, parent, text, font=None, color=INK, **pack):
        lab = self.tk.Label(parent, text=text, font=font or self.f_body, fg=color, bg=PAPER, justify="left",
                            anchor="w", wraplength=528)
        lab.pack(fill="x", **pack)
        return lab

    def button(self, parent, text, command, primary=True):
        b = self.tk.Button(parent, text=text, command=command, font=self.f_button, relief="flat", cursor="hand2",
                           padx=22, pady=8, bd=0,
                           bg=ACCENT if primary else "#eef1f8", fg="#ffffff" if primary else ACCENT,
                           activebackground="#21479c" if primary else "#dfe5f3",
                           activeforeground="#ffffff" if primary else ACCENT)
        return b

    # -- pages
    def welcome(self):
        p = self.fresh()
        if self.uninstalling:
            self.label(p, "Remove Prompt Coach", self.f_title)
            self.label(p, "This removes Prompt Coach from Claude and from this computer. Your scores and history "
                          "are kept, so you can pick up where you left off if you install it again.", pady=(14, 0))
        else:
            self.label(p, "Prompt Coach", self.f_title)
            self.label(p, "Your AI coach, inside Claude.", color=MUTED, pady=(2, 0))
            self.label(p, "It asks the right question at the right moment so you get better results from AI, and "
                          "shows your progress over time.", pady=(16, 0))
            self.label(p, "Setup will:", pady=(16, 4))
            for line in ("Install the coach on this computer (nothing else to download)",
                         "Connect it to the Claude app: Chat, Cowork and the Code tab",
                         "Close and reopen Claude to switch it on (your chats are saved)"):
                self.label(p, "   •  " + line)
        self.label(p, "Everything stays on this computer. Nothing you type is stored or sent anywhere by "
                      "Prompt Coach.", self.f_small, MUTED, pady=(18, 0))
        bar = self.tk.Frame(p, bg=PAPER)
        bar.pack(side="bottom", fill="x")
        self.label(bar, "Version %s" % __version__, self.f_small, MUTED, side="left")
        self.go = self.button(bar, "Remove" if self.uninstalling else "Install", self.start)
        self.go.pack(side="right")
        self.button(bar, "Cancel", self.root.destroy, primary=False).pack(side="right", padx=(0, 10))

    def start(self):
        from tkinter import messagebox
        close = None
        if self.opts.real_claude and installer.claude_running():
            if not messagebox.askyesno("Prompt Coach Setup", "Claude is open and needs to close to finish.\n\n"
                                       "Close Claude now? Your chats are saved, and setup reopens it afterwards.",
                                       parent=self.root):
                return
            close = installer.close_claude
        self.progress()
        threading.Thread(target=self.work, args=(close,), daemon=True).start()

    def progress(self):
        p = self.fresh()
        self.label(p, "Removing Prompt Coach..." if self.uninstalling else "Installing Prompt Coach...", self.f_title)
        self.label(p, "This takes about a minute. Claude will reopen by itself.", color=MUTED, pady=(4, 14))
        self.rows = self.tk.Frame(p, bg=PAPER)
        self.rows.pack(fill="x")
        self.now = self.label(p, "Working...", color=MUTED, pady=(10, 0))

    def work(self, close):
        def out(text):
            self.log(text)
            self.root.after(0, self.show_step, text)
        try:
            if self.uninstalling:
                self.result = installer.uninstall(self.opts, out=out, close=close)
            else:
                self.result = installer.run(self.opts, out=out, close=close)
        except Exception as exc:  # noqa: BLE001  (show it; never a silent crash)
            self.result = installer.Result(out)
            self.result.add("Setup", installer.FAILED, "%s: %s" % (type(exc).__name__, exc))
        self.root.after(0, self.done)

    def show_step(self, text):
        step, _, rest = text.partition(": ")
        status = rest.split(" ", 1)[0]
        mark, color = MARK.get(status, ("•", MUTED))
        row = self.tk.Frame(self.rows, bg=PAPER)
        row.pack(fill="x", pady=2)
        self.tk.Label(row, text=mark, fg=color, bg=PAPER, font=self.f_button, width=2).pack(side="left")
        self.tk.Label(row, text=step, fg=INK, bg=PAPER, font=self.f_body, anchor="w").pack(side="left")

    def done(self):
        p = self.fresh()
        head, lines = summary(self.result, self.uninstalling)
        self.label(p, head, self.f_title, GOOD if self.result.ok else BAD)
        for line in lines:
            self.label(p, line, pady=(8, 0))
        bar = self.tk.Frame(p, bg=PAPER)
        bar.pack(side="bottom", fill="x")
        self.button(bar, "Finish", self.root.destroy).pack(side="right")
        if not self.result.ok:
            self.label(p, "Details were saved to %s" % (self.log.path or "(no log)"), self.f_small, MUTED,
                       pady=(14, 0))
            return
        if self.uninstalling:
            return
        self.button(bar, "Open my dashboard", self.dashboard, primary=False).pack(side="right", padx=(0, 10))
        box = self.tk.Frame(p, bg="#f5f7fb", padx=14, pady=12, highlightbackground=LINE, highlightthickness=1)
        box.pack(fill="x", pady=(18, 0))
        self.tk.Label(box, text="One last step, so the coach starts by itself in every chat", font=self.f_button,
                      fg=INK, bg="#f5f7fb", anchor="w").pack(fill="x")
        self.tk.Label(box, text="In Claude, click your name (bottom left) > Settings > Account. Paste this line "
                                "into the box called \"Instructions for Claude\" and save.", font=self.f_small,
                      fg=MUTED, bg="#f5f7fb", anchor="w", justify="left", wraplength=496).pack(fill="x", pady=(2, 8))
        line = self.tk.Text(box, height=3, wrap="word", font=self.f_small, fg=INK, bg=PAPER, relief="flat",
                            highlightbackground=LINE, highlightthickness=1, padx=8, pady=6)
        line.insert("1.0", installer.PREFERENCE_LINE)
        line.configure(state="disabled")
        line.pack(fill="x")
        self.copy = self.button(box, "Copy the line", self.copy_line, primary=False)
        self.copy.configure(font=self.f_small, padx=12, pady=4)
        self.copy.pack(anchor="e", pady=(8, 0))

    def copy_line(self):
        try:
            put_on_clipboard(installer.PREFERENCE_LINE, self.root)
        except OSError as exc:
            self.log("copy: %s" % exc)
            self.copy.configure(text="Couldn't copy: select the line and press Ctrl+C")
            return
        self.copy.configure(text="Copied")

    def dashboard(self):
        import subprocess
        exe = os.path.join(self.opts.install_dir, "coachw.exe")
        try:
            subprocess.Popen([exe, "dashboard"], cwd=self.opts.install_dir)
        except OSError as exc:
            self.log("dashboard: %s" % exc)


def put_on_clipboard(text, root):
    """Put text on the clipboard so it is still there after this window closes.

    Tk only promises the text to Windows and hands it over when a program asks; once the setup
    window is gone nothing answers, and pasting gives nothing. So on Windows the text is handed
    over right away, through Windows itself."""
    if sys.platform != "win32":
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        return
    import ctypes
    from ctypes import wintypes
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    CF_UNICODETEXT, GMEM_MOVEABLE = 13, 0x0002
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    data = text.encode("utf-16-le") + b"\0\0"
    for _ in range(20):                      # another program may be holding the clipboard for a moment
        if user32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        raise OSError("the clipboard is busy")
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not handle:
            raise OSError("out of memory")
        ctypes.memmove(kernel32.GlobalLock(handle), data, len(data))
        kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            kernel32.GlobalFree(handle)
            raise OSError("Windows refused the text")
    finally:
        user32.CloseClipboard()


def selftest_gui(opts, log):
    """Build every page without showing a window for long; proves the window code runs on this computer."""
    win = Window(opts, log)
    pause = float(os.environ.get("PROMPT_COACH_SELFTEST_PAUSE", "0") or 0)     # seconds per page, for screenshots

    def show():
        end = time.time() + pause
        win.root.update()
        while time.time() < end:
            win.root.update()
            time.sleep(0.05)

    win.root.title("Prompt Coach Setup (welcome)" if pause else win.root.title())
    show()
    win.progress()
    for text in ("Install the coach: ok (x)", "Connect Claude chat and Cowork: ok", "Add to the Code tab: skipped (y)"):
        win.show_step(text)
    win.root.title("Prompt Coach Setup (progress)" if pause else win.root.title())
    show()
    r = installer.Result()
    r.add("Install the coach", installer.OK)
    r.add("Connect Claude chat and Cowork", installer.OK)
    r.add("Add to the Code tab", installer.SKIPPED, "Claude Code isn't on this computer yet")
    win.result = r
    win.done()
    win.root.title("Prompt Coach Setup (done)" if pause else win.root.title())
    show()
    win.copy_line()
    copied = win.root.clipboard_get() == installer.PREFERENCE_LINE
    bad = installer.Result()
    bad.add("Install the coach", installer.FAILED, "files are in use")
    win.result = bad
    win.done()
    win.root.update()
    win.root.destroy()
    log("selftest-gui: %s" % ("ok" if copied else "clipboard failed"))
    return 0 if copied else 1


def main(argv=None):
    args = parse(sys.argv[1:] if argv is None else argv)
    log = Log(args.log or default_log(), echo=args.silent)
    opts = options(args)
    if args.selftest_gui:
        return selftest_gui(opts, log)
    if args.silent:
        close = installer.close_claude if args.close_claude else None
        if args.uninstall:
            result = installer.uninstall(opts, out=log, close=close, delete_data=args.delete_data)
        else:
            result = installer.run(opts, out=log, close=close)
        head, lines = summary(result, args.uninstall)
        log(head)
        for line in lines:
            log("  " + line)
        return 0 if result.ok else 1
    Window(opts, log, uninstalling=args.uninstall).root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
