#!/usr/bin/env python3
"""
Kirayedaar (Tenant) Management App
For tracking rooms, rent, and electricity bills
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import sqlite3
from datetime import datetime, date
from pathlib import Path
import calendar

DB_PATH = Path(__file__).parent / "kirayedaar.db"


class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.create_tables()
        self.seed_defaults()

    def create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_number TEXT UNIQUE NOT NULL,
                tenant_name TEXT DEFAULT '',
                base_rent REAL NOT NULL DEFAULT 0,
                phone TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                is_active INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS monthly_bills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id INTEGER NOT NULL,
                month TEXT NOT NULL,          -- YYYY-MM
                rent_amount REAL NOT NULL,
                electricity_amount REAL DEFAULT 0,
                electricity_units REAL DEFAULT 0,
                total_amount REAL NOT NULL,
                status TEXT DEFAULT 'pending', -- pending / paid
                paid_on TEXT,
                payment_note TEXT DEFAULT '',
                created_at TEXT,
                FOREIGN KEY (room_id) REFERENCES rooms(id),
                UNIQUE(room_id, month)
            );
        """)
        self.conn.commit()

    def seed_defaults(self):
        cur = self.conn.execute("SELECT COUNT(*) FROM rooms")
        if cur.fetchone()[0] == 0:
            samples = [
                ("101", "Ram Singh", 5000, "9876543210"),
                ("102", "Sita Devi", 4500, ""),
                ("201", "Amit Kumar", 6000, "9876501234"),
                ("202", "", 5500, ""),
            ]
            self.conn.executemany(
                "INSERT INTO rooms (room_number, tenant_name, base_rent, phone) VALUES (?, ?, ?, ?)",
                samples)
            self.conn.commit()

    # ---------- Rooms ----------
    def get_rooms(self, active_only=True):
        q = "SELECT * FROM rooms"
        if active_only:
            q += " WHERE is_active = 1"
        q += " ORDER BY room_number"
        return self.conn.execute(q).fetchall()

    def add_room(self, room_number, tenant_name, base_rent, phone="", notes=""):
        try:
            self.conn.execute(
                "INSERT INTO rooms (room_number, tenant_name, base_rent, phone, notes) VALUES (?, ?, ?, ?, ?)",
                (room_number, tenant_name, base_rent, phone, notes))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def update_room(self, room_id, room_number, tenant_name, base_rent, phone, notes):
        self.conn.execute(
            """UPDATE rooms SET room_number=?, tenant_name=?, base_rent=?, phone=?, notes=?
               WHERE id=?""",
            (room_number, tenant_name, base_rent, phone, notes, room_id))
        self.conn.commit()

    def delete_room(self, room_id):
        self.conn.execute("UPDATE rooms SET is_active=0 WHERE id=?", (room_id,))
        self.conn.commit()

    def get_room(self, room_id):
        return self.conn.execute("SELECT * FROM rooms WHERE id=?", (room_id,)).fetchone()

    # ---------- Monthly Bills ----------
    def get_or_create_bill(self, room_id, month, rent_amount, elec_amount=0, elec_units=0):
        existing = self.conn.execute(
            "SELECT * FROM monthly_bills WHERE room_id=? AND month=?",
            (room_id, month)).fetchone()
        if existing:
            return existing
        total = rent_amount + elec_amount
        now = datetime.now().isoformat(timespec="seconds")
        cur = self.conn.execute(
            """INSERT INTO monthly_bills
               (room_id, month, rent_amount, electricity_amount, electricity_units,
                total_amount, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (room_id, month, rent_amount, elec_amount, elec_units, total, now))
        self.conn.commit()
        return self.conn.execute(
            "SELECT * FROM monthly_bills WHERE id=?", (cur.lastrowid,)).fetchone()

    def update_bill(self, bill_id, rent_amount, elec_amount, elec_units, status=None, paid_on=None, note=""):
        total = rent_amount + elec_amount
        if status == "paid" and not paid_on:
            paid_on = date.today().isoformat()
        self.conn.execute(
            """UPDATE monthly_bills
               SET rent_amount=?, electricity_amount=?, electricity_units=?,
                   total_amount=?, status=COALESCE(?, status),
                   paid_on=COALESCE(?, paid_on), payment_note=?
               WHERE id=?""",
            (rent_amount, elec_amount, elec_units, total, status, paid_on, note, bill_id))
        self.conn.commit()

    def mark_paid(self, bill_id, note=""):
        today = date.today().isoformat()
        self.conn.execute(
            "UPDATE monthly_bills SET status='paid', paid_on=?, payment_note=? WHERE id=?",
            (today, note, bill_id))
        self.conn.commit()

    def get_bills_for_month(self, month):
        return self.conn.execute("""
            SELECT b.*, r.room_number, r.tenant_name, r.phone
            FROM monthly_bills b
            JOIN rooms r ON b.room_id = r.id
            WHERE b.month = ? AND r.is_active = 1
            ORDER BY r.room_number
        """, (month,)).fetchall()

    def get_bill(self, bill_id):
        return self.conn.execute("""
            SELECT b.*, r.room_number, r.tenant_name
            FROM monthly_bills b
            JOIN rooms r ON b.room_id = r.id
            WHERE b.id = ?
        """, (bill_id,)).fetchone()

    def get_pending_summary(self, month=None):
        if month:
            row = self.conn.execute("""
                SELECT
                    COUNT(*) as total_bills,
                    SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) as pending_count,
                    SUM(CASE WHEN status='paid' THEN 1 ELSE 0 END) as paid_count,
                    COALESCE(SUM(CASE WHEN status='pending' THEN total_amount ELSE 0 END), 0) as pending_amount,
                    COALESCE(SUM(CASE WHEN status='paid' THEN total_amount ELSE 0 END), 0) as collected_amount
                FROM monthly_bills b
                JOIN rooms r ON b.room_id = r.id
                WHERE b.month = ? AND r.is_active = 1
            """, (month,)).fetchone()
        else:
            row = self.conn.execute("""
                SELECT
                    COUNT(*) as total_bills,
                    SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) as pending_count,
                    SUM(CASE WHEN status='paid' THEN 1 ELSE 0 END) as paid_count,
                    COALESCE(SUM(CASE WHEN status='pending' THEN total_amount ELSE 0 END), 0) as pending_amount,
                    COALESCE(SUM(CASE WHEN status='paid' THEN total_amount ELSE 0 END), 0) as collected_amount
                FROM monthly_bills b
                JOIN rooms r ON b.room_id = r.id
                WHERE r.is_active = 1
            """).fetchone()
        return row


class KirayedaarApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Kirayedaar Management – Room Rent & Electricity")
        self.geometry("1050x650")
        self.minsize(900, 550)
        self.db = Database()

        self.bg = "#f0f2f5"
        self.primary = "#1a73e8"
        self.success = "#0d904f"
        self.danger = "#d93025"
        self.warning = "#f9ab00"
        self.configure(bg=self.bg)

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TNotebook", background=self.bg)
        style.configure("TNotebook.Tab", padding=[14, 8], font=("Segoe UI", 10, "bold"))
        style.configure("Treeview", font=("Segoe UI", 10), rowheight=28)
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
        style.configure("TButton", font=("Segoe UI", 10), padding=6)

        self.current_month = date.today().strftime("%Y-%m")
        self._build_ui()
        self.refresh_rooms()
        self.refresh_bills()

    def _build_ui(self):
        # Header
        header = tk.Frame(self, bg=self.primary, height=54)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="🏠  Kirayedaar Management",
                 font=("Segoe UI", 16, "bold"), bg=self.primary, fg="white").pack(side="left", padx=20, pady=12)
        self.clock_label = tk.Label(header, font=("Segoe UI", 11), bg=self.primary, fg="white")
        self.clock_label.pack(side="right", padx=20)
        self._update_clock()

        # Notebook
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=10, pady=10)

        self.tab_rooms = tk.Frame(self.nb, bg=self.bg)
        self.tab_bills = tk.Frame(self.nb, bg=self.bg)
        self.tab_report = tk.Frame(self.nb, bg=self.bg)

        self.nb.add(self.tab_rooms, text="  Rooms / Tenants  ")
        self.nb.add(self.tab_bills, text="  Monthly Bills  ")
        self.nb.add(self.tab_report, text="  Reports  ")

        self._build_rooms_tab()
        self._build_bills_tab()
        self._build_report_tab()

    def _update_clock(self):
        self.clock_label.config(text=datetime.now().strftime("%d %b %Y  %I:%M %p"))
        self.after(30000, self._update_clock)

    # ===================== ROOMS TAB =====================
    def _build_rooms_tab(self):
        top = tk.Frame(self.tab_rooms, bg=self.bg)
        top.pack(fill="x", pady=(0, 8))
        tk.Label(top, text="All Rooms & Tenants", font=("Segoe UI", 12, "bold"), bg=self.bg).pack(side="left")
        ttk.Button(top, text="+ Add Room", command=self._add_room).pack(side="right", padx=4)
        ttk.Button(top, text="Edit", command=self._edit_room).pack(side="right", padx=4)
        ttk.Button(top, text="Delete", command=self._delete_room).pack(side="right", padx=4)

        cols = ("room", "tenant", "rent", "phone", "notes")
        self.room_tree = ttk.Treeview(self.tab_rooms, columns=cols, show="headings", height=18)
        self.room_tree.heading("room", text="Room No.")
        self.room_tree.heading("tenant", text="Tenant Name")
        self.room_tree.heading("rent", text="Base Rent ₹")
        self.room_tree.heading("phone", text="Phone")
        self.room_tree.heading("notes", text="Notes")
        self.room_tree.column("room", width=90, anchor="center")
        self.room_tree.column("tenant", width=180)
        self.room_tree.column("rent", width=100, anchor="e")
        self.room_tree.column("phone", width=120)
        self.room_tree.column("notes", width=200)
        self.room_tree.pack(fill="both", expand=True)
        self.room_tree.bind("<Double-1>", lambda e: self._edit_room())

    def refresh_rooms(self):
        for i in self.room_tree.get_children():
            self.room_tree.delete(i)
        for r in self.db.get_rooms():
            self.room_tree.insert("", "end", iid=r["id"], values=(
                r["room_number"],
                r["tenant_name"] or "— Vacant —",
                f"{r['base_rent']:.0f}",
                r["phone"] or "",
                r["notes"] or ""
            ))

    def _add_room(self):
        self._room_dialog()

    def _edit_room(self):
        sel = self.room_tree.selection()
        if not sel:
            messagebox.showinfo("Select", "Please select a room to edit.")
            return
        room = self.db.get_room(int(sel[0]))
        self._room_dialog(room)

    def _delete_room(self):
        sel = self.room_tree.selection()
        if not sel:
            return
        if messagebox.askyesno("Delete", "Remove this room from the list?"):
            self.db.delete_room(int(sel[0]))
            self.refresh_rooms()
            self.refresh_bills()

    def _room_dialog(self, room=None):
        dlg = tk.Toplevel(self)
        dlg.title("Edit Room" if room else "Add Room")
        dlg.geometry("380x280")
        dlg.transient(self)
        dlg.grab_set()
        dlg.configure(bg=self.bg)

        fields = [
            ("Room Number:", "room_number"),
            ("Tenant Name:", "tenant_name"),
            ("Base Rent (₹):", "base_rent"),
            ("Phone:", "phone"),
            ("Notes:", "notes"),
        ]
        entries = {}
        for i, (label, key) in enumerate(fields):
            tk.Label(dlg, text=label, bg=self.bg).grid(row=i, column=0, sticky="e", padx=10, pady=6)
            e = ttk.Entry(dlg, width=28)
            e.grid(row=i, column=1, pady=6)
            if room:
                val = room[key] if key != "base_rent" else str(room["base_rent"])
                e.insert(0, val or "")
            entries[key] = e

        def save():
            rn = entries["room_number"].get().strip()
            tn = entries["tenant_name"].get().strip()
            try:
                rent = float(entries["base_rent"].get() or 0)
            except ValueError:
                messagebox.showerror("Error", "Invalid rent amount.", parent=dlg)
                return
            ph = entries["phone"].get().strip()
            nt = entries["notes"].get().strip()
            if not rn:
                messagebox.showerror("Error", "Room number is required.", parent=dlg)
                return
            if room:
                self.db.update_room(room["id"], rn, tn, rent, ph, nt)
            else:
                if not self.db.add_room(rn, tn, rent, ph, nt):
                    messagebox.showerror("Error", "Room number already exists.", parent=dlg)
                    return
            self.refresh_rooms()
            self.refresh_bills()
            dlg.destroy()

        ttk.Button(dlg, text="Save", command=save).grid(row=len(fields), column=0, columnspan=2, pady=16)

    # ===================== BILLS TAB =====================
    def _build_bills_tab(self):
        top = tk.Frame(self.tab_bills, bg=self.bg)
        top.pack(fill="x", pady=(0, 8))

        tk.Label(top, text="Month:", bg=self.bg, font=("Segoe UI", 10)).pack(side="left")
        self.month_var = tk.StringVar(value=self.current_month)
        month_entry = ttk.Entry(top, textvariable=self.month_var, width=10)
        month_entry.pack(side="left", padx=6)
        ttk.Button(top, text="Load", command=self.refresh_bills).pack(side="left", padx=4)
        ttk.Button(top, text="← Prev", command=self._prev_month).pack(side="left", padx=2)
        ttk.Button(top, text="Next →", command=self._next_month).pack(side="left", padx=2)

        ttk.Button(top, text="Generate Bills for Month", command=self._generate_bills).pack(side="right", padx=4)
        ttk.Button(top, text="Mark as Paid", command=self._mark_paid).pack(side="right", padx=4)
        ttk.Button(top, text="Edit Bill", command=self._edit_bill).pack(side="right", padx=4)

        # Summary bar
        self.bill_summary = tk.Label(self.tab_bills, text="", font=("Segoe UI", 10), bg=self.bg, fg="#333")
        self.bill_summary.pack(anchor="w", pady=4)

        cols = ("room", "tenant", "rent", "elec", "total", "status", "paid_on")
        self.bill_tree = ttk.Treeview(self.tab_bills, columns=cols, show="headings", height=16)
        self.bill_tree.heading("room", text="Room")
        self.bill_tree.heading("tenant", text="Tenant")
        self.bill_tree.heading("rent", text="Rent ₹")
        self.bill_tree.heading("elec", text="Electricity ₹")
        self.bill_tree.heading("total", text="Total ₹")
        self.bill_tree.heading("status", text="Status")
        self.bill_tree.heading("paid_on", text="Paid On")
        self.bill_tree.column("room", width=70, anchor="center")
        self.bill_tree.column("tenant", width=150)
        self.bill_tree.column("rent", width=90, anchor="e")
        self.bill_tree.column("elec", width=100, anchor="e")
        self.bill_tree.column("total", width=90, anchor="e")
        self.bill_tree.column("status", width=80, anchor="center")
        self.bill_tree.column("paid_on", width=100, anchor="center")
        self.bill_tree.pack(fill="both", expand=True)
        self.bill_tree.bind("<Double-1>", lambda e: self._edit_bill())

        # Color tags
        self.bill_tree.tag_configure("pending", background="#fff3cd")
        self.bill_tree.tag_configure("paid", background="#d4edda")

    def _prev_month(self):
        y, m = map(int, self.month_var.get().split("-"))
        m -= 1
        if m < 1:
            m = 12
            y -= 1
        self.month_var.set(f"{y:04d}-{m:02d}")
        self.refresh_bills()

    def _next_month(self):
        y, m = map(int, self.month_var.get().split("-"))
        m += 1
        if m > 12:
            m = 1
            y += 1
        self.month_var.set(f"{y:04d}-{m:02d}")
        self.refresh_bills()

    def refresh_bills(self):
        month = self.month_var.get().strip()
        for i in self.bill_tree.get_children():
            self.bill_tree.delete(i)

        bills = self.db.get_bills_for_month(month)
        pending_amt = 0
        collected = 0
        for b in bills:
            tag = b["status"]
            if b["status"] == "pending":
                pending_amt += b["total_amount"]
            else:
                collected += b["total_amount"]
            self.bill_tree.insert("", "end", iid=b["id"], tags=(tag,), values=(
                b["room_number"],
                b["tenant_name"] or "—",
                f"{b['rent_amount']:.0f}",
                f"{b['electricity_amount']:.0f}",
                f"{b['total_amount']:.0f}",
                b["status"].upper(),
                b["paid_on"] or ""
            ))

        self.bill_summary.config(
            text=f"Month: {month}   |   Pending: ₹ {pending_amt:.0f}   |   Collected: ₹ {collected:.0f}   |   Bills: {len(bills)}"
        )

    def _generate_bills(self):
        month = self.month_var.get().strip()
        rooms = self.db.get_rooms()
        if not rooms:
            messagebox.showinfo("No Rooms", "Add rooms first.")
            return
        count = 0
        for r in rooms:
            existing = self.db.conn.execute(
                "SELECT id FROM monthly_bills WHERE room_id=? AND month=?",
                (r["id"], month)).fetchone()
            if not existing:
                self.db.get_or_create_bill(r["id"], month, r["base_rent"], 0, 0)
                count += 1
        self.refresh_bills()
        messagebox.showinfo("Done", f"Generated {count} new bill(s) for {month}.\n(Existing bills were not changed.)")

    def _edit_bill(self):
        sel = self.bill_tree.selection()
        if not sel:
            messagebox.showinfo("Select", "Select a bill to edit.")
            return
        bill = self.db.get_bill(int(sel[0]))
        self._bill_dialog(bill)

    def _mark_paid(self):
        sel = self.bill_tree.selection()
        if not sel:
            messagebox.showinfo("Select", "Select a bill to mark as paid.")
            return
        bill_id = int(sel[0])
        bill = self.db.get_bill(bill_id)
        if bill["status"] == "paid":
            messagebox.showinfo("Already Paid", "This bill is already marked as paid.")
            return
        if messagebox.askyesno("Confirm", f"Mark Room {bill['room_number']} as PAID?\nTotal: ₹ {bill['total_amount']:.0f}"):
            self.db.mark_paid(bill_id)
            self.refresh_bills()

    def _bill_dialog(self, bill):
        dlg = tk.Toplevel(self)
        dlg.title(f"Edit Bill – Room {bill['room_number']} ({bill['month']})")
        dlg.geometry("360x300")
        dlg.transient(self)
        dlg.grab_set()
        dlg.configure(bg=self.bg)

        tk.Label(dlg, text=f"Tenant: {bill['tenant_name'] or '—'}", font=("Segoe UI", 11, "bold"),
                 bg=self.bg).pack(pady=(12, 8))

        form = tk.Frame(dlg, bg=self.bg)
        form.pack(padx=20, pady=4)

        tk.Label(form, text="Rent (₹):", bg=self.bg).grid(row=0, column=0, sticky="e", pady=6)
        rent_e = ttk.Entry(form, width=18)
        rent_e.grid(row=0, column=1, pady=6)
        rent_e.insert(0, str(bill["rent_amount"]))

        tk.Label(form, text="Electricity (₹):", bg=self.bg).grid(row=1, column=0, sticky="e", pady=6)
        elec_e = ttk.Entry(form, width=18)
        elec_e.grid(row=1, column=1, pady=6)
        elec_e.insert(0, str(bill["electricity_amount"]))

        tk.Label(form, text="Units (optional):", bg=self.bg).grid(row=2, column=0, sticky="e", pady=6)
        units_e = ttk.Entry(form, width=18)
        units_e.grid(row=2, column=1, pady=6)
        units_e.insert(0, str(bill["electricity_units"] or 0))

        tk.Label(form, text="Status:", bg=self.bg).grid(row=3, column=0, sticky="e", pady=6)
        status_var = tk.StringVar(value=bill["status"])
        ttk.Radiobutton(form, text="Pending", variable=status_var, value="pending").grid(row=3, column=1, sticky="w")
        ttk.Radiobutton(form, text="Paid", variable=status_var, value="paid").grid(row=4, column=1, sticky="w")

        def save():
            try:
                rent = float(rent_e.get() or 0)
                elec = float(elec_e.get() or 0)
                units = float(units_e.get() or 0)
            except ValueError:
                messagebox.showerror("Error", "Invalid numbers.", parent=dlg)
                return
            self.db.update_bill(bill["id"], rent, elec, units, status=status_var.get())
            self.refresh_bills()
            dlg.destroy()

        ttk.Button(dlg, text="Save", command=save).pack(pady=16)

    # ===================== REPORT TAB =====================
    def _build_report_tab(self):
        top = tk.Frame(self.tab_report, bg=self.bg)
        top.pack(fill="x", pady=(0, 8))
        tk.Label(top, text="Monthly Summary", font=("Segoe UI", 12, "bold"), bg=self.bg).pack(side="left")
        ttk.Button(top, text="🔄 Refresh", command=self._load_report).pack(side="right")

        self.report_summary = tk.Frame(self.tab_report, bg=self.bg)
        self.report_summary.pack(fill="x", pady=8)

        self.report_status = tk.Label(self.tab_report, text="", font=("Segoe UI", 10), bg=self.bg)
        self.report_status.pack(anchor="w")

        cols = ("room", "tenant", "rent", "elec", "total", "status")
        self.report_tree = ttk.Treeview(self.tab_report, columns=cols, show="headings", height=14)
        self.report_tree.heading("room", text="Room")
        self.report_tree.heading("tenant", text="Tenant")
        self.report_tree.heading("rent", text="Rent ₹")
        self.report_tree.heading("elec", text="Electricity ₹")
        self.report_tree.heading("total", text="Total ₹")
        self.report_tree.heading("status", text="Status")
        for c, w in zip(cols, [70, 160, 90, 100, 90, 80]):
            self.report_tree.column(c, width=w, anchor="center" if c != "tenant" else "w")
        self.report_tree.pack(fill="both", expand=True)
        self.report_tree.tag_configure("pending", background="#fff3cd")
        self.report_tree.tag_configure("paid", background="#d4edda")

        self._load_report()

    def _load_report(self):
        for w in self.report_summary.winfo_children():
            w.destroy()
        for i in self.report_tree.get_children():
            self.report_tree.delete(i)

        month = self.month_var.get() if hasattr(self, "month_var") else date.today().strftime("%Y-%m")
        summary = self.db.get_pending_summary(month)
        bills = self.db.get_bills_for_month(month)

        def card(parent, title, value, color):
            f = tk.Frame(parent, bg=color, padx=14, pady=10)
            f.pack(side="left", padx=6)
            tk.Label(f, text=title, font=("Segoe UI", 9), bg=color, fg="white").pack()
            tk.Label(f, text=value, font=("Segoe UI", 15, "bold"), bg=color, fg="white").pack()

        card(self.report_summary, "Total Bills", str(summary["total_bills"] or 0), self.primary)
        card(self.report_summary, "Pending", str(summary["pending_count"] or 0), self.warning)
        card(self.report_summary, "Paid", str(summary["paid_count"] or 0), self.success)
        card(self.report_summary, "Pending ₹", f"{summary['pending_amount'] or 0:.0f}", self.danger)
        card(self.report_summary, "Collected ₹", f"{summary['collected_amount'] or 0:.0f}", self.success)

        for b in bills:
            self.report_tree.insert("", "end", tags=(b["status"],), values=(
                b["room_number"],
                b["tenant_name"] or "—",
                f"{b['rent_amount']:.0f}",
                f"{b['electricity_amount']:.0f}",
                f"{b['total_amount']:.0f}",
                b["status"].upper()
            ))

        self.report_status.config(text=f"Showing data for {month}")


if __name__ == "__main__":
    app = KirayedaarApp()
    app.mainloop()
from kivy.app import App
from kivy.uix.button import Button
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label

class MyApp(App):
    def build(self):
        layout = BoxLayout(orientation='vertical', padding=20, spacing=15)
        
        self.label = Label(
            text="Hello! This is my first Python Android app",
            font_size=22
        )
        
        button = Button(
            text="Click Me!",
            size_hint=(1, 0.3),
            font_size=24
        )
        button.bind(on_press=self.on_button_click)
        
        layout.add_widget(self.label)
        layout.add_widget(button)
        
        return layout

    def on_button_click(self, instance):
        self.label.text = "Button clicked! 🎉"

if __name__ == "__main__":
    MyApp().run()