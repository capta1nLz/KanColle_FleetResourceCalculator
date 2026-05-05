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

import csv
import json
import os
import re
import sys
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

TITLE = "舰队资源消耗计算器"
SHIPS_CSV_NAME = "ships.csv"
SAVED_FLEETS_NAME = "saved_fleets.json"


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
SAVED_FLEETS_FILE = os.path.join(get_app_dir(), SAVED_FLEETS_NAME)


def normalize_id(value: str) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if re.fullmatch(r"\d+\.0+", text):
        return text.split(".")[0]
    return text


def is_numeric_id(text: str) -> bool:
    return bool(re.fullmatch(r"\d+(?:\.0+)?", text.strip()))


def round_half_up_percent(base_value: int, percent: int) -> int:
    return (base_value * percent + 50) // 100


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
        self.master.geometry("780x560")
        self.master.minsize(760, 520)

        self.ships = []
        self.ships_by_name = {}
        self.ships_by_id = {}
        self._load_ship_data()

        self.id_entries = []
        self.name_entries = []

        self._build_ui()

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

    def _build_ui(self):
        main = ttk.Frame(self.master, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(main, text=TITLE, font=("Microsoft YaHei UI", 14, "bold"))
        title.pack(anchor="w", pady=(0, 8))

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

        result_frame = ttk.LabelFrame(main, text="计算结果", padding=8)
        result_frame.pack(fill=tk.BOTH, expand=True)

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

        self.status_var = tk.StringVar(value=f"已载入舰船数据：{len(self.ships)} 条")
        status_bar = ttk.Label(main, textvariable=self.status_var, anchor="w", foreground="#555555")
        status_bar.pack(fill=tk.X, pady=(6, 0))

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
