#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Fleet Resource Calculator
=========================
This simple desktop application helps players of the browser game “Kantai
Collection” (舰队Collection) calculate the fuel and ammunition consumed by
their fleet during a single battle. 

It calculate resource consumption based 
on the total resource needed to restock the ship, and take 20% of that to 
work out the cost of each battle, and another 10% if the battle extends into 
the night.  

Calculator only account for standard battle consume, and not covering extras
like repairing cost.

Calculator also allows users to save the fleet they entered and load the fleet
to the current editor.

Data will be updated irregularly.

UI is written in Chinese at the this time, but preped for localization.
English UI will be added when I finish other projects.

The data is sourced from the KCWiki (舰娘百科). 
If you can provide list of ship names and IDs in English, 
please send to yuzewang0706@gmail.com, thank you!

Author: Jeremy Wang
Assisted by: ChatGPT
"""

"""
ver2.0 update:
Added button "Praise the Omnissiah" in the top right conner to please the machine spirit.
"""

from __future__ import annotations



import csv
import json
import os
import re
import sys
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

TITLE = "舰队资源消耗计算器"
SHIPS_CSV_NAME = "ships.csv"
EXP_TABLE_CSV_NAME = "exp_table.csv"
SAVED_FLEETS_NAME = "saved_fleets.json"
POPUP_MAX_CHARS = 10
POPUP_TEXT = "机魂大悦+1"
POPUP_BUTTON_TEXT = "赞美欧姆弥赛亚"


def get_app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_resource_path(filename: str) -> str:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        bundled_path = os.path.join(sys._MEIPASS, filename)
        if os.path.exists(bundled_path):
            return bundled_path

    external_path = os.path.join(get_app_dir(), filename)
    if os.path.exists(external_path):
        return external_path

    return os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)


SHIPS_FILE = get_resource_path(SHIPS_CSV_NAME)
EXP_TABLE_FILE = get_resource_path(EXP_TABLE_CSV_NAME)
SAVED_FLEETS_FILE = os.path.join(get_app_dir(), SAVED_FLEETS_NAME)


def normalize_id(value: str) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    # 兼容 Excel 导出的 80.0、145.0
    if re.fullmatch(r"\d+\.0+", text):
        return text.split(".")[0]
    return text


def is_numeric_id(text: str) -> bool:
    return bool(re.fullmatch(r"\d+(?:\.0+)?", text.strip()))


def round_half_up_percent(base_value: int, percent: int) -> int:
    return (base_value * percent + 50) // 100


def clamp_int(value: int, min_value: int, max_value: int) -> int:
    if value < min_value:
        return min_value
    if value > max_value:
        return max_value
    return value


class ExpTable:
    def __init__(self, total_exp_by_level: dict[int, int]):
        if not total_exp_by_level:
            raise ValueError("经验表为空。")
        self.total_exp_by_level = dict(total_exp_by_level)
        self.min_level = min(self.total_exp_by_level)
        self.max_level = max(self.total_exp_by_level)

    @classmethod
    def from_csv(cls, file_path: str) -> "ExpTable":
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"未找到经验表：{file_path}")

        total_exp_by_level: dict[int, int] = {}
        with open(file_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            for row in reader:
                if not row or len(row) < 3:
                    continue

                level_text = str(row[0]).strip()
                if not level_text.isdigit():
                    continue

                try:
                    level = int(level_text)
                    total_exp = int(str(row[2]).strip())
                except ValueError:
                    continue

                total_exp_by_level[level] = total_exp

        table = cls(total_exp_by_level)

        missing = [lv for lv in range(table.min_level, table.max_level + 1) if lv not in table.total_exp_by_level]
        if missing:
            raise ValueError(f"经验表缺少等级数据：{missing[0]} 等")
        return table

    def total_exp(self, level: int) -> int:
        return self.total_exp_by_level[level]

    def exp_needed(self, current_level: int, target_level: int) -> int:
        if target_level <= current_level:
            return 0
        return self.total_exp(target_level) - self.total_exp(current_level)


class DualHandleLevelSlider(tk.Canvas):
    def __init__(
        self,
        master,
        *,
        min_level: int,
        max_level: int,
        low_level: int,
        high_level: int,
        command=None,
        height: int = 40,
        **kwargs,
    ):
        super().__init__(master, height=height, highlightthickness=0, **kwargs)

        if max_level <= min_level:
            raise ValueError("max_level 必须大于 min_level")

        self.min_level = int(min_level)
        self.max_level = int(max_level)
        self.command = command

        self._handle_radius = 9
        self._padding = self._handle_radius + 2
        self._track_height = 6

        self._low_level = clamp_int(int(low_level), self.min_level, self.max_level)
        self._high_level = clamp_int(int(high_level), self.min_level, self.max_level)
        if self._low_level > self._high_level:
            self._low_level, self._high_level = self._high_level, self._low_level

        self._active_handle: str | None = None
        self._last_reported: tuple[int, int] | None = None

        self.bind("<Configure>", self._on_configure)
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)

        self._redraw()

    def get_levels(self) -> tuple[int, int]:
        return self._low_level, self._high_level

    def set_levels(self, low_level: int, high_level: int, *, notify: bool = False):
        low = clamp_int(int(low_level), self.min_level, self.max_level)
        high = clamp_int(int(high_level), self.min_level, self.max_level)
        if low > high:
            low, high = high, low

        changed = (low != self._low_level) or (high != self._high_level)
        self._low_level = low
        self._high_level = high
        if changed:
            self._redraw()
        if notify:
            self._notify_if_changed(force=True)

    def _track_y(self) -> int:
        return max(self._handle_radius + 2, self.winfo_height() // 2)

    def _track_x0_x1(self) -> tuple[int, int]:
        width = max(1, self.winfo_width())
        x0 = self._padding
        x1 = max(x0 + 1, width - self._padding)
        return x0, x1

    def _level_to_x(self, level: int) -> int:
        x0, x1 = self._track_x0_x1()
        span = self.max_level - self.min_level
        if span <= 0:
            return x0
        ratio = (level - self.min_level) / span
        return int(round(x0 + ratio * (x1 - x0)))

    def _x_to_level(self, x: int) -> int:
        x0, x1 = self._track_x0_x1()
        if x1 <= x0:
            return self.min_level
        ratio = (x - x0) / (x1 - x0)
        ratio = max(0.0, min(1.0, ratio))
        level = self.min_level + ratio * (self.max_level - self.min_level)
        return int(round(level))

    def _handle_center(self, handle: str) -> tuple[int, int]:
        y = self._track_y()
        level = self._low_level if handle == "low" else self._high_level
        return self._level_to_x(level), y

    def _distance_sq(self, x0: int, y0: int, x1: int, y1: int) -> int:
        return (x0 - x1) ** 2 + (y0 - y1) ** 2

    def _pick_handle(self, x: int, y: int) -> str:
        lx, ly = self._handle_center("low")
        hx, hy = self._handle_center("high")

        low_d = self._distance_sq(x, y, lx, ly)
        high_d = self._distance_sq(x, y, hx, hy)
        return "low" if low_d <= high_d else "high"

    def _on_configure(self, _event=None):
        self._redraw()

    def _on_press(self, event):
        self._active_handle = self._pick_handle(event.x, event.y)
        self._on_drag(event)

    def _on_drag(self, event):
        if not self._active_handle:
            return

        new_level = self._x_to_level(event.x)
        if self._active_handle == "low":
            new_level = min(new_level, self._high_level)
            if new_level != self._low_level:
                self._low_level = new_level
                self._redraw()
                self._notify_if_changed()
        else:
            new_level = max(new_level, self._low_level)
            if new_level != self._high_level:
                self._high_level = new_level
                self._redraw()
                self._notify_if_changed()

    def _on_release(self, _event):
        self._active_handle = None

    def _notify_if_changed(self, *, force: bool = False):
        if self.command is None:
            return
        current = (self._low_level, self._high_level)
        if (not force) and self._last_reported == current:
            return
        self._last_reported = current
        try:
            self.command(*current)
        except TypeError:
            self.command(current)

    def _redraw(self):
        self.delete("all")

        x0, x1 = self._track_x0_x1()
        y = self._track_y()
        low_x = self._level_to_x(self._low_level)
        high_x = self._level_to_x(self._high_level)

        track_y0 = y - self._track_height // 2
        track_y1 = y + self._track_height // 2

        self.create_rectangle(x0, track_y0, x1, track_y1, outline="", fill="#D0D0D0")
        self.create_rectangle(low_x, track_y0, high_x, track_y1, outline="", fill="#7A7A7A")

        r = self._handle_radius
        self.create_oval(low_x - r, y - r, low_x + r, y + r, outline="#404040", fill="#FFFFFF")
        self.create_oval(high_x - r, y - r, high_x + r, y + r, outline="#404040", fill="#FFFFFF")


class Ship:
    def __init__(self, sort_id: str, display_id: str, wiki_id: str, name: str, fuel: int, ammo: int):
        self.sort_id = normalize_id(sort_id)
        self.display_id = normalize_id(display_id)
        self.wiki_id = normalize_id(wiki_id)
        self.name = str(name).strip()
        self.fuel = int(fuel)
        self.ammo = int(ammo)

    def primary_id(self) -> str:
        return self.display_id or self.wiki_id

    def id_text(self) -> str:
        pieces = []
        if self.display_id:
            pieces.append(f"显示ID:{self.display_id}")
        if self.wiki_id:
            pieces.append(f"WikiID:{self.wiki_id}")
        return " / ".join(pieces)


class FleetResourceCalculatorApp:
    def __init__(self, master: tk.Tk):
        self.master = master
        self.master.title(TITLE)

        self.ships = []
        self.ships_by_name = {}
        self.ships_by_id = {}
        self._load_ship_data()

        self.exp_table: ExpTable | None = None
        self._load_exp_table()

        self.id_entries = []
        self.name_entries = []
        self.toast_widget = None
        self.toast_after_id = None

        self._exp_ui_updating = False
        self._exp_slider: DualHandleLevelSlider | None = None
        self._exp_current_var: tk.StringVar | None = None
        self._exp_target_var: tk.StringVar | None = None
        self._exp_needed_var: tk.StringVar | None = None

        self._build_ui()
        self._apply_startup_window_size()

    def _apply_startup_window_size(self):
        self.master.update_idletasks()

        screen_w = max(1, self.master.winfo_screenwidth())
        screen_h = max(1, self.master.winfo_screenheight())

        req_w = max(1, self.master.winfo_reqwidth())
        req_h = max(1, self.master.winfo_reqheight())

        base_w, base_h = 780, 760
        cap_w = max(1, int(screen_w * 0.95))
        cap_h = max(1, int(screen_h * 0.90))

        width = min(max(base_w, req_w), cap_w)
        height = min(max(base_h, req_h), cap_h)

        self.master.geometry(f"{width}x{height}")
        self.master.minsize(min(760, width), min(680, height))

    def _load_ship_data(self):
        if not os.path.exists(SHIPS_FILE):
            raise FileNotFoundError(f"未找到数据文件：{SHIPS_FILE}")

        with open(SHIPS_FILE, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            for row in reader:
                if not row or len(row) < 5:
                    continue

                if len(row) >= 6:
                    sort_id, display_id, wiki_id, name, fuel, ammo = row[:6]
                else:
                    sort_id = ""
                    display_id, wiki_id, name, fuel, ammo = row[:5]

                try:
                    ship = Ship(sort_id, display_id, wiki_id, name, int(fuel), int(ammo))
                except ValueError:
                    continue

                if not ship.name:
                    continue

                self.ships.append(ship)
                self.ships_by_name[ship.name] = ship

                for candidate_id in (ship.display_id, ship.wiki_id):
                    if candidate_id:
                        self.ships_by_id[candidate_id] = ship

        if not self.ships:
            raise ValueError("ships.csv 中没有读取到有效舰船数据。")

    def _load_exp_table(self):
        if not os.path.exists(EXP_TABLE_FILE):
            self.exp_table = None
            return
        try:
            self.exp_table = ExpTable.from_csv(EXP_TABLE_FILE)
        except Exception as e:
            self.exp_table = None
            try:
                messagebox.showerror("错误", f"读取经验表失败：{e}")
            except Exception:
                pass

    def _build_ui(self):
        main = ttk.Frame(self.master, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        top_bar = ttk.Frame(main)
        top_bar.pack(fill=tk.X, pady=(0, 8))

        title = ttk.Label(top_bar, text=TITLE, font=("Microsoft YaHei UI", 14, "bold"))
        title.pack(side=tk.LEFT, anchor="w")

        popup_control = ttk.Frame(top_bar)
        popup_control.pack(side=tk.RIGHT, anchor="e")
        ttk.Button(popup_control, text=POPUP_BUTTON_TEXT, command=self.show_center_popup).pack(side=tk.RIGHT)

        hint = ttk.Label(
            main,
            text="每个位置可输入舰船ID或中文舰船名；ID支持显示编号或KCWiki链接ID。留空的位置不会参与计算。",
            foreground="#555555",
        )
        hint.pack(anchor="w", pady=(0, 8))

        input_frame = ttk.LabelFrame(main, text="舰队编辑（最多6艘）", padding=10)
        input_frame.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(input_frame, text="位置", width=8).grid(row=0, column=0, padx=4, pady=3, sticky="w")
        ttk.Label(input_frame, text="舰船ID", width=14).grid(row=0, column=1, padx=4, pady=3, sticky="w")
        ttk.Label(input_frame, text="舰船名（中文）", width=28).grid(row=0, column=2, padx=4, pady=3, sticky="w")
        ttk.Label(input_frame, text="说明", width=30).grid(row=0, column=3, padx=4, pady=3, sticky="w")

        for i in range(6):
            ttk.Label(input_frame, text=f"舰船 {i + 1}").grid(row=i + 1, column=0, padx=4, pady=3, sticky="e")

            id_entry = ttk.Entry(input_frame, width=14)
            id_entry.grid(row=i + 1, column=1, padx=4, pady=3, sticky="we")
            self.id_entries.append(id_entry)

            name_entry = ttk.Entry(input_frame, width=28)
            name_entry.grid(row=i + 1, column=2, padx=4, pady=3, sticky="we")
            self.name_entries.append(name_entry)

            ttk.Label(input_frame, text="二者填一项即可；同时填写时必须对应同一艘船").grid(
                row=i + 1, column=3, padx=4, pady=3, sticky="w"
            )

        input_frame.columnconfigure(1, weight=1)
        input_frame.columnconfigure(2, weight=2)

        button_frame = ttk.Frame(main)
        button_frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(button_frame, text="计算消耗", command=self.calculate_consumption).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(button_frame, text="保存舰队", command=self.save_fleet).pack(side=tk.LEFT, padx=6)
        ttk.Button(button_frame, text="载入舰队", command=self.load_fleet).pack(side=tk.LEFT, padx=6)
        ttk.Button(button_frame, text="清空输入", command=self.clear_inputs).pack(side=tk.LEFT, padx=6)

        self.status_var = tk.StringVar(value=f"已载入舰船数据：{len(self.ships)} 条")
        status_bar = ttk.Label(main, textvariable=self.status_var, anchor="w", foreground="#555555")
        status_bar.pack(side=tk.BOTTOM, fill=tk.X, pady=(6, 0))

        self._build_exp_ui(main)

        result_frame = ttk.LabelFrame(main, text="计算结果", padding=8)
        result_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        columns = ("slot", "id", "ship", "normal_fuel", "normal_ammo", "night_fuel", "night_ammo")
        self.tree = ttk.Treeview(result_frame, columns=columns, show="headings", height=10)

        headings = {
            "slot": "位置",
            "id": "舰船ID",
            "ship": "舰船",
            "normal_fuel": "普通燃料",
            "normal_ammo": "普通弹药",
            "night_fuel": "夜战燃料",
            "night_ammo": "夜战弹药",
        }
        widths = {
            "slot": 60,
            "id": 130,
            "ship": 180,
            "normal_fuel": 90,
            "normal_ammo": 90,
            "night_fuel": 90,
            "night_ammo": 90,
        }
        anchors = {
            "slot": tk.CENTER,
            "id": tk.W,
            "ship": tk.W,
            "normal_fuel": tk.E,
            "normal_ammo": tk.E,
            "night_fuel": tk.E,
            "night_ammo": tk.E,
        }
        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=widths[col], anchor=anchors[col], stretch=True)

        y_scroll = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=y_scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        y_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_exp_ui(self, parent: ttk.Frame):
        exp_frame = ttk.LabelFrame(parent, text="升级经验计算", padding=10)
        exp_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))

        if self.exp_table is None:
            ttk.Label(exp_frame, text="未能载入 exp_table.csv，升级经验计算不可用。", foreground="#555555").pack(
                anchor="w"
            )
            return

        min_level = self.exp_table.min_level
        max_level = self.exp_table.max_level
        init_current = min_level
        init_target = min(min_level + 1, max_level)

        controls = ttk.Frame(exp_frame)
        controls.pack(fill=tk.X)

        self._exp_current_var = tk.StringVar(value=str(init_current))
        self._exp_target_var = tk.StringVar(value=str(init_target))
        self._exp_needed_var = tk.StringVar(value="")

        ttk.Label(controls, text="当前等级").pack(side=tk.LEFT)
        ttk.Entry(controls, width=6, textvariable=self._exp_current_var).pack(side=tk.LEFT, padx=(4, 12))

        ttk.Label(controls, text="目标等级").pack(side=tk.LEFT)
        ttk.Entry(controls, width=6, textvariable=self._exp_target_var).pack(side=tk.LEFT, padx=(4, 12))

        ttk.Label(controls, textvariable=self._exp_needed_var, font=("Microsoft YaHei UI", 10, "bold")).pack(
            side=tk.LEFT
        )

        self._exp_slider = DualHandleLevelSlider(
            exp_frame,
            min_level=min_level,
            max_level=max_level,
            low_level=init_current,
            high_level=init_target,
            command=self._on_exp_slider_change,
            bg=self.master.cget("bg"),
        )
        self._exp_slider.pack(fill=tk.X, pady=(8, 0))

        # 双向联动：输入框 ↔ 滑块
        self._exp_current_var.trace_add("write", self._on_exp_current_entry_change)
        self._exp_target_var.trace_add("write", self._on_exp_target_entry_change)

        self._update_exp_needed(init_current, init_target)

    def _parse_level_text(self, text: str) -> int | None:
        value = str(text).strip() if text is not None else ""
        if not value or not value.isdigit():
            return None
        try:
            return int(value)
        except ValueError:
            return None

    def _set_exp_levels(self, current_level: int, target_level: int, *, from_source: str):
        if self.exp_table is None:
            return
        if self._exp_current_var is None or self._exp_target_var is None or self._exp_slider is None:
            return

        min_level = self.exp_table.min_level
        max_level = self.exp_table.max_level

        current_level = clamp_int(int(current_level), min_level, max_level)
        target_level = clamp_int(int(target_level), min_level, max_level)
        if current_level > target_level:
            current_level, target_level = target_level, current_level

        self._exp_ui_updating = True
        try:
            if self._exp_current_var.get().strip() != str(current_level):
                self._exp_current_var.set(str(current_level))
            if self._exp_target_var.get().strip() != str(target_level):
                self._exp_target_var.set(str(target_level))

            if from_source != "slider":
                self._exp_slider.set_levels(current_level, target_level, notify=False)

            self._update_exp_needed(current_level, target_level)
        finally:
            self._exp_ui_updating = False

    def _update_exp_needed(self, current_level: int, target_level: int):
        if self.exp_table is None or self._exp_needed_var is None:
            return
        needed = self.exp_table.exp_needed(current_level, target_level)
        self._exp_needed_var.set(f"总共所需经验值：{needed:,}")

    def _on_exp_slider_change(self, current_level: int, target_level: int):
        if self._exp_ui_updating:
            return
        self._set_exp_levels(current_level, target_level, from_source="slider")

    def _on_exp_current_entry_change(self, *_args):
        if self._exp_ui_updating or self.exp_table is None:
            return
        if self._exp_current_var is None or self._exp_target_var is None or self._exp_slider is None:
            return

        current = self._parse_level_text(self._exp_current_var.get())
        if current is None:
            return

        low, high = self._exp_slider.get_levels()
        target = self._parse_level_text(self._exp_target_var.get())
        if target is None:
            target = high

        min_level = self.exp_table.min_level
        max_level = self.exp_table.max_level
        current = clamp_int(current, min_level, max_level)
        target = clamp_int(target, min_level, max_level)

        # 当前等级变大时，目标等级跟随，避免用户输入被“弹回”
        if current > target:
            target = current

        self._set_exp_levels(current, target, from_source="entry")

    def _on_exp_target_entry_change(self, *_args):
        if self._exp_ui_updating or self.exp_table is None:
            return
        if self._exp_current_var is None or self._exp_target_var is None or self._exp_slider is None:
            return

        target = self._parse_level_text(self._exp_target_var.get())
        if target is None:
            return

        low, high = self._exp_slider.get_levels()
        current = self._parse_level_text(self._exp_current_var.get())
        if current is None:
            current = low

        min_level = self.exp_table.min_level
        max_level = self.exp_table.max_level
        current = clamp_int(current, min_level, max_level)
        target = clamp_int(target, min_level, max_level)

        # 目标等级变小时，当前等级跟随
        if target < current:
            current = target

        self._set_exp_levels(current, target, from_source="entry")

    def _get_popup_text(self) -> str:
        text = str(POPUP_TEXT).strip() or "提示"
        if len(text) > POPUP_MAX_CHARS:
            text = text[:POPUP_MAX_CHARS]
        return text

    def show_center_popup(self):
        text = self._get_popup_text()

        if self.toast_after_id is not None:
            try:
                self.master.after_cancel(self.toast_after_id)
            except Exception:
                pass
            self.toast_after_id = None

        if self.toast_widget is not None and self.toast_widget.winfo_exists():
            self.toast_widget.destroy()
            self.toast_widget = None

        toast = tk.Frame(self.master, bg="#222222", bd=1, relief=tk.SOLID)
        self.toast_widget = toast

        label = tk.Label(
            toast,
            text=text,
            bg="#222222",
            fg="#FFFFFF",
            font=("Microsoft YaHei UI", 16, "bold"),
            padx=30,
            pady=18,
            justify=tk.CENTER,
        )
        label.pack(fill=tk.BOTH, expand=True)

        toast.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        toast.lift()

        def close_toast():
            if self.toast_widget is not None and self.toast_widget.winfo_exists():
                self.toast_widget.destroy()
            self.toast_widget = None
            self.toast_after_id = None

        self.toast_after_id = self.master.after(2000, close_toast)

    def find_ship(self, id_text: str = "", name_text: str = ""):
        ship_by_id = None
        ship_by_name = None

        id_key = normalize_id(id_text)
        name_key = name_text.strip()

        if id_key:
            ship_by_id = self.ships_by_id.get(id_key)
            if ship_by_id is None:
                raise ValueError(f"找不到ID为“{id_text}”的舰船。")

        if name_key:
            ship_by_name = self.ships_by_name.get(name_key)
            if ship_by_name is None:
                raise ValueError(f"找不到名称为“{name_text}”的舰船。")

        if ship_by_id and ship_by_name and ship_by_id is not ship_by_name:
            raise ValueError(
                f"ID“{id_text}”对应“{ship_by_id.name}”，但舰船名“{name_text}”对应另一艘船；请只保留一项或修正输入。"
            )

        return ship_by_id or ship_by_name

    def get_current_fleet(self):
        fleet = []
        for i in range(6):
            id_text = self.id_entries[i].get().strip()
            name_text = self.name_entries[i].get().strip()
            if not id_text and not name_text:
                continue
            ship = self.find_ship(id_text, name_text)
            fleet.append((i + 1, ship, id_text, name_text))
        return fleet

    def calculate_consumption(self):
        try:
            fleet = self.get_current_fleet()
        except ValueError as e:
            messagebox.showwarning("输入错误", str(e))
            return

        if not fleet:
            messagebox.showwarning("警告", "请至少输入一艘舰船。")
            return

        for item in self.tree.get_children():
            self.tree.delete(item)

        total_nf = total_na = total_yf = total_ya = 0

        for slot, ship, _id_text, _name_text in fleet:
            normal_fuel = round_half_up_percent(ship.fuel, 20)
            normal_ammo = round_half_up_percent(ship.ammo, 20)
            night_fuel = round_half_up_percent(ship.fuel, 30)
            night_ammo = round_half_up_percent(ship.ammo, 30)

            total_nf += normal_fuel
            total_na += normal_ammo
            total_yf += night_fuel
            total_ya += night_ammo

            self.tree.insert(
                "",
                tk.END,
                values=(
                    slot,
                    ship.id_text(),
                    ship.name,
                    normal_fuel,
                    normal_ammo,
                    night_fuel,
                    night_ammo,
                ),
            )

        self.tree.insert("", tk.END, values=("合计", "", "", total_nf, total_na, total_yf, total_ya), tags=("total",))
        self.tree.tag_configure("total", font=("Microsoft YaHei UI", 9, "bold"))
        self.status_var.set("计算完成：各舰先单独四舍五入，再进行舰队合计。")

    def clear_inputs(self):
        for entry in self.id_entries + self.name_entries:
            entry.delete(0, tk.END)
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.status_var.set(f"已清空输入。已载入舰船数据：{len(self.ships)} 条")

    def save_fleet(self):
        try:
            self.get_current_fleet()
        except ValueError as e:
            messagebox.showwarning("输入错误", str(e))
            return

        entries = []
        for i in range(6):
            id_text = self.id_entries[i].get().strip()
            name_text = self.name_entries[i].get().strip()
            if id_text or name_text:
                entries.append({"id": id_text, "name": name_text})

        if not entries:
            messagebox.showwarning("警告", "请至少输入一艘舰船。")
            return

        fleet_name = simpledialog.askstring("保存舰队", "请输入舰队名称：")
        if not fleet_name or not fleet_name.strip():
            return
        fleet_name = fleet_name.strip()

        fleets = self._read_saved_fleets()
        fleets[fleet_name] = entries
        self._write_saved_fleets(fleets)
        messagebox.showinfo("信息", f"舰队“{fleet_name}”已保存。")

    def load_fleet(self):
        fleets = self._read_saved_fleets()
        if not fleets:
            messagebox.showwarning("警告", "没有保存的舰队。")
            return

        dialog = FleetSelectDialog(self.master, list(fleets.keys()))
        selected_name = dialog.selected
        if not selected_name:
            return

        selected_entries = fleets[selected_name]
        self.clear_inputs()

        for i, item in enumerate(selected_entries[:6]):
            if isinstance(item, dict):
                self.id_entries[i].insert(0, item.get("id", ""))
                self.name_entries[i].insert(0, item.get("name", ""))
            else:
                text = str(item).strip()
                if is_numeric_id(text):
                    self.id_entries[i].insert(0, normalize_id(text))
                else:
                    self.name_entries[i].insert(0, text)

        self.status_var.set(f"已载入舰队：{selected_name}")

    def _read_saved_fleets(self):
        if not os.path.exists(SAVED_FLEETS_FILE):
            return {}
        try:
            with open(SAVED_FLEETS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception as e:
            messagebox.showerror("错误", f"读取保存舰队失败：{e}")
        return {}

    def _write_saved_fleets(self, fleets):
        with open(SAVED_FLEETS_FILE, "w", encoding="utf-8") as f:
            json.dump(fleets, f, ensure_ascii=False, indent=2)


class FleetSelectDialog(simpledialog.Dialog):
    def __init__(self, parent, fleet_names):
        self.fleet_names = fleet_names
        self.selected = None
        super().__init__(parent, "载入舰队")

    def body(self, master):
        ttk.Label(master, text="请选择要载入的舰队：").pack(anchor="w", padx=8, pady=(8, 4))
        self.combo = ttk.Combobox(master, values=self.fleet_names, state="readonly", width=38)
        self.combo.pack(padx=8, pady=4)
        if self.fleet_names:
            self.combo.current(0)
        return self.combo

    def apply(self):
        self.selected = self.combo.get().strip()


def main():
    try:
        root = tk.Tk()
        try:
            style = ttk.Style(root)
            if "vista" in style.theme_names():
                style.theme_use("vista")
        except Exception:
            pass
        FleetResourceCalculatorApp(root)
        root.mainloop()
    except Exception as e:
        messagebox.showerror("错误", str(e))


if __name__ == "__main__":
    main()
