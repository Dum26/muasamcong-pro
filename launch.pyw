"""Khởi động bằng pythonw, hiển thị thông báo nếu không mở được ứng dụng."""
import os
from pathlib import Path
import traceback

folder = Path(__file__).resolve().parent
os.chdir(folder)
try:
    from app import App
    App().mainloop()
except Exception:
    report = traceback.format_exc()
    (folder / "startup_error.log").write_text(report, encoding="utf-8")
    import tkinter as tk
    from tkinter import messagebox
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror("Không mở được MuaSamCong", "Chi tiết lỗi được lưu tại:\n" + str(folder / "startup_error.log") + "\n\n" + report.splitlines()[-1])
    root.destroy()
