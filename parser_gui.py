import sys
import subprocess
import logging
import os
import sqlite3  # Импорт sqlite3 для работы с базой данных
from importlib import metadata
import threading  # Для многопоточности
import queue  # Для очереди сообщений между потоками
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from tkinter import ttk  # Для прогресс-бара
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import re
import shutil
import pyperclip
from urllib.parse import urljoin

# Определение пути к директории с исполняемым файлом
if getattr(sys, 'frozen', False):
    # Если программа упакована PyInstaller
    application_path = os.path.dirname(sys.executable)
else:
    # Если программа запущена из исходного кода
    application_path = os.path.dirname(os.path.abspath(__file__))

# Настройка логирования
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

# Создание обработчика для записи в файл с нужной кодировкой
log_file = os.path.join(application_path, 'parser_log.txt')
handler = logging.FileHandler(log_file, encoding='utf-8')
handler.setLevel(logging.DEBUG)

# Создание формата логирования
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

# Добавление обработчика к логгеру
logger.addHandler(handler)

# Функция для инициализации базы данных
def init_db():
    db_path = os.path.join(application_path, 'parsing_history.db')
    # Установите check_same_thread=False, чтобы разрешить доступ из нескольких потоков
    conn = sqlite3.connect(db_path, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            time TEXT NOT NULL,
            client_number TEXT NOT NULL,
            url TEXT NOT NULL
        )
    ''')
    conn.commit()
    return conn

# Инициализация базы данных
conn = init_db()

# Создание очереди для сообщений между потоками
update_queue = queue.Queue()

# Валидация URL
def is_valid_url(url):
    regex = re.compile(
        r'^(?:http|ftp)s?://'  # протокол
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'  # доменное имя
        r'localhost|'  # localhost
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # IP-адрес
        r'(?::\d+)?'  # порт
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    return re.match(regex, url) is not None

# Функция для очистки папки
def clear_folder(folder_path):
    if os.path.exists(folder_path):
        for file in os.listdir(folder_path):
            file_path = os.path.join(folder_path, file)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                logging.error(f'Не удалось удалить {file_path}. Причина: {e}')
        logging.info(f'Папка {folder_path} успешно очищена.')
    else:
        logging.warning(f'Папка {folder_path} не найдена.')

# Функция для сохранения истории в базу данных
def save_history(client_number, url, time):
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO history (time, client_number, url)
            VALUES (?, ?, ?)
        ''', (time, client_number, url))
        conn.commit()
        logging.info(f'История сохранена: Клиент {client_number}, Ссылка {url}')
    except Exception as e:
        logging.error(f'Не удалось сохранить историю: {e}')

# Создание главного окна
root = tk.Tk()
root.title("Парсер Кришa")
root.geometry("1000x800")  # Увеличенный размер для размещения новых элементов

# Создание Canvas и Scrollbar для прокрутки
main_canvas = tk.Canvas(root, borderwidth=0)
scrollbar = tk.Scrollbar(root, orient="vertical", command=main_canvas.yview)
main_canvas.configure(yscrollcommand=scrollbar.set)

scrollbar.pack(side="right", fill="y")
main_canvas.pack(side="left", fill="both", expand=True)

# Создание внутреннего фрейма
content_frame = tk.Frame(main_canvas)
main_canvas.create_window((0, 0), window=content_frame, anchor='nw')

# Обновление области прокрутки при изменении размера контента
def on_frame_configure(event):
    main_canvas.configure(scrollregion=main_canvas.bbox("all"))

content_frame.bind("<Configure>", on_frame_configure)

# Создание вкладок
notebook = ttk.Notebook(content_frame)
notebook.pack(pady=10, padx=10, fill='both', expand=True)

# Вкладка "Основная"
main_tab = ttk.Frame(notebook)
notebook.add(main_tab, text='Основная')

# Вкладка "Отчёты"
reports_tab = ttk.Frame(notebook)
notebook.add(reports_tab, text='Отчёты')

# Вкладка "Логи"
logs_tab = ttk.Frame(notebook)
notebook.add(logs_tab, text='Логи')

# Вкладка "Описание"
description_tab = ttk.Frame(notebook)
notebook.add(description_tab, text='Описание')

# ----- Вкладка "Основная" -----
# Фрейм для ввода URL и кнопки "Вставить"
url_frame = tk.Frame(main_tab)
url_frame.pack(pady=10, padx=10, anchor='w')

# Метка для URL
tk.Label(url_frame, text="Ссылка для парсинга:", font=('Arial', 12)).pack(side=tk.LEFT, padx=5)

# Поле ввода URL
entry_url = tk.Entry(url_frame, width=60, font=('Arial', 12))
entry_url.pack(side=tk.LEFT, padx=5)

# Кнопка "Вставить" для вставки URL из буфера обмена
def paste_url():
    try:
        clipboard_content = root.clipboard_get()
        entry_url.delete(0, tk.END)  # Очистка текущего содержимого
        entry_url.insert(0, clipboard_content)  # Вставка содержимого буфера обмена
        logging.info("URL вставлен из буфера обмена.")
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось вставить URL: {e}")
        logging.error(f"Не удалось вставить URL из буфера обмена: {e}")

tk.Button(url_frame, text="Вставить", command=paste_url, font=('Arial', 12)).pack(side=tk.LEFT, padx=5)

# Фрейм для ввода номера клиента
client_frame = tk.Frame(main_tab)
client_frame.pack(pady=10, padx=10, anchor='w')

tk.Label(client_frame, text="Номер клиента:", font=('Arial', 12)).pack(side=tk.LEFT, padx=5)
entry_client = tk.Entry(client_frame, width=30, font=('Arial', 12))
entry_client.pack(side=tk.LEFT, padx=5)

# Фрейм для выбора папки и кнопок
folder_frame = tk.Frame(main_tab)
folder_frame.pack(pady=10, padx=10, anchor='w')

tk.Label(folder_frame, text="Папка для сохранения фото:", font=('Arial', 12)).pack(side=tk.LEFT, padx=5)
entry_folder = tk.Entry(folder_frame, width=50, font=('Arial', 12))
entry_folder.pack(side=tk.LEFT, padx=5)

# Функция для выбора папки
def browse_folder():
    folder_selected = filedialog.askdirectory()
    if folder_selected:
        entry_folder.delete(0, tk.END)
        entry_folder.insert(0, folder_selected)
        logging.info(f'Папка для сохранения выбрана: {folder_selected}')

tk.Button(folder_frame, text="Выбрать", command=browse_folder, font=('Arial', 12)).pack(side=tk.LEFT, padx=5)

# Функция для открытия папки с фото
def open_folder():
    save_path = entry_folder.get()
    if os.path.isdir(save_path):
        try:
            os.startfile(save_path)  # Для Windows
            logging.info(f'Папка открыта: {save_path}')
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть папку: {e}")
            logging.error(f"Не удалось открыть папку {save_path}: {e}")
    else:
        messagebox.showerror("Ошибка", "Папка не существует.")
        logging.error(f"Папка не существует: {save_path}")

tk.Button(folder_frame, text="Открыть папку с фото", command=open_folder, font=('Arial', 12)).pack(side=tk.LEFT, padx=5)  # Новая кнопка

# Кнопка запуска парсинга
def start_parse():
    parse_thread = threading.Thread(target=parse, daemon=True)
    parse_thread.start()

tk.Button(main_tab, text="Начать парсинг", command=start_parse, bg="green", fg="white", font=('Arial', 12, 'bold')).pack(pady=10)

# Прогресс-бар и метка прогресса
progress_frame = tk.Frame(main_tab)
progress_frame.pack(pady=5, padx=10, anchor='w')

progress_bar = ttk.Progressbar(progress_frame, orient='horizontal', length=400, mode='determinate')
progress_bar.pack(side=tk.LEFT, padx=5)

progress_label = tk.Label(progress_frame, text="Скачано 0 из 200 изображений.", font=('Arial', 12))
progress_label.pack(side=tk.LEFT, padx=10)

# ----- Вкладка "Отчёты" -----
reports_label = tk.Label(reports_tab, text="Отчёты:", font=('Arial', 12, 'bold'))
reports_label.pack(pady=5, padx=10, anchor='w')

reports_text = scrolledtext.ScrolledText(reports_tab, width=105, height=25, state='disabled', font=('Arial', 10))
reports_text.pack(pady=5, padx=10)

# Функция для обновления отчетов из базы данных
def update_reports():
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT time, client_number, url FROM history ORDER BY id DESC')
        rows = cursor.fetchall()
        reports = {}
        for row in rows:
            time_str, client_number, url = row
            if client_number not in reports:
                reports[client_number] = []
            reports[client_number].append((time_str, url))
        
        # Очистка и обновление поля отчетов
        reports_text.config(state='normal')
        reports_text.delete(1.0, tk.END)
        for client, entries in reports.items():
            reports_text.insert(tk.END, f"{client}\n")
            for entry in entries:
                reports_text.insert(tk.END, f"{entry[0]} {entry[1]}\n")
            reports_text.insert(tk.END, "\n")
        reports_text.config(state='disabled')
        logging.info("Отчеты обновлены.")
    except Exception as e:
        logging.error(f"Не удалось обновить отчеты: {e}")

tk.Button(reports_tab, text="Обновить отчёты", command=update_reports, font=('Arial', 12)).pack(pady=5, padx=10, anchor='w')

# ----- Вкладка "Логи" -----
log_label = tk.Label(logs_tab, text="Логи:", font=('Arial', 12, 'bold'))
log_label.pack(pady=5, padx=10, anchor='w')

log_text = scrolledtext.ScrolledText(logs_tab, width=105, height=25, state='disabled', font=('Arial', 10))
log_text.pack(pady=5, padx=10)

# Функция для открытия логов
def open_logs():
    try:
        os.startfile(os.path.join(application_path, 'parser_log.txt'))
        logging.info("Открыт файл логов.")
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось открыть логи: {e}")
        logging.error(f"Не удалось открыть логи: {e}")

tk.Button(logs_tab, text="Просмотреть лог-файл", command=open_logs, font=('Arial', 12)).pack(pady=5, padx=10, anchor='w')

# ----- Вкладка "Описание" -----
description_label = tk.Label(description_tab, text="Описание квартиры:", font=('Arial', 12, 'bold'))
description_label.pack(pady=5, padx=10, anchor='w')

description_text = scrolledtext.ScrolledText(description_tab, width=105, height=10, state='disabled', font=('Arial', 10))
description_text.pack(pady=5, padx=10)

# Функция для копирования описания квартиры
def copy_description():
    description = description_text.get(1.0, tk.END).strip()
    if description:
        try:
            pyperclip.copy(description)
            messagebox.showinfo("Успех", "Описание скопировано в буфер обмена.")
            logging.info("Описание скопировано в буфер обмена.")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось скопировать описание: {e}")
            logging.error(f"Не удалось скопировать описание: {e}")
    else:
        messagebox.showwarning("Предупреждение", "Описание квартиры пусто.")
        logging.warning("Попытка скопировать пустое описание.")

tk.Button(description_tab, text="Копировать описание", command=copy_description, font=('Arial', 12)).pack(pady=5, padx=10, anchor='w')

# Основная функция парсинга
def parse():
    url = entry_url.get()
    client_number = entry_client.get()
    save_path = entry_folder.get()

    if not url or not client_number or not save_path:
        messagebox.showwarning("Предупреждение", "Пожалуйста, заполните все поля.")
        logging.warning("Пользователь не заполнил все поля.")
        return

    # Валидация URL
    if not is_valid_url(url):
        messagebox.showerror("Ошибка", "Введённый URL некорректен.")
        logging.error(f"Некорректный URL: {url}")
        return

    # Очистка папки
    clear_folder(save_path)

    # Настройка прогресс-бара
    max_images = 200  # Максимальное количество изображений для попыток
    progress_queue = update_queue
    progress_queue.put({'type': 'init_progress', 'max_images': max_images})

    # Загрузка страницы
    try:
        response = requests.get(url, timeout=10)
        logging.info(f'Страница загружена: {url} Статус: {response.status_code}')
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось загрузить страницу: {e}")
        logging.error(f"Не удалось загрузить страницу {url}: {e}")
        progress_queue.put({'type': 'error', 'message': f"Не удалось загрузить страницу: {e}"})
        return

    if response.status_code == 200:
        # Парсинг HTML-кода страницы
        soup = BeautifulSoup(response.content, 'html.parser')

        # Парсинг заголовка объявления
        title_tag = soup.find('h1', class_='offer__title')
        title = title_tag.get_text(strip=True) if title_tag else ''

        # Парсинг метража
        size_tag = soup.find('div', class_='offer__advert-title')
        size = size_tag.get_text(strip=True).split('Оставить')[0].strip() if size_tag else ''

        # Парсинг адреса
        address_tag = soup.find('div', class_='offer__location')
        address = address_tag.get_text(strip=True) if address_tag else ''

        # Парсинг цены
        price_tag = soup.find('div', class_='offer__price')
        price = price_tag.get_text(strip=True) if price_tag else ''

        # Парсинг точного адреса
        full_address_tag = soup.find('div', class_='offer__location').find_next('div')
        full_address = full_address_tag.get_text(strip=True) if full_address_tag else ''
        full_address = full_address.replace('Адрес', '').strip()  # Удаление лишнего слова "Адрес"

        # Форматирование вывода
        formatted_output = f"{size}, {full_address}, {price}"

        # Обновление поля описания квартиры
        progress_queue.put({'type': 'update_description', 'description': formatted_output})

        # Сохранение истории в базу данных
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        progress_queue.put({'type': 'save_history', 'client_number': client_number, 'url': url, 'time': current_time})

        # Найти первую картинку нужного размера
        img_tag = soup.find('img', src=re.compile('750x470'))
        if img_tag:
            img_url = img_tag['src']
            # Извлекаем base_url и суффикс из найденной ссылки
            match = re.match(r'(.*\/)(\d+)(-750x470\.\w+)', img_url)
            if match:
                base_url = match.group(1)
                image_suffix = match.group(3)

                # Логирование готовности папки
                logging.info(f'Папка для изображений готова: {save_path}')

                downloaded = 0
                attempted = 0

                for count in range(1, max_images + 1):
                    image_url = f"{base_url}{count}{image_suffix}"
                    attempted += 1
                    try:
                        img_response = requests.get(image_url, timeout=10)
                        if img_response.status_code == 200:
                            # Определение расширения файла из URL
                            ext = os.path.splitext(image_url)[1]  # включает точку
                            if not ext:
                                ext = '.jpg'  # стандартное расширение, если отсутствует
                            # Генерация уникального имени файла
                            file_path = os.path.join(save_path, f'image_{count}{ext}')
                            with open(file_path, 'wb') as f:
                                f.write(img_response.content)
                            log_message = f'Скачано изображение: {image_url}\n'
                            progress_queue.put({'type': 'log', 'message': log_message})
                            logging.info(f'Скачано изображение: {image_url}')
                            downloaded += 1
                        else:
                            log_message = f"Не удалось скачать изображение: {image_url} (Статус: {img_response.status_code})\n"
                            progress_queue.put({'type': 'log', 'message': log_message})
                            logging.warning(f"Не удалось скачать изображение: {image_url} Статус: {img_response.status_code}")
                    except Exception as e:
                        log_message = f"Ошибка при скачивании {image_url}: {e}\n"
                        progress_queue.put({'type': 'log', 'message': log_message})
                        logging.error(f"Ошибка при скачивании {image_url}: {e}")

                    # Обновление прогресса
                    progress_queue.put({'type': 'update_progress', 'attempted': attempted, 'downloaded': downloaded, 'max_images': max_images})

                # После завершения скачивания
                completion_message = f'Попытки загрузки завершены. Скачано {downloaded} изображений.\n'
                progress_queue.put({'type': 'log', 'message': completion_message})
                logging.info(f'Попытки загрузки завершены. Скачано {downloaded} изображений.')
                progress_queue.put({'type': 'complete', 'downloaded': downloaded, 'max_images': max_images})
            else:
                log_message = "Не удалось извлечь base_url из ссылки на изображение.\n"
                progress_queue.put({'type': 'log', 'message': log_message})
                logging.warning("Не удалось извлечь base_url из ссылки на изображение.")
        else:
            log_message = "Не удалось найти изображение нужного размера на странице.\n"
            progress_queue.put({'type': 'log', 'message': log_message})
            logging.warning("Не удалось найти изображение нужного размера на странице.")

# Функция для обработки сообщений из очереди
def process_queue():
    try:
        while True:
            message = update_queue.get_nowait()
            msg_type = message.get('type')
            
            if msg_type == 'init_progress':
                max_images = message.get('max_images', 200)
                progress_bar.config(maximum=max_images)
                progress_bar['value'] = 0
                progress_label.config(text="Поиск фото...")
            
            elif msg_type == 'update_progress':
                attempted = message.get('attempted', 0)
                downloaded = message.get('downloaded', 0)
                max_images = message.get('max_images', 200)
                progress_bar['value'] = attempted
                progress_label.config(text=f"Скачано {downloaded} из {max_images} изображений.")
            
            elif msg_type == 'log':
                log_message = message.get('message', '')
                log_text.config(state='normal')
                log_text.insert(tk.END, log_message)
                log_text.see(tk.END)
                log_text.config(state='disabled')
            
            elif msg_type == 'update_description':
                description = message.get('description', '')
                description_text.config(state='normal')
                description_text.delete(1.0, tk.END)
                description_text.insert(tk.END, description)
                description_text.config(state='disabled')
            
            elif msg_type == 'save_history':
                client_number = message.get('client_number', '')
                url = message.get('url', '')
                time = message.get('time', '')
                save_history(client_number, url, time)
            
            elif msg_type == 'complete':
                downloaded = message.get('downloaded', 0)
                max_images = message.get('max_images', 200)
                progress_label.config(text=f"Загрузка завершена. Скачано {downloaded} изображений.")
                progress_bar['value'] = max_images
                update_reports()
            
            elif msg_type == 'error':
                error_message = message.get('message', '')
                messagebox.showerror("Ошибка", error_message)
                
    except queue.Empty:
        pass
    finally:
        root.after(100, process_queue)  # Проверять очередь каждые 100 мс

# Функция для обновления отчетов из базы данных
def update_reports():
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT time, client_number, url FROM history ORDER BY id DESC')
        rows = cursor.fetchall()
        reports = {}
        for row in rows:
            time_str, client_number, url = row
            if client_number not in reports:
                reports[client_number] = []
            reports[client_number].append((time_str, url))
        
        # Очистка и обновление поля отчетов
        reports_text.config(state='normal')
        reports_text.delete(1.0, tk.END)
        for client, entries in reports.items():
            reports_text.insert(tk.END, f"{client}\n")
            for entry in entries:
                reports_text.insert(tk.END, f"{entry[0]} {entry[1]}\n")
            reports_text.insert(tk.END, "\n")
        reports_text.config(state='disabled')
        logging.info("Отчеты обновлены.")
    except Exception as e:
        logging.error(f"Не удалось обновить отчеты: {e}")

# Функция для закрытия соединения с базой данных при выходе
def on_closing():
    try:
        conn.close()
        logging.info("Соединение с базой данных закрыто.")
    except Exception as e:
        logging.error(f"Ошибка при закрытии базы данных: {e}")
    root.destroy()

# Установка протокола закрытия окна
root.protocol("WM_DELETE_WINDOW", on_closing)

# Запуск обработки очереди
root.after(100, process_queue)

# Запуск главного цикла
root.mainloop()
