import sys
import subprocess
import os
import json
import plistlib
import threading
import rumps

# --- CONFIGURATION ---
CONFIG_FILE = os.path.expanduser("~/.shiftscroll_config.json")
LOGIN_AGENT_LABEL = "com.vominhduc.shiftscroll"
LOGIN_AGENT_FILE = os.path.expanduser(f"~/Library/LaunchAgents/{LOGIN_AGENT_LABEL}.plist")
INSTANCE_LOCK_FILE = os.path.expanduser("~/.shiftscroll.lock")
MENU_BAR_ICON_FILE = os.path.expanduser("~/.shiftscroll_menubar_icon.png")
SCROLL_STEP_MIN = 1
SCROLL_STEP_MAX = 12
_INSTANCE_LOCK_HANDLE = None

# Default settings matching the UI
DEFAULT_CONFIG = {
    "enabled": True,
    "start_at_login": False,
    "rev_vert": True,
    "rev_horiz": False,
    "apply_trackpad": False,
    "apply_mouse": True,
    "step_size": 2,
}
# ---------------------


def normalize_step_size(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = DEFAULT_CONFIG["step_size"]
    return max(SCROLL_STEP_MIN, min(SCROLL_STEP_MAX, value))


def hide_from_dock():
    if sys.platform != "darwin":
        return

    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory

        NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyAccessory
        )
    except Exception:
        pass


def acquire_single_instance_lock():
    global _INSTANCE_LOCK_HANDLE

    if sys.platform != "darwin":
        return True

    try:
        import fcntl

        _INSTANCE_LOCK_HANDLE = open(INSTANCE_LOCK_FILE, "w")
        fcntl.flock(_INSTANCE_LOCK_HANDLE, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _INSTANCE_LOCK_HANDLE.seek(0)
        _INSTANCE_LOCK_HANDLE.truncate()
        _INSTANCE_LOCK_HANDLE.write(str(os.getpid()))
        _INSTANCE_LOCK_HANDLE.flush()
        return True
    except OSError:
        return False


def find_app_bundle_path():
    marker = ".app/Contents/MacOS"

    for candidate in (sys.argv[0], sys.executable):
        if not candidate:
            continue

        candidate = os.path.abspath(candidate)
        marker_index = candidate.find(marker)
        if marker_index != -1:
            return candidate[: marker_index + len(".app")]

    return None


def login_item_arguments():
    app_bundle_path = find_app_bundle_path()
    if app_bundle_path:
        return ["/usr/bin/open", "-g", "-j", app_bundle_path]

    script_path = os.path.abspath(__file__)
    return [sys.executable, script_path]


def is_start_at_login_enabled():
    if not os.path.exists(LOGIN_AGENT_FILE):
        return False

    try:
        with open(LOGIN_AGENT_FILE, "rb") as f:
            login_agent = plistlib.load(f)
    except (OSError, plistlib.InvalidFileException):
        return True

    return login_agent.get("Label") == LOGIN_AGENT_LABEL


def unload_login_agent():
    if sys.platform != "darwin":
        return

    gui_domain = f"gui/{os.getuid()}"
    for command in (
        ["launchctl", "bootout", gui_domain, LOGIN_AGENT_FILE],
        ["launchctl", "unload", LOGIN_AGENT_FILE],
    ):
        subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )


def set_start_at_login(enabled):
    if enabled:
        os.makedirs(os.path.dirname(LOGIN_AGENT_FILE), exist_ok=True)

        login_agent = {
            "Label": LOGIN_AGENT_LABEL,
            "ProgramArguments": login_item_arguments(),
            "RunAtLoad": True,
            "KeepAlive": False,
        }

        with open(LOGIN_AGENT_FILE, "wb") as f:
            plistlib.dump(login_agent, f)
    else:
        unload_login_agent()
        if os.path.exists(LOGIN_AGENT_FILE):
            os.remove(LOGIN_AGENT_FILE)


def create_menu_bar_icon():
    try:
        from PIL import Image, ImageDraw

        scale = 3
        size = 22
        image = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        def point(x, y):
            return (x * scale, y * scale)

        color = (0, 0, 0, 255)
        line_width = 3 * scale
        center_x = 11

        draw.line(
            [point(center_x, 4), point(center_x, 18)],
            fill=color,
            width=line_width,
        )

        draw.polygon(
            [point(center_x, 3), point(6, 8), point(16, 8)],
            fill=color,
        )

        draw.polygon(
            [point(center_x, 19), point(6, 14), point(16, 14)],
            fill=color,
        )

        image = image.resize((20, 20), Image.Resampling.LANCZOS)
        image.save(MENU_BAR_ICON_FILE)
        return MENU_BAR_ICON_FILE

    except Exception:
        return None


def load_config():
    config = DEFAULT_CONFIG.copy()

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                loaded_config = json.load(f)
            for key in DEFAULT_CONFIG:
                if key in loaded_config:
                    config[key] = loaded_config[key]
        except (OSError, json.JSONDecodeError):
            pass

    config["enabled"] = bool(config["enabled"])
    config["start_at_login"] = is_start_at_login_enabled()
    config["rev_vert"] = bool(config["rev_vert"])
    config["rev_horiz"] = bool(config["rev_horiz"])
    config["apply_trackpad"] = bool(config["apply_trackpad"])
    config["apply_mouse"] = bool(config["apply_mouse"])
    config["step_size"] = normalize_step_size(config["step_size"])
    return config


def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


# ==========================================
# PART 1: THE TKINTER SETTINGS UI
# ==========================================
def run_settings_ui():
    import webbrowser
    import tkinter as tk
    from tkinter import messagebox

    config = load_config()

    bg = "#242424"
    card_bg = "#292929"
    card_border = "#3a3a3a"
    text = "#f2f2f2"
    muted = "#a8a8a8"
    blue = "#2f8cff"
    blue_dark = "#1167d8"
    unchecked = "#5d5d5d"
    unchecked_border = "#6a6a6a"
    font_family = ".AppleSystemUIFont"

    def rounded_rectangle(canvas, x1, y1, x2, y2, radius, **kwargs):
        points = [
            x1 + radius,
            y1,
            x2 - radius,
            y1,
            x2,
            y1,
            x2,
            y1 + radius,
            x2,
            y2 - radius,
            x2,
            y2,
            x2 - radius,
            y2,
            x1 + radius,
            y2,
            x1,
            y2,
            x1,
            y2 - radius,
            x1,
            y1 + radius,
            x1,
            y1,
        ]
        return canvas.create_polygon(points, smooth=True, splinesteps=18, **kwargs)

    class RoundedCard(tk.Canvas):
        def __init__(self, master, width, height, radius=14, padding=20):
            super().__init__(
                master,
                width=width,
                height=height,
                bg=bg,
                bd=0,
                highlightthickness=0,
            )
            self.width = width
            self.height = height
            self.radius = radius
            self.padding = padding
            self.inner = tk.Frame(self, bg=card_bg)
            self.draw()

        def draw(self):
            self.delete("all")
            rounded_rectangle(
                self,
                1,
                1,
                self.width - 1,
                self.height - 1,
                self.radius,
                fill=card_bg,
                outline=card_border,
                width=2,
            )
            self.create_window(
                self.padding,
                self.padding,
                anchor="nw",
                window=self.inner,
                width=self.width - (self.padding * 2),
                height=self.height - (self.padding * 2),
            )

    class ModernCheckbutton(tk.Frame):
        def __init__(
            self,
            master,
            label,
            variable,
            bg_color,
            size=26,
            font_size=18,
            bold=False,
            gap=10,
        ):
            super().__init__(master, bg=bg_color)
            self.variable = variable
            self.bg_color = bg_color
            self.size = size
            weight = "bold" if bold else "normal"
            self.checkbutton = tk.Checkbutton(
                self,
                text=label,
                variable=variable,
                bg=bg_color,
                fg=text,
                activebackground=bg_color,
                activeforeground=text,
                selectcolor=blue,
                indicatoron=True,
                bd=0,
                highlightthickness=0,
                padx=0,
                pady=0,
                font=(".AppleSystemUIFont", font_size, weight),
            )
            self.checkbutton.pack(side=tk.LEFT, padx=(0, gap))

    class ModernSlider(tk.Frame):
        def __init__(self, master, variable, command=None, width=210):
            super().__init__(master, bg=card_bg)
            self.variable = variable
            self.command = command
            self.width = width
            self.height = 28
            self.padding = 10
            self.last_value = variable.get()
            self.canvas = tk.Canvas(
                self,
                width=width,
                height=self.height,
                bg=card_bg,
                bd=0,
                highlightthickness=0,
            )
            self.canvas.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.value_label = tk.Label(
                self,
                width=3,
                text=str(variable.get()),
                bg=card_bg,
                fg=text,
                font=(font_family, 12),
                anchor=tk.E,
            )
            self.value_label.pack(side=tk.LEFT, padx=(6, 0))

            self.canvas.bind("<Button-1>", self.set_from_event)
            self.canvas.bind("<B1-Motion>", self.set_from_event)
            self.canvas.bind("<Configure>", lambda _event: self.draw())
            self.variable.trace_add("write", self.on_variable_change)
            self.draw()

        def set_from_event(self, event):
            width = max(self.canvas.winfo_width(), self.width)
            start = self.padding
            end = width - self.padding
            x = max(start, min(event.x, end))
            ratio = (x - start) / (end - start)
            value = round(SCROLL_STEP_MIN + ratio * (SCROLL_STEP_MAX - SCROLL_STEP_MIN))
            self.variable.set(normalize_step_size(value))

        def on_variable_change(self, *_args):
            value = normalize_step_size(self.variable.get())
            if value != self.variable.get():
                self.variable.set(value)
                return

            self.value_label.config(text=str(value))
            self.draw()

            if value != self.last_value:
                self.last_value = value
                if self.command:
                    self.command(value)

        def draw(self):
            self.canvas.delete("all")
            width = max(self.canvas.winfo_width(), self.width)
            start = self.padding
            end = width - self.padding
            y = self.height // 2
            value = normalize_step_size(self.variable.get())
            ratio = (value - SCROLL_STEP_MIN) / (SCROLL_STEP_MAX - SCROLL_STEP_MIN)
            thumb_x = start + ratio * (end - start)

            self.canvas.create_line(
                start,
                y,
                end,
                y,
                fill="#4b4b4b",
                width=5,
                capstyle=tk.ROUND,
            )
            self.canvas.create_line(
                start,
                y,
                thumb_x,
                y,
                fill=blue,
                width=5,
                capstyle=tk.ROUND,
            )
            self.canvas.create_oval(
                thumb_x - 9,
                y - 9,
                thumb_x + 9,
                y + 9,
                fill="#bdbdbd",
                outline="#c7c7c7",
                width=1,
            )

    def center_window(window, width, height):
        window.update_idletasks()
        x = max(0, (window.winfo_screenwidth() - width) // 2)
        y = max(0, (window.winfo_screenheight() - height) // 2)
        window.geometry(f"{width}x{height}+{x}+{y}")

    root = tk.Tk()
    hide_from_dock()
    root.withdraw()
    root.title("ShiftScroll Settings")
    root.configure(bg=bg)
    root.resizable(False, False)
    center_window(root, 400, 390)

    is_syncing = False

    def on_change(*args):
        nonlocal is_syncing
        if is_syncing:
            return

        config["enabled"] = bool(var_enabled.get())
        config["start_at_login"] = bool(var_start_login.get())
        config["rev_vert"] = bool(var_rev_vert.get())
        config["rev_horiz"] = bool(var_rev_horiz.get())
        config["apply_trackpad"] = bool(var_trackpad.get())
        config["apply_mouse"] = bool(var_mouse.get())

        try:
            if config["start_at_login"] != is_start_at_login_enabled():
                set_start_at_login(config["start_at_login"])
        except Exception as exc:
            config["start_at_login"] = is_start_at_login_enabled()
            is_syncing = True
            var_start_login.set(config["start_at_login"])
            is_syncing = False
            messagebox.showerror(
                "Start at Login",
                f"Could not update the login item.\n\n{exc}",
                parent=root,
            )

        save_config(config)

    var_enabled = tk.BooleanVar(value=config["enabled"])
    var_start_login = tk.BooleanVar(value=config["start_at_login"])
    var_rev_vert = tk.BooleanVar(value=config["rev_vert"])
    var_rev_horiz = tk.BooleanVar(value=config["rev_horiz"])
    var_trackpad = tk.BooleanVar(value=config["apply_trackpad"])
    var_mouse = tk.BooleanVar(value=config["apply_mouse"])
    var_step = tk.IntVar(value=config["step_size"])

    for var in (
        var_enabled,
        var_start_login,
        var_rev_vert,
        var_rev_horiz,
        var_trackpad,
        var_mouse,
    ):
        var.trace_add("write", on_change)

    def on_step_change(value):
        config["step_size"] = normalize_step_size(value)
        save_config(config)

    main = tk.Frame(root, bg=bg)
    main.pack(fill=tk.BOTH, expand=True, padx=14, pady=10)

    top = tk.Frame(main, bg=bg)
    top.pack(fill=tk.X, pady=(0, 8))
    top_options = tk.Frame(top, bg=bg)
    top_options.pack(anchor=tk.CENTER)
    ModernCheckbutton(
        top_options,
        "Enable ShiftScroll",
        var_enabled,
        bg,
        size=18,
        font_size=12,
        gap=8,
    ).pack(anchor=tk.W)
    ModernCheckbutton(
        top_options,
        "Start at login",
        var_start_login,
        bg,
        size=18,
        font_size=12,
        gap=8,
    ).pack(anchor=tk.W, pady=(5, 0))

    columns = tk.Frame(main, bg=bg)
    columns.pack(fill=tk.X)

    axes_section = tk.Frame(columns, bg=bg)
    axes_section.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 4))
    tk.Label(
        axes_section,
        text="Scrolling Axes",
        bg=bg,
        fg=text,
        font=(".AppleSystemUIFont", 14, "bold"),
    ).pack(anchor=tk.W, padx=8, pady=(0, 2))
    axes_card = RoundedCard(axes_section, 182, 74, radius=10, padding=10)
    axes_card.pack(fill=tk.BOTH)
    axes_options = tk.Frame(axes_card.inner, bg=card_bg)
    axes_options.pack(expand=True, anchor=tk.W)
    ModernCheckbutton(
        axes_options,
        "Reverse Vertical",
        var_rev_vert,
        card_bg,
        size=16,
        font_size=12,
        gap=7,
    ).pack(anchor=tk.W)
    ModernCheckbutton(
        axes_options,
        "Reverse Horizontal",
        var_rev_horiz,
        card_bg,
        size=16,
        font_size=12,
        gap=7,
    ).pack(anchor=tk.W, pady=(8, 0))

    devices_section = tk.Frame(columns, bg=bg)
    devices_section.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(4, 0))
    tk.Label(
        devices_section,
        text="Scrolling Devices",
        bg=bg,
        fg=text,
        font=(".AppleSystemUIFont", 14, "bold"),
    ).pack(anchor=tk.W, padx=8, pady=(0, 2))
    devices_card = RoundedCard(devices_section, 182, 74, radius=10, padding=10)
    devices_card.pack(fill=tk.BOTH)
    devices_options = tk.Frame(devices_card.inner, bg=card_bg)
    devices_options.pack(expand=True, anchor=tk.W)
    ModernCheckbutton(
        devices_options,
        "Reverse Trackpad",
        var_trackpad,
        card_bg,
        size=16,
        font_size=12,
        gap=7,
    ).pack(anchor=tk.W)
    ModernCheckbutton(
        devices_options,
        "Reverse Mouse",
        var_mouse,
        card_bg,
        size=16,
        font_size=12,
        gap=7,
    ).pack(anchor=tk.W, pady=(8, 0))

    step_section = tk.Frame(main, bg=bg)
    step_section.pack(fill=tk.X, pady=(9, 0))
    tk.Label(
        step_section,
        text="Scroll Wheel",
        bg=bg,
        fg=text,
        font=(".AppleSystemUIFont", 14, "bold"),
    ).pack(anchor=tk.W, padx=8, pady=(0, 2))
    step_card = RoundedCard(step_section, 372, 78, radius=10, padding=12)
    step_card.pack(fill=tk.X)

    slider_row = tk.Frame(step_card.inner, bg=card_bg)
    slider_row.pack(fill=tk.X)
    tk.Label(
        slider_row,
        text="Step size",
        bg=card_bg,
        fg=text,
        font=(font_family, 12, "normal"),
    ).pack(side=tk.LEFT, padx=(0, 8))
    ModernSlider(slider_row, var_step, command=on_step_change).pack(
        side=tk.LEFT, fill=tk.X, expand=True
    )

    slider_labels = tk.Frame(step_card.inner, bg=card_bg)
    slider_labels.pack(fill=tk.X, padx=(67, 32), pady=(4, 0))
    tk.Label(
        slider_labels,
        text="Small",
        bg=card_bg,
        fg=muted,
        font=(font_family, 9),
    ).pack(side=tk.LEFT)
    tk.Label(
        slider_labels,
        text="Large",
        bg=card_bg,
        fg=muted,
        font=(font_family, 9),
    ).pack(side=tk.RIGHT)

    credit_section = tk.Frame(main, bg=bg)
    credit_section.pack(fill=tk.X, pady=(14, 0))

    tk.Frame(credit_section, bg=card_border, height=1).pack(fill=tk.X, padx=4, pady=(0, 10))

    tk.Label(
        credit_section,
        text="ShiftScroll",
        bg=bg,
        fg=text,
        font=(font_family, 12, "bold"),
    ).pack(anchor=tk.CENTER)
    tk.Label(
        credit_section,
        text="1.0",
        bg=bg,
        fg=text,
        font=(font_family, 11),
    ).pack(anchor=tk.CENTER)
    tk.Label(
        credit_section,
        text="by MinhDuc",
        bg=bg,
        fg=text,
        font=(font_family, 11),
    ).pack(anchor=tk.CENTER)

    credit_url = "https://github.com/M1n4Dux"
    link_label = tk.Label(
        credit_section,
        text=credit_url,
        bg=bg,
        fg=blue,
        cursor="hand2",
        font=(font_family, 11),
    )
    link_label.pack(anchor=tk.CENTER)
    link_label.bind("<Button-1>", lambda _event: webbrowser.open_new_tab(credit_url))

    parent_pid = os.environ.get("SHIFTSCROLL_PARENT_PID")

    def close_if_parent_exits():
        if parent_pid:
            try:
                os.kill(int(parent_pid), 0)
            except (OSError, ValueError):
                root.destroy()
                return
        root.after(1000, close_if_parent_exits)

    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.deiconify()
    root.lift()
    root.attributes("-topmost", True)
    root.focus_force()
    root.after(150, lambda: root.attributes("-topmost", False))
    close_if_parent_exits()

    root.mainloop()


# ==========================================
# PART 2: THE BACKGROUND APP & COREGRAPHICS
# ==========================================
class ShiftScrollApp(rumps.App):
    def __init__(self):
        super(ShiftScrollApp, self).__init__("", quit_button=None, template=True)

        self.config = load_config()
        self.setup_dynamic_icon()

        self.menu = [
            rumps.MenuItem("Settings", callback=self.open_settings),
            None,  # Adds a divider line
            rumps.MenuItem("Quit ShiftScroll", callback=self.quit_app),
        ]

        self.current_run_loop = None
        self.settings_process = None

        # Check for config updates every 1 second
        self.timer = rumps.Timer(self.refresh_config, 1)
        self.timer.start()

        self.start_core_graphics_loop()

    def setup_dynamic_icon(self):
        icon_path = create_menu_bar_icon()
        if icon_path:
            self.icon = icon_path
            self.title = None
        else:
            self.title = "↕︎"

    def refresh_config(self, _):
        self.config = load_config()

    def open_settings(self, _):
        # Spawn the UI in a completely isolated process to prevent macOS threading crashes
        if self.settings_process and self.settings_process.poll() is None:
            return

        env = os.environ.copy()
        env["SHIFTSCROLL_PARENT_PID"] = str(os.getpid())
        self.settings_process = subprocess.Popen(
            [sys.executable, sys.argv[0], "--settings"],
            env=env,
        )

    def close_settings_window(self):
        if not self.settings_process or self.settings_process.poll() is not None:
            return

        self.settings_process.terminate()
        try:
            self.settings_process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.settings_process.kill()

    def scroll_callback(self, proxy, event_type, cg_event, refcon):
        from Quartz import (
            kCGEventScrollWheel,
            kCGEventFlagMaskShift,
            kCGScrollWheelEventDeltaAxis1,
            kCGScrollWheelEventDeltaAxis2,
            kCGScrollWheelEventPointDeltaAxis1,
            kCGScrollWheelEventPointDeltaAxis2,
            kCGScrollWheelEventFixedPtDeltaAxis1,
            kCGScrollWheelEventFixedPtDeltaAxis2,
            CGEventGetFlags,
            CGEventSetFlags,
            CGEventGetIntegerValueField,
            CGEventGetDoubleValueField,
            CGEventSetIntegerValueField,
            CGEventSetDoubleValueField,
            kCGScrollWheelEventIsContinuous
        )
        import math

        if event_type != kCGEventScrollWheel or not self.config["enabled"]:
            return cg_event

        # Same detection used by Scroll Reverser
        is_continuous = bool(
            CGEventGetIntegerValueField(
                cg_event,
                kCGScrollWheelEventIsContinuous
            )
        )
        is_trackpad = is_continuous

        # Check if the current device is enabled in settings
        if (is_trackpad and not self.config["apply_trackpad"]) or (
            not is_trackpad and not self.config["apply_mouse"]
        ):
            return cg_event

        flags = CGEventGetFlags(cg_event)
        is_shift = bool(flags & kCGEventFlagMaskShift)

        v_int = CGEventGetIntegerValueField(cg_event, kCGScrollWheelEventDeltaAxis1)
        h_int = CGEventGetIntegerValueField(cg_event, kCGScrollWheelEventDeltaAxis2)
        point_v = CGEventGetIntegerValueField(
            cg_event, kCGScrollWheelEventPointDeltaAxis1
        )
        point_h = CGEventGetIntegerValueField(
            cg_event, kCGScrollWheelEventPointDeltaAxis2
        )
        fixed_v = CGEventGetDoubleValueField(
            cg_event, kCGScrollWheelEventFixedPtDeltaAxis1
        )

        fixed_h = CGEventGetDoubleValueField(
            cg_event, kCGScrollWheelEventFixedPtDeltaAxis2
        )

        # 1. Bypass Shift-to-Horizontal conversion
        if is_shift:
            CGEventSetFlags(cg_event, flags & ~kCGEventFlagMaskShift)
        # Scroll Reverser style

        step = normalize_step_size(self.config["step_size"])

        discrete_adjust = (
            not is_trackpad
            and abs(v_int) == 1
        )

        vmul = -1 if self.config["rev_vert"] else 1
        hmul = -1 if self.config["rev_horiz"] else 1

        # Vertical

        if discrete_adjust:
            CGEventSetIntegerValueField(
                cg_event,
                kCGScrollWheelEventDeltaAxis1,
                v_int * vmul * step
            )
        else:
            if vmul != 1:
                CGEventSetIntegerValueField(
                    cg_event,
                    kCGScrollWheelEventDeltaAxis1,
                    v_int * vmul
                )

                CGEventSetIntegerValueField(
                    cg_event,
                    kCGScrollWheelEventPointDeltaAxis1,
                    point_v * vmul
                )

                CGEventSetDoubleValueField(
                    cg_event,
                    kCGScrollWheelEventFixedPtDeltaAxis1,
                    fixed_v * vmul
                )

        # Horizontal

        if hmul != 1:
            CGEventSetIntegerValueField(
                cg_event,
                kCGScrollWheelEventDeltaAxis2,
                h_int * hmul
            )

            CGEventSetIntegerValueField(
                cg_event,
                kCGScrollWheelEventPointDeltaAxis2,
                point_h * hmul
            )

            CGEventSetDoubleValueField(
                cg_event,
                kCGScrollWheelEventFixedPtDeltaAxis2,
                fixed_h * hmul
            )





        return cg_event

    def start_tap(self):
        from Quartz import (
            CGEventTapCreate,
            kCGSessionEventTap,
            kCGHeadInsertEventTap,
            kCGEventTapOptionDefault,
            kCGEventScrollWheel,
            CFMachPortCreateRunLoopSource,
            CFRunLoopGetCurrent,
            CFRunLoopAddSource,
            kCFRunLoopCommonModes,
            CFRunLoopRun,
        )

        event_mask = 1 << kCGEventScrollWheel
        tap = CGEventTapCreate(
            kCGSessionEventTap,
            kCGHeadInsertEventTap,
            kCGEventTapOptionDefault,
            event_mask,
            self.scroll_callback,
            None,
        )

        if tap:
            run_loop_source = CFMachPortCreateRunLoopSource(None, tap, 0)
            self.current_run_loop = CFRunLoopGetCurrent()
            CFRunLoopAddSource(
                self.current_run_loop, run_loop_source, kCFRunLoopCommonModes
            )
            CFRunLoopRun()
        else:
            rumps.alert(
                "Permissions Error", "Ensure ShiftScroll has Accessibility permissions."
            )
            os._exit(1)

    def start_core_graphics_loop(self):
        threading.Thread(target=self.start_tap, daemon=True).start()

    def quit_app(self, _):
        from Quartz import CFRunLoopStop

        self.close_settings_window()
        if self.current_run_loop:
            CFRunLoopStop(self.current_run_loop)
        rumps.quit_application()


if __name__ == "__main__":
    # If the script is called with the settings argument, launch the UI window.
    if len(sys.argv) > 1 and sys.argv[1] == "--settings":
        run_settings_ui()
    # Otherwise, launch the background menu bar app.
    else:
        if not acquire_single_instance_lock():
            sys.exit(0)
        hide_from_dock()
        ShiftScrollApp().run()
