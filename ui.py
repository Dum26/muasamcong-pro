"""Giao diện desktop cho MuaSamCong; không chứa logic truy vấn dữ liệu."""

from __future__ import annotations

import os
import tkinter as tk
from datetime import date
from tkinter import messagebox, ttk
from typing import Any, Callable


# Bảng màu trung tính pha xanh ngọc, ưu tiên độ tương phản khi đọc dữ liệu lâu.
BG = "#F3F6FA"
SURFACE = "#FFFFFF"
SURFACE_ALT = "#F7F9FC"
INK = "#10233D"
MUTED = "#71839B"
NAVY = "#0B2239"
NAVY_SOFT = "#14334D"
TEAL = "#078B82"
TEAL_DARK = "#066F69"
TEAL_SOFT = "#E3F5F1"
BLUE_SOFT = "#EAF1FF"
BORDER = "#DDE6EF"
BORDER_STRONG = "#CAD7E3"


def build_style(app: Any) -> None:
    style = ttk.Style(app)
    style.theme_use("clam")
    app.configure(background=BG)

    app.option_add("*TCombobox*Listbox.background", SURFACE)
    app.option_add("*TCombobox*Listbox.selectBackground", TEAL_SOFT)
    app.option_add("*TCombobox*Listbox.selectForeground", INK)
    app.option_add("*TCombobox*Listbox.font", ("Segoe UI", 10))

    style.configure(".", font=("Segoe UI", 10), background=SURFACE, foreground=INK)
    style.configure("TFrame", background=SURFACE)
    style.configure("Page.TFrame", background=BG)
    style.configure("Filter.TFrame", background=SURFACE_ALT)
    style.configure("TLabel", background=SURFACE, foreground=INK)
    style.configure("Muted.TLabel", background=SURFACE, foreground=MUTED)
    style.configure(
        "Field.TLabel",
        background=SURFACE,
        foreground="#536A84",
        font=("Segoe UI", 8, "bold"),
    )
    style.configure(
        "Filter.TLabel",
        background=SURFACE_ALT,
        foreground=MUTED,
        font=("Segoe UI", 9),
    )
    style.configure(
        "Section.TLabel",
        background=SURFACE,
        foreground=INK,
        font=("Segoe UI", 15, "bold"),
    )
    style.configure(
        "Count.TLabel",
        background=TEAL_SOFT,
        foreground=TEAL_DARK,
        padding=(12, 6),
        font=("Segoe UI", 9, "bold"),
    )

    style.configure(
        "TButton",
        background="#EDF2F7",
        foreground="#38516B",
        padding=(15, 10),
        borderwidth=0,
        focusthickness=0,
        font=("Segoe UI", 9),
    )
    style.map(
        "TButton",
        background=[("pressed", "#D7E2EC"), ("active", "#E2EAF2")],
        foreground=[("disabled", "#A5B2BF")],
    )
    style.configure(
        "Primary.TButton",
        background=TEAL,
        foreground="white",
        font=("Segoe UI", 10, "bold"),
        padding=(21, 12),
    )
    style.map(
        "Primary.TButton",
        background=[
            ("disabled", "#9ABFBB"),
            ("pressed", "#055F5A"),
            ("active", TEAL_DARK),
        ],
        foreground=[("disabled", "white"), ("active", "white")],
    )
    style.configure(
        "Secondary.TButton",
        background=BLUE_SOFT,
        foreground="#315B9C",
        padding=(16, 10),
        font=("Segoe UI", 9, "bold"),
    )
    style.map(
        "Secondary.TButton",
        background=[("pressed", "#D6E3FA"), ("active", "#DEE9FC")],
    )
    style.configure(
        "Ghost.TButton",
        background=SURFACE,
        foreground="#526A83",
        padding=(12, 9),
    )
    style.map("Ghost.TButton", background=[("active", "#F1F5F9")])

    style.configure(
        "TEntry",
        fieldbackground="#FAFCFE",
        foreground=INK,
        insertcolor=INK,
        bordercolor=BORDER_STRONG,
        lightcolor=BORDER_STRONG,
        darkcolor=BORDER_STRONG,
        padding=(11, 10),
        borderwidth=1,
    )
    style.map(
        "TEntry",
        bordercolor=[("focus", TEAL)],
        lightcolor=[("focus", TEAL)],
        darkcolor=[("focus", TEAL)],
    )
    style.configure(
        "TCombobox",
        fieldbackground="#FAFCFE",
        background="#EEF3F8",
        foreground=INK,
        bordercolor=BORDER_STRONG,
        lightcolor=BORDER_STRONG,
        darkcolor=BORDER_STRONG,
        arrowcolor="#647B93",
        padding=(10, 9),
        borderwidth=1,
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", "#FAFCFE")],
        selectbackground=[("readonly", "#FAFCFE")],
        selectforeground=[("readonly", INK)],
        bordercolor=[("focus", TEAL)],
    )
    style.configure(
        "TSpinbox",
        fieldbackground=SURFACE,
        bordercolor=BORDER_STRONG,
        lightcolor=BORDER_STRONG,
        darkcolor=BORDER_STRONG,
        padding=(8, 7),
        arrowsize=12,
    )
    style.configure(
        "TCheckbutton",
        background=SURFACE,
        foreground="#526A83",
        padding=(0, 4),
        font=("Segoe UI", 9),
        indicatorcolor=SURFACE,
        indicatorrelief="flat",
    )
    style.map(
        "TCheckbutton",
        background=[("active", SURFACE)],
        indicatorcolor=[("selected", TEAL), ("!selected", SURFACE)],
        indicatorrelief=[("pressed", "flat")],
    )
    style.configure(
        "Filter.TCheckbutton",
        background=SURFACE_ALT,
        foreground="#526A83",
        padding=(0, 4),
        font=("Segoe UI", 9),
        indicatorcolor=SURFACE,
    )
    style.map(
        "Filter.TCheckbutton",
        background=[("active", SURFACE_ALT)],
        indicatorcolor=[("selected", TEAL), ("!selected", SURFACE)],
    )

    style.configure(
        "Treeview",
        background=SURFACE,
        fieldbackground=SURFACE,
        foreground="#2E455E",
        rowheight=45,
        borderwidth=0,
        relief="flat",
        font=("Segoe UI", 9),
    )
    style.configure(
        "Treeview.Heading",
        background="#F3F7FA",
        foreground="#526B85",
        padding=(12, 13),
        borderwidth=0,
        relief="flat",
        font=("Segoe UI", 8, "bold"),
    )
    style.map("Treeview.Heading", background=[("active", "#E9F0F5")])
    style.map(
        "Treeview",
        background=[("selected", "#DDF3EF")],
        foreground=[("selected", "#075F5A")],
    )
    style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    style.configure(
        "TScrollbar",
        background="#D1DCE6",
        troughcolor="#F3F6F9",
        borderwidth=0,
        arrowsize=12,
        arrowcolor="#7890A7",
    )
    style.configure(
        "Horizontal.TProgressbar",
        background=TEAL,
        troughcolor=BG,
        lightcolor=TEAL,
        darkcolor=TEAL,
        borderwidth=0,
        thickness=3,
    )
    style.configure("TSeparator", background=BORDER)


def _card(parent: Any) -> tuple[tk.Frame, tk.Frame]:
    """Tạo card viền mảnh, trả về (khung ngoài, nội dung)."""
    shell = tk.Frame(parent, background=BORDER, bd=0, highlightthickness=0)
    body = tk.Frame(shell, background=SURFACE, bd=0)
    body.pack(fill="both", expand=True, padx=1, pady=1)
    return shell, body


def _hover_nav(
    widgets: tuple[tk.Widget, ...],
    normal: str,
    hover: str,
    active: bool,
) -> None:
    if active:
        return

    def paint(color: str) -> Callable[[Any], None]:
        def handler(_event: Any) -> None:
            for widget in widgets:
                widget.configure(background=color)

        return handler

    for widget in widgets:
        widget.bind("<Enter>", paint(hover), add="+")
        widget.bind("<Leave>", paint(normal), add="+")


def build_ui(app: Any, date_entry: Any, download_dir: Any) -> None:
    app.columnconfigure(1, weight=1)
    app.rowconfigure(0, weight=1)

    sidebar = tk.Frame(app, background=NAVY, width=220, bd=0)
    sidebar.grid(row=0, column=0, sticky="ns")
    sidebar.grid_propagate(False)

    brand = tk.Frame(sidebar, background=NAVY)
    brand.pack(fill="x", padx=22, pady=(25, 24))
    logo = tk.Canvas(brand, width=44, height=44, background=NAVY, highlightthickness=0)
    logo.pack(anchor="w")
    logo.create_rectangle(1, 1, 43, 43, fill=TEAL, outline=TEAL)
    logo.create_text(22, 22, text="M", fill="white", font=("Segoe UI", 21, "bold"))
    tk.Label(brand, text="MuaSamCong", background=NAVY, foreground="white",
             font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(12, 2))
    tk.Label(brand, text="TRUNG TÂM TRA CỨU DỮ LIỆU", background=NAVY,
             foreground="#82A3BD", font=("Segoe UI", 7, "bold")).pack(anchor="w")

    tk.Frame(sidebar, background="#244059", height=1).pack(fill="x", padx=22)
    tk.Label(sidebar, text="KHÔNG GIAN LÀM VIỆC", background=NAVY,
             foreground="#718FA9", font=("Segoe UI", 7, "bold")).pack(
                 anchor="w", padx=24, pady=(24, 11))

    def nav(icon: str, text: str, command: Any, active: bool = False) -> None:
        normal = "#174059" if active else NAVY
        hover = "#12314A"
        row = tk.Frame(sidebar, background=normal, cursor="hand2")
        row.pack(fill="x", padx=12, pady=3)
        accent = tk.Frame(row, width=3, background="#51D2C3" if active else normal)
        accent.pack(side="left", fill="y")
        icon_label = tk.Label(row, text=icon, width=3, anchor="center",
                              background=normal, foreground="#69D8CC" if active else "#8EABBF",
                              font=("Segoe UI Symbol", 10, "bold"), cursor="hand2")
        icon_label.pack(side="left", padx=(8, 1), pady=12)
        text_label = tk.Label(row, text=text, anchor="w", background=normal,
                              foreground="#E7F4F7" if active else "#B9CBD8",
                              font=("Segoe UI", 9, "bold" if active else "normal"), cursor="hand2")
        text_label.pack(side="left", fill="x", expand=True, padx=(2, 8), pady=12)
        widgets = (row, icon_label, text_label)
        for widget in widgets:
            widget.bind("<Button-1>", lambda _event, action=command: action())
        _hover_nav(widgets, normal, hover, active)

    nav("⌕", "Tra cứu đấu thầu", lambda: app.keyword_entry.focus_set(), True)
    nav("⇩", "Xuất bảng kết quả", app.export_excel)

    def open_download_folder() -> None:
        try:
            download_dir.mkdir(parents=True, exist_ok=True)
            os.startfile(str(download_dir))
        except OSError as exc:
            messagebox.showerror("Mở thư mục", f"Không mở được {download_dir}: {exc}", parent=app)

    nav("↗", "Thư mục đã tải", open_download_folder)

    side_bottom = tk.Frame(sidebar, background=NAVY_SOFT, padx=16, pady=15)
    side_bottom.pack(side="bottom", fill="x", padx=13, pady=18)
    tk.Label(side_bottom, text="NƠI LƯU PHÂN LÔ", background=NAVY_SOFT,
             foreground="#82A3BD", font=("Segoe UI", 7, "bold")).pack(anchor="w")
    tk.Label(side_bottom, text=str(download_dir), background=NAVY_SOFT,
             foreground="#F0F8FA", font=("Segoe UI", 11, "bold"),
             wraplength=160, justify="left").pack(anchor="w", pady=(6, 5))
    tk.Label(side_bottom, text="●  Tự động lưu khi tải file", background=NAVY_SOFT,
             foreground="#72CFC5", font=("Segoe UI", 8)).pack(anchor="w")

    page = ttk.Frame(app, style="Page.TFrame", padding=(26, 20, 26, 12))
    page.grid(row=0, column=1, sticky="nsew")
    page.columnconfigure(0, weight=1)
    page.rowconfigure(2, weight=1)

    header = tk.Frame(page, background=BG)
    header.grid(row=0, column=0, sticky="ew", pady=(0, 18))
    header.columnconfigure(0, weight=1)
    title_box = tk.Frame(header, background=BG)
    title_box.grid(row=0, column=0, sticky="w")
    tk.Label(title_box, text="Tra cứu đấu thầu", background=BG, foreground=INK,
             font=("Segoe UI", 24, "bold")).pack(anchor="w")
    tk.Label(title_box,
             text="Tìm đúng kế hoạch  •  Kiểm tra nhanh  •  Xuất dữ liệu trong một bước",
             background=BG, foreground=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 0))
    live = tk.Frame(header, background="#E7F4F1", padx=12, pady=8)
    live.grid(row=0, column=1, sticky="e")
    tk.Label(live, text="●", background="#E7F4F1", foreground=TEAL,
             font=("Segoe UI", 8, "bold")).pack(side="left", padx=(0, 6))
    tk.Label(live, text="Dữ liệu trực tiếp từ e-GP", background="#E7F4F1",
             foreground=TEAL_DARK, font=("Segoe UI", 8, "bold")).pack(side="left")

    search_shell, search = _card(page)
    search_shell.grid(row=1, column=0, sticky="ew", pady=(0, 17))
    search.columnconfigure(0, weight=0)
    search.columnconfigure(1, weight=1)
    search.columnconfigure(2, weight=0)

    search_head = tk.Frame(search, background=SURFACE)
    search_head.grid(row=0, column=0, columnspan=3, sticky="ew", padx=20, pady=(15, 12))
    search_head.columnconfigure(1, weight=1)
    tk.Label(search_head, text="01", width=3, height=1, background=TEAL_SOFT,
             foreground=TEAL_DARK, font=("Segoe UI", 10, "bold"), padx=4, pady=5).grid(
                 row=0, column=0, rowspan=2, sticky="w", padx=(0, 11))
    tk.Label(search_head, text="Thiết lập truy vấn", background=SURFACE, foreground=INK,
             font=("Segoe UI", 13, "bold")).grid(row=0, column=1, sticky="sw")
    tk.Label(search_head, text="Chọn nguồn dữ liệu và nhập nội dung cần tìm",
             background=SURFACE, foreground=MUTED, font=("Segoe UI", 8)).grid(
                 row=1, column=1, sticky="nw", pady=(2, 0))
    tk.Label(search_head, text="HTLCNT ĐƯỢC ĐỒNG BỘ TỰ ĐỘNG", background=SURFACE,
             foreground="#7890A6", font=("Segoe UI", 7, "bold")).grid(
                 row=0, column=2, rowspan=2, sticky="e")
    ttk.Separator(search).grid(row=1, column=0, columnspan=3, sticky="ew")

    ttk.Label(search, text="LOẠI THÔNG TIN", style="Field.TLabel").grid(
        row=2, column=0, sticky="w", padx=(20, 0), pady=(13, 6))
    app.keyword_label_var = tk.StringVar(value="TỪ KHÓA HOẶC MÃ KHLCNT")
    ttk.Label(search, textvariable=app.keyword_label_var, style="Field.TLabel").grid(
        row=2, column=1, sticky="w", padx=(14, 0), pady=(13, 6))
    ttk.Combobox(search, textvariable=app.search_mode_var,
                 values=["Kế hoạch lựa chọn nhà thầu", "Thông báo mời thầu"],
                 state="readonly", width=29).grid(row=3, column=0, sticky="ew", padx=(20, 0))
    app.keyword_entry = ttk.Entry(search, textvariable=app.keyword_var)
    app.keyword_entry.grid(row=3, column=1, sticky="ew", padx=(14, 12))
    app.keyword_entry.bind("<Return>", lambda _event: app.start_search())
    app.search_btn = ttk.Button(search, text="Tìm kiếm   →", style="Primary.TButton",
                                command=app.start_search)
    app.search_btn.grid(row=3, column=2, sticky="ew", padx=(0, 20))

    filter_bar = ttk.Frame(search, style="Filter.TFrame", padding=(14, 10))
    filter_bar.grid(row=4, column=0, columnspan=3, sticky="ew", padx=20, pady=(14, 15))
    top_filters = ttk.Frame(filter_bar, style="Filter.TFrame")
    top_filters.pack(fill="x")
    filter_toggle = ttk.Checkbutton(top_filters, text="Lọc theo ngày",
                                    variable=app.use_date_filter_var,
                                    style="Filter.TCheckbutton")
    filter_toggle.pack(side="left", padx=(0, 13))

    date_widgets: list[Any] = []
    for label, variable, attribute, day in (
        ("Từ", app.date_from_var, "date_from_widget", 1),
        ("Đến", app.date_to_var, "date_to_widget", date.today().day),
    ):
        ttk.Label(top_filters, text=label, style="Filter.TLabel").pack(side="left", padx=(0, 7))
        if date_entry is not None:
            widget = date_entry(top_filters, textvariable=variable, width=11,
                                date_pattern="dd/mm/yyyy", locale="vi_VN", firstweekday="monday",
                                year=date.today().year, month=date.today().month, day=day,
                                background=TEAL, foreground="white", borderwidth=0,
                                headersbackground="#EFF5F8", headersforeground=INK,
                                selectbackground=TEAL, selectforeground="white")
        else:
            widget = ttk.Entry(top_filters, textvariable=variable, width=12)
        setattr(app, attribute, widget)
        widget.pack(side="left", padx=(0, 13))
        date_widgets.append(widget)

    ttk.Button(top_filters, text="Làm mới", style="Ghost.TButton", command=app.reset).pack(side="right")
    ttk.Spinbox(top_filters, from_=1, to=50, textvariable=app.pages_var, width=4).pack(
        side="right", padx=(8, 0))
    ttk.Label(top_filters, text="Số trang tối đa", style="Filter.TLabel").pack(side="right")
    ttk.Separator(filter_bar).pack(fill="x", pady=(8, 6))
    bottom_filters = ttk.Frame(filter_bar, style="Filter.TFrame")
    bottom_filters.pack(fill="x")
    ttk.Checkbutton(bottom_filters, text="Loại bỏ kết quả trùng lặp",
                    variable=app.remove_dup_var, style="Filter.TCheckbutton").pack(
                        side="left", padx=(0, 20))
    ttk.Checkbutton(bottom_filters, text="Lấy chi tiết KQLCNT", variable=app.detail_var,
                    style="Filter.TCheckbutton").pack(side="left")
    detail_hint = ttk.Label(
        bottom_filters,
        text="Bật chi tiết có thể làm thời gian tìm kiếm lâu hơn",
        style="Filter.TLabel",
    )
    detail_hint.pack(side="right")
    status_group = ttk.Frame(bottom_filters, style="Filter.TFrame")
    ttk.Label(status_group, text="Trạng thái TBMT", style="Filter.TLabel").pack(
        side="left", padx=(0, 7)
    )
    app.notice_status_combo = ttk.Combobox(
        status_group,
        textvariable=app.notice_status_var,
        values=[
            "Tất cả trạng thái",
            "Chưa đóng thầu",
            "Chưa mở thầu",
            "Đang xét thầu",
            "Có nhà thầu trúng thầu",
            "Không có nhà thầu trúng thầu",
            "Đã hủy TBMT",
            "Đã hủy thầu",
            "Đã hủy KQLCNT",
            "Tuyên bố vô hiệu quyết định về KQLCNT",
            "Không công nhận KQLCNT",
            "Chưa xác định",
        ],
        state="readonly",
        width=22,
    )
    app.notice_status_combo.pack(side="left")

    def sync_date_widgets() -> None:
        state = "normal" if app.use_date_filter_var.get() else "disabled"
        for widget in date_widgets:
            try:
                widget.configure(state=state)
            except tk.TclError:
                pass

    filter_toggle.configure(command=sync_date_widgets)
    sync_date_widgets()

    results_shell, results = _card(page)
    results_shell.grid(row=2, column=0, sticky="nsew")
    results.columnconfigure(0, weight=1)
    results.rowconfigure(2, weight=1)

    toolbar = tk.Frame(results, background=SURFACE)
    toolbar.grid(row=0, column=0, sticky="ew", padx=19, pady=(13, 12))
    toolbar.columnconfigure(2, weight=1)
    tk.Label(toolbar, text="Kết quả tra cứu", background=SURFACE, foreground=INK,
             font=("Segoe UI", 14, "bold")).grid(row=0, column=0, sticky="w")
    ttk.Label(toolbar, textvariable=app.count_var, style="Count.TLabel").grid(
        row=0, column=1, sticky="w", padx=(12, 0))
    app.selection_var = tk.StringVar(value="Chưa chọn dòng")
    tk.Label(toolbar, textvariable=app.selection_var, background=SURFACE, foreground=MUTED,
             font=("Segoe UI", 9)).grid(row=0, column=3, sticky="e")
    ttk.Separator(results).grid(row=1, column=0, sticky="ew")

    table = ttk.Frame(results)
    table.grid(row=2, column=0, sticky="nsew", padx=(10, 7))
    table.columnconfigure(0, weight=1)
    table.rowconfigure(0, weight=1)
    columns = (
        "stt", "notify_no", "plan_no", "plan_name", "package_name", "public_date",
        "bid_close_date", "tender_status", "location", "decision_date", "winner",
        "bid_form", "investor", "lot_file",
    )
    app.tree = ttk.Treeview(table, columns=columns, show="headings", height=5,
                            selectmode="extended")
    plan_display_columns = (
        "stt", "plan_no", "lot_file", "plan_name", "bid_form", "public_date",
        "package_name", "decision_date", "winner", "investor",
    )
    notice_display_columns = (
        "stt", "notify_no", "tender_status", "bid_close_date", "location",
        "package_name", "bid_form", "public_date", "plan_no", "investor",
        "lot_file", "winner",
    )
    app.tree.configure(displaycolumns=plan_display_columns)
    app.tree.tag_configure("alternate", background="#F8FAFC")
    app.tree.bind("<Double-1>", app._copy_clicked_cell)
    app.tree.bind("<Button-3>", app._show_copy_menu)
    app.tree.bind("<Control-c>", lambda _event: app.copy_selected_rows())
    app.tree.bind("<Control-C>", lambda _event: app.copy_selected_rows())
    app.tree.bind("<Control-a>", app._select_all_rows)
    app.tree.bind("<<TreeviewSelect>>", lambda _event: app.selection_var.set(
        f"Đã chọn {len(app.tree.selection())} dòng" if app.tree.selection() else "Chưa chọn dòng"))
    headings = {
        "stt": ("STT", 48), "plan_no": ("MÃ KHLCNT", 145),
        "notify_no": ("MÃ TBMT", 155),
        "lot_file": ("PHÂN LÔ", 105), "plan_name": ("TÊN KẾ HOẠCH / DỰ ÁN", 325),
        "bid_form": ("HÌNH THỨC LCNT", 190), "public_date": ("NGÀY ĐĂNG TẢI", 125),
        "bid_close_date": ("ĐÓNG THẦU", 155),
        "tender_status": ("TRẠNG THÁI", 155),
        "location": ("TỈNH / THÀNH PHỐ", 190),
        "package_name": ("TÊN GÓI THẦU", 300), "decision_date": ("NGÀY PHÊ DUYỆT", 135),
        "winner": ("NHÀ THẦU TRÚNG", 230), "investor": ("CHỦ ĐẦU TƯ", 240),
    }
    for key in columns:
        title, width = headings[key]
        app.tree.heading(key, text=title, command=lambda col=key: app.copy_column_values(col))
        centered = key in (
            "stt", "notify_no", "plan_no", "lot_file", "public_date",
            "bid_close_date", "tender_status", "decision_date",
        )
        app.tree.column(key, width=width, minwidth=width if centered else 120,
                        stretch=not centered, anchor="center" if centered else "w")
    app.tree.grid(row=0, column=0, sticky="nsew")
    ybar = ttk.Scrollbar(table, orient="vertical", command=app.tree.yview)
    xbar = ttk.Scrollbar(table, orient="horizontal", command=app.tree.xview)
    app.tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
    ybar.grid(row=0, column=1, sticky="ns")
    xbar.grid(row=1, column=0, sticky="ew")

    app.empty_state = tk.Frame(table, background=SURFACE)
    empty_badge = tk.Label(app.empty_state, text="⌕", width=3, height=1,
                           background=TEAL_SOFT, foreground=TEAL,
                           font=("Segoe UI Symbol", 25), padx=3, pady=5)
    empty_badge.pack(pady=(0, 13))
    app.empty_title_var = tk.StringVar(value="Bắt đầu với một từ khóa")
    app.empty_hint_var = tk.StringVar(
        value="Nhập tên gói thầu hoặc mã KHLCNT rồi nhấn Tìm kiếm.")
    empty_title = tk.Label(app.empty_state, textvariable=app.empty_title_var,
                           background=SURFACE, foreground=INK,
                           font=("Segoe UI", 14, "bold"))
    empty_title.pack(pady=(0, 6))
    tk.Label(app.empty_state, textvariable=app.empty_hint_var, background=SURFACE,
             foreground=MUTED, font=("Segoe UI", 9)).pack()

    def fit_empty_state(event: Any) -> None:
        if event.height < 210:
            empty_badge.pack_forget()
        elif not empty_badge.winfo_manager():
            empty_badge.pack(before=empty_title, pady=(0, 13))

    table.bind("<Configure>", fit_empty_state)
    app.empty_state.place(relx=0.5, rely=0.53, anchor="center")

    ttk.Separator(results).grid(row=3, column=0, sticky="ew")
    actions = tk.Frame(results, background=SURFACE)
    actions.grid(row=4, column=0, sticky="ew", padx=16, pady=10)
    tk.Label(actions, text="MẸO  •  Nhấp đúp để copy ô  ·  Nhấp tiêu đề để copy cột",
             background=SURFACE, foreground="#8091A4", font=("Segoe UI", 8)).pack(side="left")
    app.download_btn = ttk.Button(actions, text="↓  Tải phân lô", style="Primary.TButton",
                                  command=app.download_lot_lists)
    app.download_btn.pack(side="right", padx=(9, 0))
    ttk.Button(actions, text="Xuất Excel", style="Secondary.TButton",
               command=app.export_excel).pack(side="right", padx=(9, 0))
    ttk.Button(actions, text="Copy mã đã chọn", style="Ghost.TButton",
               command=lambda: app.copy_codes(selected_only=True)).pack(side="right", padx=(9, 0))
    ttk.Button(actions, text="Copy tất cả mã", style="Ghost.TButton",
               command=app.copy_codes).pack(side="right")

    progress_track = ttk.Frame(page, height=3, style="Page.TFrame")
    progress_track.grid(row=3, column=0, sticky="ew", pady=(7, 5))
    progress_track.pack_propagate(False)
    app.progress_bar = ttk.Progressbar(progress_track, mode="indeterminate")
    app.progress_bar.pack(fill="both", expand=True)

    footer = tk.Frame(page, background=BG)
    footer.grid(row=4, column=0, sticky="ew")
    app.status_label = tk.Label(footer, textvariable=app.status_var, background=BG,
                                foreground=MUTED, font=("Segoe UI", 8), anchor="w", width=1)
    app.status_label.pack(side="left", fill="x", expand=True)
    tk.Label(footer,
             text="Ctrl+K  tìm nhanh   ·   Ctrl+C  sao chép   ·   Ctrl+A  chọn tất cả",
             background=BG, foreground=MUTED, font=("Segoe UI", 8)).pack(side="right")

    app.copy_menu = tk.Menu(app, tearoff=False, font=("Segoe UI", 10),
                            background=SURFACE, foreground=INK,
                            activebackground=TEAL_SOFT, activeforeground=INK,
                            borderwidth=1, relief="solid")
    app.copy_menu.add_command(label="Sao chép cả cột", command=app.copy_column_values)
    app.copy_menu.add_command(label="Sao chép cột · dòng đã chọn",
                              command=lambda: app.copy_column_values(selected_only=True))
    app.copy_menu.add_separator()
    app.copy_menu.add_command(label="Sao chép ô này",
                              command=lambda: app._put_clipboard(app.copy_cell_value, "Đã sao chép ô"))
    app.copy_menu.add_command(label="Sao chép dòng đã chọn   Ctrl+C",
                              command=app.copy_selected_rows)
    app.copy_menu.add_command(label="Sao chép mã đã chọn",
                              command=lambda: app.copy_codes(selected_only=True))
    app.copy_menu.add_separator()
    app.copy_menu.add_command(label="Tải danh sách phân lô", command=app.download_lot_lists)
    app.copy_menu.add_command(label="Sao chép tất cả mã", command=app.copy_codes)
    app.column_menu = tk.Menu(app, tearoff=False, font=("Segoe UI", 10),
                              background=SURFACE, foreground=INK,
                              activebackground=TEAL_SOFT, activeforeground=INK)
    app.column_menu.add_command(label="Sao chép cả cột", command=app.copy_column_values)
    app.column_menu.add_command(label="Sao chép cột · dòng đã chọn",
                                command=lambda: app.copy_column_values(selected_only=True))

    def focus_search(_event: Any = None) -> str:
        app.keyword_entry.focus_set()
        app.keyword_entry.selection_range(0, "end")
        return "break"

    app.bind("<Control-k>", focus_search)
    app.bind("<Control-K>", focus_search)

    def sync_search_mode(*_args: Any) -> None:
        notice_mode = app.search_mode_var.get() == "Thông báo mời thầu"
        if notice_mode:
            app.keyword_label_var.set("TỪ KHÓA / MÃ TBMT  ·  CÓ THỂ ĐỂ TRỐNG")
            app.search_btn.configure(text="Quét TBMT   →")
            app.tree.configure(displaycolumns=notice_display_columns)
            detail_hint.pack_forget()
            if not status_group.winfo_manager():
                status_group.pack(side="right")
        else:
            app.keyword_label_var.set("TỪ KHÓA HOẶC MÃ KHLCNT")
            app.search_btn.configure(text="Tìm kiếm   →")
            app.tree.configure(displaycolumns=plan_display_columns)
            status_group.pack_forget()
            if not detail_hint.winfo_manager():
                detail_hint.pack(side="right")

    app.search_mode_var.trace_add("write", sync_search_mode)
    sync_search_mode()
    app.after_idle(app.keyword_entry.focus_set)
