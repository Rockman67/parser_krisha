import sys
from cx_Freeze import setup, Executable
import os

# Определение пути к директории с приложением
if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

# Определение файлов, которые должны быть включены
include_files = [
    ('parser.ico', 'parser.ico')
]

# Определение опций для cx_Freeze
build_exe_options = {
    "packages": ["os", "sys", "sqlite3", "requests", "bs4", "pyperclip", "logging", "re", "shutil", "threading", "queue", "datetime", "tkinter", "urllib", "webbrowser"],
    "include_files": include_files,
    "excludes": []
}

# Определение базового типа приложения
base = None
if sys.platform == "win32":
    base = "Win32GUI"  # Для GUI-приложений на Tkinter

setup(
    name = "Парсер Krisha",
    version = "1.0",
    description = "Программа для парсинга Krisha",
    options = {"build_exe": build_exe_options},
    executables = [Executable("parser_gui.py", base=base, icon="parser.ico")]
)
