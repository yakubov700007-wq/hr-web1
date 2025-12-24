import os
import re
import sqlite3
from datetime import datetime
import subprocess
from io import BytesIO
import json
# Force update: red border for notes field

import streamlit as st
from PIL import Image
import pandas as pd
import hashlib
import bcrypt

# Helper: safe rerun that falls back to st.stop() if experimental_rerun is unavailable
def safe_rerun():
    try:
        st.experimental_rerun()
    except Exception:
        # If experimental_rerun isn't available in this Streamlit build, stop script
        # The session_state changes already took effect so user will see login on next interaction
        st.stop()

# --- Paths ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_FILE = os.path.join(DATA_DIR, "employees.db")
PHOTOS_DIR = os.path.join(DATA_DIR, "photos")
PDFS_DIR = os.path.join(DATA_DIR, "pdfs")
os.makedirs(PHOTOS_DIR, exist_ok=True)
os.makedirs(PDFS_DIR, exist_ok=True)


def init_db():
    """Create the employees and stations database tables if they don't exist."""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rakami_tabel TEXT UNIQUE,
            last_name TEXT,
            first_name TEXT,
            nasab TEXT,
            makon TEXT,
            sanai_kabul TEXT,
            vazifa TEXT,
            phone TEXT,
            dog_no TEXT,
            pdf_file TEXT,
            photo_file TEXT
        )
        """
    )
    # Create base stations table
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS stations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            location TEXT,
            type TEXT,
            frequency TEXT,
            power TEXT,
            status TEXT,
            contact TEXT,
            notes TEXT,
            region TEXT,
            pdf_file TEXT,
            photo_file TEXT
        )
        """
    )
    # Add region column if it doesn't exist (for existing databases)
    try:
        c.execute("ALTER TABLE stations ADD COLUMN region TEXT")
    except Exception:
        pass  # Column already exists
    
    # Create maintenance history table
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS station_maintenance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            station_id INTEGER,
            maintenance_date TEXT,
            maintenance_type TEXT,
            parts_replaced TEXT,
            notes TEXT,
            user_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (station_id) REFERENCES stations (id)
        )
        """
    )
    
    conn.commit()
    conn.close()

# Authentication: two levels
# Admin password(s) (can add/edit/delete). Supports comma-separated list in env.
# Default changed to 917150564pArvinA — can override via secrets/env vars
ADMIN_PASSWORD = os.getenv("HR_APP_PASSWORD", "917150564pArvinA")
ADMIN_PASSWORDS = [p.strip() for p in ADMIN_PASSWORD.split(",") if p.strip()]
# Viewer/read-only password(s). Supports comma-separated list in env.
VIEWER_PASSWORD = os.getenv("HR_VIEWER_PASSWORD", "917150564")
VIEWER_PASSWORDS = [p.strip() for p in VIEWER_PASSWORD.split(",") if p.strip()]
# Fingerprint of current password lists used to invalidate existing sessions when passwords change
PW_FINGERPRINT = hashlib.sha256(",".join(sorted(ADMIN_PASSWORDS + VIEWER_PASSWORDS)).encode()).hexdigest()

# --- Password store helpers ---
PASSWORD_STORE_FILE = os.path.join(DATA_DIR, "passwords.json")


def load_password_store():
    try:
        with open(PASSWORD_STORE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_password_store(store: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PASSWORD_STORE_FILE, "w", encoding="utf-8") as f:
        json.dump(store, f)


def get_password_identifiers():
    """Return list of strings representing current passwords/hashes for fingerprinting."""
    ids = []
    # Admin: env var takes precedence
    env_admin = os.getenv("HR_APP_PASSWORD")
    if env_admin:
        ids.extend([p.strip() for p in env_admin.split(",") if p.strip()])
    else:
        store = load_password_store()
        if store.get("admin"):
            ids.extend(["hash:" + h for h in store.get("admin", [])])
        else:
            # fallback to configured default string
            ids.extend([p.strip() for p in ADMIN_PASSWORD.split(",") if p.strip()])

    # Viewer
    env_viewer = os.getenv("HR_VIEWER_PASSWORD")
    if env_viewer:
        ids.extend([p.strip() for p in env_viewer.split(",") if p.strip()])
    else:
        store = store or load_password_store()
        if store.get("viewer"):
            ids.extend(["hash:" + h for h in store.get("viewer", [])])
        else:
            ids.extend([p.strip() for p in VIEWER_PASSWORD.split(",") if p.strip()])

    return ids


def recompute_pw_fingerprint():
    global PW_FINGERPRINT
    ids = get_password_identifiers()
    PW_FINGERPRINT = hashlib.sha256(",".join(sorted(ids)).encode()).hexdigest()

# ensure fingerprint matches current store/env state
recompute_pw_fingerprint()


def verify_password(candidate: str, role: str) -> bool:
    """Check candidate password for role 'admin' or 'viewer'."""
    cand = (candidate or "").strip()
    if not cand:
        return False
    # env var takes precedence
    if role == "admin":
        env = os.getenv("HR_APP_PASSWORD")
        defaults = [p.strip() for p in ADMIN_PASSWORD.split(",") if p.strip()]
    else:
        env = os.getenv("HR_VIEWER_PASSWORD")
        defaults = [p.strip() for p in VIEWER_PASSWORD.split(",") if p.strip()]

    if env:
        return cand in [p.strip() for p in env.split(",") if p.strip()]

    store = load_password_store()
    hashes = store.get(role)
    if hashes:
        for h in hashes:
            try:
                if bcrypt.checkpw(cand.encode(), h.encode()):
                    return True
            except Exception:
                continue
    # fallback to plaintext defaults
    return cand in defaults


def set_new_password(role: str, new_password: str):
    store = load_password_store()
    hashed = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    store[role] = [hashed]
    save_password_store(store)
    recompute_pw_fingerprint()


def render_change_password_ui(container, prefix="chg"):
    """Render change-password UI into the given container (st or st.sidebar).

    Uses keys prefixed with `prefix` to avoid collisions.
    """
    role_choice = container.selectbox("Кого менять", ("Admin", "Viewer"), key=f"{prefix}_role")
    old_pwd = container.text_input("Старый пароль", type="password", key=f"{prefix}_old")
    new1 = container.text_input("Новый пароль", type="password", key=f"{prefix}_new1")
    new2 = container.text_input("Подтвердите новый пароль", type="password", key=f"{prefix}_new2")
    if container.button("Сменить пароль", key=f"{prefix}_btn"):
        role_key = "admin" if role_choice == "Admin" else "viewer"
        # if env var exists, disallow change via app
        if (role_key == "admin" and os.getenv("HR_APP_PASSWORD")) or (role_key == "viewer" and os.getenv("HR_VIEWER_PASSWORD")):
            container.error("Пароль управляется через переменную окружения; удалите её чтобы разрешить смену через приложение.")
        elif not verify_password(old_pwd, role_key):
            container.error("Старый пароль неверен")
        elif not new1 or new1 != new2:
            container.error("Новые пароли не совпадают")
        elif len(new1) < 6:
            container.error("Пароль слишком короткий (минимум 6 символов)")
        else:
            set_new_password(role_key, new1)
            container.success("Пароль успешно изменён. Клиенты будут вынуждены войти заново.")
            st.session_state.pw_fingerprint = PW_FINGERPRINT
            safe_rerun()

# --- DB helpers ---

def get_conn():
    return sqlite3.connect(DB_FILE)


def fetch_employees(search="", region="Все"):
    conn = get_conn()
    c = conn.cursor()
    sql = "SELECT id, rakami_tabel, last_name, first_name, nasab, makon, sanai_kabul, vazifa, phone, dog_no, pdf_file, photo_file FROM employees"
    where = []
    params = []
    if region and region != "Все":
        where.append("makon = ?")
        params.append(region)
    if search:
        like = f"%{search.strip()}%"
        where.append("(rakami_tabel LIKE ? OR last_name LIKE ? OR first_name LIKE ? OR nasab LIKE ? OR phone LIKE ?)" )
        params.extend([like, like, like, like, like])
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY rakami_tabel ASC"  # <-- сортировка по табельному №
    c.execute(sql, params)
    rows = c.fetchall()
    conn.close()
    return rows


def tabel_exists(rakami_tabel, exclude_id=None):
    conn = get_conn()
    c = conn.cursor()
    if exclude_id is None:
        c.execute("SELECT 1 FROM employees WHERE rakami_tabel=? LIMIT 1", (rakami_tabel,))
    else:
        c.execute("SELECT 1 FROM employees WHERE rakami_tabel=? AND id<>? LIMIT 1", (rakami_tabel, exclude_id))
    row = c.fetchone()
    conn.close()
    return row is not None


def add_employee(data):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO employees (rakami_tabel, last_name, first_name, nasab, makon, sanai_kabul, vazifa, phone, dog_no, pdf_file, photo_file)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        data,
    )
    conn.commit()
    conn.close()


def update_employee(emp_id, data):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        UPDATE employees
        SET rakami_tabel=?, last_name=?, first_name=?, nasab=?, makon=?, sanai_kabul=?, vazifa=?, phone=?, dog_no=?, pdf_file=?, photo_file=?
        WHERE id=?
        """,
        (*data, emp_id),
    )
    conn.commit()
    conn.close()


def delete_employee(emp_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM employees WHERE id=?", (emp_id,))
    conn.commit()
    conn.close()


# --- Station DB helpers ---

def fetch_stations(search="", region="Все"):
    conn = get_conn()
    c = conn.cursor()
    sql = "SELECT id, name, location, type, frequency, power, status, contact, notes, region, pdf_file, photo_file FROM stations"
    where = []
    params = []
    if region and region != "Все":
        where.append("region = ?")
        params.append(region)
    if search:
        like = f"%{search.strip()}%"
        where.append("(name LIKE ? OR location LIKE ? OR contact LIKE ? OR notes LIKE ?)")
        params.extend([like, like, like, like])
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY name ASC"
    c.execute(sql, params)
    rows = c.fetchall()
    conn.close()
    return rows


def station_exists(name, exclude_id=None):
    conn = get_conn()
    c = conn.cursor()
    if exclude_id is None:
        c.execute("SELECT 1 FROM stations WHERE name=? LIMIT 1", (name,))
    else:
        c.execute("SELECT 1 FROM stations WHERE name=? AND id<>? LIMIT 1", (name, exclude_id))
    row = c.fetchone()
    conn.close()
    return row is not None


def add_station(data):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO stations (name, location, type, frequency, power, status, contact, notes, region, pdf_file, photo_file)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        data,
    )
    conn.commit()
    conn.close()


def update_station(station_id, data):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        UPDATE stations
        SET name=?, location=?, type=?, frequency=?, power=?, status=?, contact=?, notes=?, region=?, pdf_file=?, photo_file=?
        WHERE id=?
        """,
        (*data, station_id),
    )
    conn.commit()
    conn.close()


def delete_station(station_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM stations WHERE id=?", (station_id,))
    conn.commit()
    conn.close()


# --- Maintenance helpers ---

def add_maintenance_record(station_id, maintenance_type, parts_replaced, notes, user_name):
    """Добавить запись об обслуживании станции"""
    conn = get_conn()
    c = conn.cursor()
    maintenance_date = datetime.now().strftime("%Y-%m-%d")
    c.execute(
        """
        INSERT INTO station_maintenance (station_id, maintenance_date, maintenance_type, parts_replaced, notes, user_name)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (station_id, maintenance_date, maintenance_type, parts_replaced, notes, user_name)
    )
    conn.commit()
    conn.close()


def get_maintenance_records(station_id=None, date_filter=None, region_filter=None):
    """Получить записи об обслуживании"""
    conn = get_conn()
    c = conn.cursor()
    
    sql = """
    SELECT sm.*, s.name as station_name, s.region, s.notes as station_notes
    FROM station_maintenance sm 
    JOIN stations s ON sm.station_id = s.id
    """
    params = []
    where_conditions = []
    
    if station_id:
        where_conditions.append("sm.station_id = ?")
        params.append(station_id)
    
    if date_filter:
        where_conditions.append("sm.maintenance_date = ?")
        params.append(date_filter)
    
    if region_filter and region_filter != "Все":
        where_conditions.append("s.region = ?")
        params.append(region_filter)
    
    if where_conditions:
        sql += " WHERE " + " AND ".join(where_conditions)
    
    sql += " ORDER BY sm.maintenance_date DESC, sm.created_at DESC"
    
    c.execute(sql, params)
    rows = c.fetchall()
    conn.close()
    return rows


def get_maintenance_stats(date_filter=None):
    """Получить статистику обслуживания за день"""
    conn = get_conn()
    c = conn.cursor()
    
    if date_filter:
        date_str = date_filter
    else:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    # Общее количество обслуженных станций
    c.execute("""
        SELECT COUNT(DISTINCT station_id) as total_maintained,
               SUM(CASE WHEN maintenance_type = 'repair' THEN 1 ELSE 0 END) as repairs,
               SUM(CASE WHEN maintenance_type = 'service' THEN 1 ELSE 0 END) as services
        FROM station_maintenance 
        WHERE maintenance_date = ?
    """, (date_str,))
    
    stats = c.fetchone()
    conn.close()
    
    return {
        'date': date_str,
        'total_maintained': stats[0] if stats else 0,
        'repairs': stats[1] if stats else 0,
        'services': stats[2] if stats else 0
    }


def get_maintenance_stats_by_region(date_filter=None, region_filter=None):
    """Получить статистику обслуживания по регионам"""
    conn = get_conn()
    c = conn.cursor()
    
    if date_filter:
        date_str = date_filter
    else:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    # SQL запрос с фильтром по регионам
    sql = """
        SELECT s.region,
               COUNT(DISTINCT sm.station_id) as total_maintained,
               SUM(CASE WHEN sm.maintenance_type = 'repair' THEN 1 ELSE 0 END) as repairs,
               SUM(CASE WHEN sm.maintenance_type = 'service' THEN 1 ELSE 0 END) as services
        FROM station_maintenance sm 
        JOIN stations s ON sm.station_id = s.id
        WHERE sm.maintenance_date = ?
    """
    
    params = [date_str]
    
    if region_filter and region_filter != "Все":
        sql += " AND s.region = ?"
        params.append(region_filter)
    
    sql += " GROUP BY s.region ORDER BY s.region"
    
    c.execute(sql, params)
    rows = c.fetchall()
    conn.close()
    
    return rows


# --- File helpers ---

def safe_write_file(target_dir: str, filename_hint: str, data: bytes) -> str:
    root, ext = os.path.splitext(filename_hint)
    root = re.sub(r"[^\w\-\.]+", "_", root).strip("._") or "file"
    ext = ext if ext else ""
    target = os.path.join(target_dir, root + ext)
    i = 1
    while os.path.exists(target):
        target = os.path.join(target_dir, f"{root}_{i}{ext}")
        i += 1
    with open(target, "wb") as f:
        f.write(data)
    # return relative path from project BASE_DIR for portability
    try:
        rel = os.path.relpath(target, BASE_DIR)
    except Exception:
        rel = target
    return rel


def get_abs_path(path_or_rel: str) -> str:
    """Return absolute path for a stored path (which may be relative to BASE_DIR).

    Returns empty string if input is falsy.
    """
    if not path_or_rel:
        return ""
    if os.path.isabs(path_or_rel):
        return path_or_rel
    return os.path.join(BASE_DIR, path_or_rel)


# --- Auth ---

def require_auth():
    # if fingerprint changed, clear auth state so users must re-login
    if st.session_state.get("pw_fingerprint") and st.session_state.get("pw_fingerprint") != PW_FINGERPRINT:
        for k in ["authed", "role", "page", "pw_fingerprint"]:
            if k in st.session_state:
                del st.session_state[k]

    """Authenticate user and set role in session_state: 'admin' or 'viewer'."""
    if "authed" not in st.session_state:
        st.session_state.authed = False
        st.session_state.role = None
    if st.session_state.authed:
        return True

    st.title("Вход")
    pwd = st.text_input("Пароль", type="password")
    if st.button("Войти"):
        p = (pwd or "").strip()
        if verify_password(p, "admin"):
            st.session_state.authed = True
            st.session_state.role = "admin"
            st.session_state.pw_fingerprint = PW_FINGERPRINT
            st.success("Вход выполнен: администратор")
            safe_rerun()
        elif verify_password(p, "viewer"):
            st.session_state.authed = True
            st.session_state.role = "viewer"
            st.session_state.pw_fingerprint = PW_FINGERPRINT
            st.session_state.page = "Сотрудники"
            st.success("Вход выполнен: только просмотр")
            safe_rerun()
        else:
            st.error("Неверный пароль")
    st.stop()


# --- UI ---

def employee_form(defaults=None, disabled: bool = False, key_prefix: str | None = None):
    """Render employee form inputs. If disabled=True inputs are readonly/disabled.

    key_prefix: optional string used to create unique widget keys when the form
    is rendered multiple times (for example per-employee edit forms). If None,
    a default prefix 'g' is used.

    Returns tuple of values in same order as before.
    """
    defaults = defaults or {}
    kp = (key_prefix or "g").strip()
    cols = st.columns(2)
    with cols[0]:
        rakami_tabel = st.text_input("Табельный №", value=defaults.get("rakami_tabel", ""), disabled=disabled, key=f"{kp}_rakami_tabel")
        last_name = st.text_input("Фамилия", value=defaults.get("last_name", ""), disabled=disabled, key=f"{kp}_last_name")
        first_name = st.text_input("Имя", value=defaults.get("first_name", ""), disabled=disabled, key=f"{kp}_first_name")
        nasab = st.text_input("Отчество", value=defaults.get("nasab", ""), disabled=disabled, key=f"{kp}_nasab")
        regions = ["РРП", "ВМКБ", "РУХО", "РУСО", "Душанбе"]
        default_makon = defaults.get("makon")
        idx = 0 if default_makon not in regions else regions.index(default_makon)
        makon = st.selectbox("Регион", regions, index=idx, disabled=disabled, key=f"{kp}_makon")
        sanai_kabul = st.text_input("Дата приёма", value=defaults.get("sanai_kabul", ""), disabled=disabled, key=f"{kp}_sanai_kabul")
    with cols[1]:
        vazifa = st.text_input("Должность", value=defaults.get("vazifa", ""), disabled=disabled, key=f"{kp}_vazifa")
        phone = st.text_input("Телефон", value=defaults.get("phone", ""), disabled=disabled, key=f"{kp}_phone")
        dog_no = st.text_input("Дог №", value=defaults.get("dog_no", ""), disabled=disabled, key=f"{kp}_dog_no")
        pdf_file = defaults.get("pdf_file", "")
        photo_file = defaults.get("photo_file", "")
        st.write("")
    return rakami_tabel, last_name, first_name, nasab, makon, sanai_kabul, vazifa, phone, dog_no, pdf_file, photo_file


def station_form(defaults=None, disabled: bool = False, key_prefix: str | None = None):
    """Render station form inputs. If disabled=True inputs are readonly/disabled.

    key_prefix: optional string used to create unique widget keys when the form
    is rendered multiple times (for example per-station edit forms). If None,
    a default prefix 'st' is used.

    Returns tuple of values for station fields.
    """
    defaults = defaults or {}
    kp = (key_prefix or "st").strip()
    cols = st.columns(2)
    with cols[0]:
        name = st.text_input("Название станции", value=defaults.get("name", ""), disabled=disabled, key=f"{kp}_name")
        location = st.text_input("Местоположение", value=defaults.get("location", ""), disabled=disabled, key=f"{kp}_location")
        station_types = ["Базовая", "Ретранслятор", "Спутниковая", "Мобильная"]
        default_type = defaults.get("type")
        type_idx = 0 if default_type not in station_types else station_types.index(default_type)
        station_type = st.selectbox("Тип станции", station_types, index=type_idx, disabled=disabled, key=f"{kp}_type")
        frequency = st.text_input("Частота", value=defaults.get("frequency", ""), disabled=disabled, key=f"{kp}_frequency")
        power = st.text_input("Мощность", value=defaults.get("power", ""), disabled=disabled, key=f"{kp}_power")
    with cols[1]:
        statuses = ["Активна", "Неактивна", "На обслуживании", "Резерв"]
        default_status = defaults.get("status")
        status_idx = 0 if default_status not in statuses else statuses.index(default_status)
        status = st.selectbox("Статус", statuses, index=status_idx, disabled=disabled, key=f"{kp}_status")
        regions = ["РРП", "ВМКБ", "РУХО", "РУСО", "Душанбе"]
        default_region = defaults.get("region")
        region_idx = 0 if default_region not in regions else regions.index(default_region)
        region = st.selectbox("Регион", regions, index=region_idx, disabled=disabled, key=f"{kp}_region")
        contact = st.text_input("Контакт", value=defaults.get("contact", ""), disabled=disabled, key=f"{kp}_contact")
        notes = st.text_area("Примечания", value=defaults.get("notes", ""), disabled=disabled, key=f"{kp}_notes")
        pdf_file = defaults.get("pdf_file", "")
        photo_file = defaults.get("photo_file", "")
        st.write("")
    return name, location, station_type, frequency, power, status, contact, notes, region, pdf_file, photo_file


def main():
    st.set_page_config(page_title="Сотрудники ПБК", layout="wide")

    # Ensure DB and data folders exist before any DB operations
    init_db()

    require_auth()
    
    # Улучшение читаемости текста в формах
    st.markdown("""
    <style>
    /* Максимальное улучшение читаемости для всех полей ввода */
    .stTextInput input,
    .stTextInput > div > div > input,
    input[type="text"],
    input {
        color: #000000 !important;
        background-color: #ffffff !important;
        font-weight: 600 !important;
        font-size: 17px !important;
        border: none !important;
        outline: none !important;
        box-shadow: none !important;
        text-shadow: none !important;
        -webkit-text-fill-color: #000000 !important;
    }
    
    .stTextArea textarea,
    .stTextArea > div > div > textarea,
    textarea {
        color: #000000 !important;
        background-color: #ffffff !important;
        font-weight: 600 !important;
        font-size: 17px !important;
        border: none !important;
        outline: none !important;
        box-shadow: none !important;
        text-shadow: none !important;
        -webkit-text-fill-color: #000000 !important;
    }
    
    .stSelectbox select,
    .stSelectbox > div > div > div,
    select {
        color: #000000 !important;
        background-color: #ffffff !important;
        font-weight: 600 !important;
        font-size: 17px !important;
        border: none !important;
        outline: none !important;
        box-shadow: none !important;
        text-shadow: none !important;
        -webkit-text-fill-color: #000000 !important;
    }
    
    /* Усиленные стили для disabled полей */
    .stTextInput input[disabled],
    .stTextInput > div > div > input[disabled],
    input[disabled] {
        color: #000000 !important;
        background-color: #f0f2f6 !important;
        font-weight: 600 !important;
        font-size: 17px !important;
        opacity: 1 !important;
        border: none !important;
        outline: none !important;
        box-shadow: none !important;
        text-shadow: none !important;
        -webkit-text-fill-color: #000000 !important;
    }
    
    .stTextArea textarea[disabled],
    .stTextArea > div > div > textarea[disabled],
    textarea[disabled] {
        color: #000000 !important;
        background-color: #f0f2f6 !important;
        font-weight: 600 !important;
        font-size: 17px !important;
        opacity: 1 !important;
        border: none !important;
        outline: none !important;
        box-shadow: none !important;
        text-shadow: none !important;
        -webkit-text-fill-color: #000000 !important;
    }
    
    .stSelectbox select[disabled],
    .stSelectbox > div > div > div[aria-disabled="true"],
    select[disabled] {
        color: #000000 !important;
        background-color: #f0f2f6 !important;
        font-weight: 600 !important;
        font-size: 17px !important;
        opacity: 1 !important;
        border: none !important;
        outline: none !important;
        box-shadow: none !important;
        text-shadow: none !important;
        -webkit-text-fill-color: #000000 !important;
    }
    
    /* Максимальная контрастность для placeholder текста */
    ::placeholder {
        color: #666666 !important;
        opacity: 1 !important;
        font-weight: 500 !important;
    }
    
    /* Усиленные лейблы */
    .stTextInput > label,
    .stTextArea > label,
    .stSelectbox > label,
    label {
        color: #000000 !important;
        font-weight: 700 !important;
        font-size: 17px !important;
        text-shadow: none !important;
    }
    
    /* Заголовки expander (увеличенные для читабельности) */
    .streamlit-expanderHeader,
    .streamlit-expanderHeader p {
        font-weight: 700 !important;
        color: #000000 !important;
        font-size: 22px !important;
        line-height: 1.1 !important;
    }
    
    /* Дополнительные стили для всех текстовых элементов в формах */
    div[data-testid="stForm"] * {
        -webkit-font-smoothing: antialiased !important;
        -moz-osx-font-smoothing: grayscale !important;
    }
    
    /* Принудительные стили для всех элементов форм */
    form input,
    form textarea,
    form select {
        color: #000000 !important;
        font-weight: 600 !important;
        -webkit-text-fill-color: #000000 !important;
    }
    
    /* Специальные стили для поля примечаний - МАКСИМАЛЬНАЯ видимость */
    .stTextArea textarea,
    textarea[aria-label*="Примечания"],
    div[data-testid="stTextArea"] textarea {
        background-color: #fff5f5 !important;
        border: 4px solid #e53e3e !important;
        border-radius: 12px !important;
        color: #1a202c !important;
        font-weight: 600 !important;
        font-size: 16px !important;
        line-height: 1.6 !important;
        padding: 16px !important;
        box-shadow: 0 4px 12px rgba(229, 62, 62, 0.3), 0 0 0 1px rgba(229, 62, 62, 0.1) !important;
        outline: none !important;
        -webkit-text-fill-color: #1a202c !important;
        min-height: 120px !important;
        transition: all 0.3s ease !important;
    }
    
    /* Дополнительное выделение контейнера поля примечаний */
    div[data-testid="stTextArea"] {
        background-color: #fff5f5 !important;
        border: 2px dashed #e53e3e !important;
        border-radius: 16px !important;
        padding: 8px !important;
        margin: 8px 0 !important;
    }
    
    /* При фокусе на поле примечаний */
    .stTextArea textarea:focus,
    textarea[aria-label*="Примечания"]:focus,
    div[data-testid="stTextArea"] textarea:focus {
        border-color: #c53030 !important;
        box-shadow: 0 0 0 4px rgba(229, 62, 62, 0.4), 0 4px 16px rgba(229, 62, 62, 0.4) !important;
        background-color: #ffffff !important;
        transform: scale(1.02) !important;
    }
    /* Крупные подписи/caption, чтобы номера/имена были легко читаемы */
    div[data-testid="stCaptionContainer"] p,
    .stCaption {
        font-size: 18px !important;
        font-weight: 700 !important;
        color: #000000 !important;
    }

    /* Увеличение шрифта только для списка сотрудников (перекрывает глобальные правила) */
    /* Сделано более компактно: меньший font-size, минимальные отступы и жёсткий max-height */
    #employees_list .streamlit-expanderHeader,
    #employees_list .streamlit-expanderHeader p {
        font-size: 40px !important; /* ещё компактнее */
        font-weight: 900 !important; /* жирный текст */
        color: #000000 !important;
        line-height: 1.0 !important;
        padding: 0 6px !important; /* минимальные горизонтальные отступы */
        display: flex !important;
        align-items: center !important; /* выровнять по центру по вертикали */
        white-space: nowrap !important; /* одна строка */
        overflow: hidden !important;
        text-overflow: ellipsis !important; /* троеточие при переполнении */
        max-height: 40px !important; /* ещё более жёсткое ограничение высоты */
        font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif !important;
    }
    /* Адаптивность: на узких экранах уменьшаем размер, чтобы не ломать верстку */
    @media (max-width: 720px) {
        #employees_list .streamlit-expanderHeader,
        #employees_list .streamlit-expanderHeader p {
            font-size: 22px !important; /* мобильный размер */
            padding: 6px 8px !important;
        }
    }
    /* Компактное содержимое раскрытой вкладки сотрудников */
    #employees_list .streamlit-expanderContent,
    #employees_list .streamlit-expanderContent > div {
        padding: 8px 12px !important; /* менее просторно внутри */
        margin: 0 !important;
        gap: 6px !important;
        font-size: 15px !important; /* чуть меньше для деталей */
        line-height: 1.3 !important;
    }
    /* Уменьшаем вертикальные отступы между полями внутри раскрытой панели */
    #employees_list .streamlit-expanderContent .stTextInput,
    #employees_list .streamlit-expanderContent .stTextArea,
    #employees_list .streamlit-expanderContent .stSelectbox,
    #employees_list .streamlit-expanderContent .stMultiSelect {
        margin-bottom: 6px !important;
        padding-bottom: 4px !important;
    }
    /* Сужаем изображение превью и контролируем его отступы */
    #employees_list .streamlit-expanderContent img {
        max-width: 180px !important;
        height: auto !important;
        margin-bottom: 6px !important;
        border-radius: 6px !important;
    }
    /* На узких экранах дополнительно уменьшаем отступы внутри содержимого */
    @media (max-width: 720px) {
        #employees_list .streamlit-expanderContent,
        #employees_list .streamlit-expanderContent > div {
            padding: 6px 8px !important;
            font-size: 14px !important;
        }
        #employees_list .streamlit-expanderContent img {
            max-width: 120px !important;
        }
    }
    </style>
    """, unsafe_allow_html=True)

    # show deployed version (git short sha) to help verify Cloud deploys
    def get_short_sha():
        try:
            out = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL)
            return out.decode().strip()
        except Exception:
            return None

    sha = get_short_sha()
    if sha:
        st.caption(f"Версия: {sha}")
    else:
        st.caption(f"Версия: (неизвестна) — локально: {datetime.utcnow().isoformat()}Z")

    # Top-right logout button (visible when authenticated)
    if st.session_state.get("authed"):
        cols_top = st.columns([9, 1])
        with cols_top[1]:
            if st.button("Выход", key="logout"):
                # clear auth-related session keys and go to login
                for k in ["authed", "role", "page"]:
                    if k in st.session_state:
                        del st.session_state[k]
                    safe_rerun()

    # --- Navigation: simple main menu ---
    if "page" not in st.session_state:
        st.session_state.page = "Главная"

    st.sidebar.title("Меню")
    # show current role, clear cache and logout in sidebar for visibility
    if st.session_state.get("authed"):
        role = st.session_state.get("role", "?")
        st.sidebar.markdown(f"**Роль:** {role}")

        if st.sidebar.button("Выход", key="logout_sidebar"):
            for k in ["authed", "role", "page"]:
                if k in st.session_state:
                    del st.session_state[k]
            safe_rerun()

        # Admin-only: password change UI (reused component)
        if st.session_state.get("role") == "admin":
            render_change_password_ui(st.sidebar, prefix="sidebar_chg")
                    elif len(new1) < 6:
                        st.error("Пароль слишком короткий (минимум 6 символов)")
                    else:
                        set_new_password(role_key, new1)
                        st.success("Пароль успешно изменён. Клиенты будут вынуждены войти заново.")
                        st.session_state.pw_fingerprint = PW_FINGERPRINT
                        safe_rerun()
    # Navigation with individual buttons in sidebar for instant single-click navigation
    st.sidebar.header("Навигация")
    
    # Get current page from session state, default to "Главная"
    if "page" not in st.session_state:
        st.session_state.page = "Главная"
    
    current_page = st.session_state.page
    
    # Individual navigation buttons with strict black & white icons
    if st.sidebar.button("⌂ Главная", 
                        key="nav_home",
                        type="primary" if current_page == "Главная" else "secondary",
                        use_container_width=True):
        st.session_state.page = "Главная"
        safe_rerun()
    
    if st.sidebar.button("☉ Сотрудники", 
                        key="nav_employees", 
                        type="primary" if current_page == "Сотрудники" else "secondary",
                        use_container_width=True):
        st.session_state.page = "Сотрудники"
        safe_rerun()
    
    if st.sidebar.button("↯ Базовые станции", 
                        key="nav_stations",
                        type="primary" if current_page == "⌁ Базовые станции" else "secondary", 
                        use_container_width=True):
        st.session_state.page = "⌁ Базовые станции"
        safe_rerun()
    
    # Use the session state page for logic
    page = st.session_state.page

    if page == "Главная":
        st.header("Главное меню")
        st.write("Вы вошли в систему. Используйте меню слева, чтобы перейти в разделы.")
        st.write("Используйте меню в боковой панели для навигации между разделами:")

        # Сделать пункты меню интерактивными кнопками на главной странице
        cols = st.columns(2)
        page_changed = False
        
        with cols[0]:
            if st.button("Сотрудники", key="menu_btn_employees"):
                st.session_state.page = "Сотрудники"
                page_changed = True
            st.caption("Управление персоналом — добавление, редактирование, поиск")

        with cols[1]:
            if st.button("⌁ Базовые станции", key="menu_btn_stations"):
                st.session_state.page = "⌁ Базовые станции"
                page_changed = True
            st.caption("Управление базовыми станциями: добавление, настройки, файлы")

        # Обновить страницу только если была нажата кнопка
        if page_changed:
            safe_rerun()

        # Admin: change-password toggle on main menu
        if st.session_state.get("role") == "admin":
            if st.button("Изменить пароль", key="main_chg_toggle"):
                st.session_state.show_change_password_main = not st.session_state.get("show_change_password_main", False)
            if st.session_state.get("show_change_password_main"):
                with st.expander("Изменить пароль", expanded=True):
                    render_change_password_ui(st, prefix="main_chg")

        return

    elif page == "⌁ Базовые станции":
        st.header("Базовые станции")
        
        # Вкладки внутри страницы базовых станций
        tab1, tab2 = st.tabs(["🏛️ Управление станциями", "📊 Отчеты"])
        
        with tab1:
            # Show view-only info for non-admin users
            if st.session_state.get("role") != "admin":
                st.info("👁️ Режим только для просмотра - добавление и удаление недоступно")

            # Sidebar filters/actions for stations  
            st.sidebar.header("Фильтр")
            region = st.sidebar.selectbox("Регион", ["Все", "РРП", "ВМКБ", "РУХО", "РУСО", "Душанбе"], index=0)
            search = st.sidebar.text_input("Поиск")
            st.sidebar.divider()
        
        # Determine add mode from sidebar toggle only
        if st.session_state.get("role") == "admin":
            add_mode = st.sidebar.toggle("Добавить новую станцию", value=False, key="sidebar_add_toggle")
        else:
            add_mode = False
            st.sidebar.caption("Режим: только просмотр")

        # Data table or add form
        if add_mode:
            st.subheader("Добавить базовую станцию")
            with st.form("add_station_form"):
                vals = station_form(key_prefix="add_station")
                submitted = st.form_submit_button("Сохранить")
            if submitted:
                station_name = vals[0].strip()
                if not station_name:
                    st.error("Название станции обязательно")
                    st.stop()
                if station_exists(station_name):
                    st.error("Такая станция уже существует")
                    st.stop()
                add_station((
                    station_name, vals[1], vals[2], vals[3], vals[4], vals[5], vals[6], vals[7], vals[8],
                    "", ""  # Empty strings for PDF and photo paths
                ))
                st.success("Станция добавлена")
                safe_rerun()
        else:
            rows = fetch_stations(search=search, region=region)
            
            st.caption(f"Найдено станций: {len(rows)}")

            for row in rows:
                (
                    station_id, name, location, s_type, frequency, power, status, contact, notes, region, pdf_file, photo_file
                ) = row
                
                with st.expander(f"{name} — {location}", expanded=False):
                    # Edit block: only admins may edit/delete. Viewers see read-only fields.
                    if st.session_state.get("role") == "admin":
                            st.markdown("**Редактировать станцию**")
                            with st.form(f"edit_station_{station_id}"):
                                vals = station_form({
                                    "name": name,
                                    "location": location,
                                    "type": s_type,
                                    "frequency": frequency,
                                    "power": power,
                                    "status": status,
                                    "contact": contact,
                                    "notes": notes,
                                    "region": region,
                                    "pdf_file": pdf_file or "",
                                    "photo_file": photo_file or "",
                                }, disabled=False, key_prefix=f"station_{station_id}")
                                save = st.form_submit_button("Сохранить изменения")
                            cols_btn = st.columns(2)
                            if save:
                                new_name = vals[0].strip()
                                if not new_name:
                                    st.error("Название станции обязательно")
                                    st.stop()
                                if station_exists(new_name, exclude_id=station_id):
                                    st.error("Такая станция уже существует")
                                    st.stop()
                                update_station(station_id, (
                                    new_name, vals[1], vals[2], vals[3], vals[4], vals[5], vals[6], vals[7], vals[8], vals[9] or "", vals[10] or ""
                                ))
                                st.success("Сохранено")
                                safe_rerun()
                            with cols_btn[1]:
                                if st.button("Удалить", type="primary", key=f"station_del_{station_id}"):
                                    delete_station(station_id)
                                    st.warning("Станция удалена")
                                    safe_rerun()
                    else:
                        st.markdown("**Информация станции**")
                        # Показать поля только для чтения (кроме примечаний)
                        with st.form(f"readonly_station_{station_id}"):
                            cols = st.columns(2)
                            with cols[0]:
                                st.text_input("Название станции", value=name, disabled=True, key=f"ro_name_{station_id}")
                                st.text_input("Местоположение", value=location, disabled=True, key=f"ro_location_{station_id}")
                                st.selectbox("Тип станции", ["Базовая", "Ретранслятор", "Спутниковая", "Мобильная"], 
                                           index=["Базовая", "Ретранслятор", "Спутниковая", "Мобильная"].index(s_type) if s_type in ["Базовая", "Ретранслятор", "Спутниковая", "Мобильная"] else 0,
                                           disabled=True, key=f"ro_type_{station_id}")
                                st.text_input("Частота", value=frequency, disabled=True, key=f"ro_frequency_{station_id}")
                                st.text_input("Мощность", value=power, disabled=True, key=f"ro_power_{station_id}")
                            with cols[1]:
                                st.selectbox("Статус", ["Активна", "Неактивна", "На обслуживании", "Резерв"],
                                           index=["Активна", "Неактивна", "На обслуживании", "Резерв"].index(status) if status in ["Активна", "Неактивна", "На обслуживании", "Резерв"] else 0,
                                           disabled=True, key=f"ro_status_{station_id}")
                                st.selectbox("Регион", ["РРП", "ВМКБ", "РУХО", "РУСО", "Душанбе"],
                                           index=["РРП", "ВМКБ", "РУХО", "РУСО", "Душанбе"].index(region) if region in ["РРП", "ВМКБ", "РУХО", "РУСО", "Душанбе"] else 0,
                                           disabled=True, key=f"ro_region_{station_id}")
                                st.text_input("Контакт", value=contact, disabled=True, key=f"ro_contact_{station_id}")
                                
                                # Поле примечаний - редактируемое для всех пользователей (в правой колонке)
                                st.markdown("**Рабочие заметки**")
                                new_notes = st.text_area("Примечания", value=notes, disabled=False, key=f"editable_notes_{station_id}", 
                                                        height=100, help="Вы можете оставлять свои заметки и отчеты")
                                
                                # Чекбокс обслуживания
                                st.markdown("**🔧 Сегодняшнее обслуживание**")
                                serviced_today = st.checkbox("⚙️ Обслужено сегодня", key=f"service_{station_id}")
                                
                                if serviced_today:
                                    st.caption("💡 Детали работ и замененные запчасти указывайте в примечаниях выше")
                                
                            # Кнопка сохранения заметок
                            save_notes = st.form_submit_button("❏ Сохранить заметки", help="Сохранить изменения в примечаниях")
                        
                        if save_notes:
                            # Обновляем только поле примечаний, остальные поля остаются неизменными
                            update_station(station_id, (
                                name, location, s_type, frequency, power, status, contact, new_notes, region, pdf_file or "", photo_file or ""
                            ))
                            st.success("✅ Заметки сохранены! Администратор увидит ваши изменения.")
                            safe_rerun()
                        
                        # Автоматическое сохранение при установке галочки обслуживания
                        if serviced_today:
                            # Проверяем, не была ли уже запись об обслуживании сегодня
                            today_str = datetime.now().strftime("%Y-%m-%d")
                            existing_records = get_maintenance_records(station_id=station_id, date_filter=today_str)
                            
                            if not existing_records:
                                try:
                                    type_name = "Обслуживание"
                                    user_name = f"Пользователь ({st.session_state.get('role', 'неизвестно')})"
                                    
                                    add_maintenance_record(
                                        station_id, 
                                        "service", 
                                        "", 
                                        f"Тип: {type_name}", 
                                        user_name
                                    )
                                    
                                    st.success("✅ Обслуживание отмечено автоматически!")
                                    st.balloons()  # Визуальная обратная связь
                                    safe_rerun()
                                    
                                except Exception as e:
                                    st.error(f"❌ Ошибка при сохранении: {str(e)}")
                            else:
                                st.info("ℹ️ Обслуживание уже было отмечено сегодня")
                        
                        st.caption("📖 Информация станции доступна только для просмотра. Вы можете редактировать только примечания.")
        
        with tab2:
            st.subheader("📊 Отчеты по базовым станциям")
            
            # Отчеты по обслуживанию
            st.markdown("### 🔧 Отчеты по обслуживанию")
            
            # Фильтры для отчета
            col_date1, col_date2, col_region = st.columns(3)
            with col_date1:
                report_date = st.date_input("Дата отчета", value=datetime.now().date())
            with col_date2:
                date_str = report_date.strftime("%Y-%m-%d")
            with col_region:
                report_region_filter = st.selectbox("Регион", ["Все", "РРП", "ВМКБ", "РУХО", "РУСО", "Душанбе"], key="maintenance_region_filter")
            
            maintenance_stats = get_maintenance_stats(date_str)
            
            # Отладочная информация (временно)
            st.write(f"🔍 Отладка: Ищем записи за {date_str}")
            all_maintenance_records = get_maintenance_records()
            st.write(f"📊 Всего записей в базе: {len(all_maintenance_records)}")
            
            # Показываем последние 3 записи для отладки
            if all_maintenance_records:
                st.write("🔍 Последние записи:")
                for i, record in enumerate(all_maintenance_records[:3]):
                    st.write(f"  {i+1}. {record[8]} | {record[2]} | {record[3]} | {record[7]}")
            else:
                st.write("❌ Нет записей в таблице обслуживания")
            
            # Показываем статистику обслуживания
            if maintenance_stats['total_maintained'] > 0:
                col_stat1, col_stat2 = st.columns(2)
                
                with col_stat1:
                    st.metric("🔧 Всего обслужено", maintenance_stats['total_maintained'])
                with col_stat2:
                    st.metric("⚙️ Обслужено", maintenance_stats['services'])
                
                # Статистика по регионам с toggle
                with st.expander("🗺️ Статистика по регионам", expanded=False):
                    region_stats = get_maintenance_stats_by_region(date_str, report_region_filter)
                    
                    if region_stats:
                        if report_region_filter != "Все":
                            st.caption(f"Показаны данные только для региона: **{report_region_filter}**")
                        
                        # Создаем колонки для каждого региона
                        num_regions = len(region_stats)
                        if num_regions > 0:
                            cols_regions = st.columns(min(num_regions, 5))  # Максимум 5 колонок
                            
                            for i, (region, total, repairs, services) in enumerate(region_stats):
                                with cols_regions[i % 5]:
                                    st.markdown(f"**📍 {region}**")
                                    st.metric("⚙️", services, help="Обслужено")
                                    st.metric("Всего", total, help="Общее количество станций")
                    else:
                        st.info("Нет данных об обслуживании по регионам за выбранную дату")
                
                # Детальная информация по обслуживанию
                st.markdown(f"#### 📋 Детали обслуживания за {date_str}")
                maintenance_records = get_maintenance_records(date_filter=date_str, region_filter=report_region_filter)
                
                if maintenance_records:
                    for record in maintenance_records:
                        record_id, station_id, maint_date, maint_type, parts, notes, user_name, created_at, station_name, region, station_notes = record
                        
                        type_icon = "⚙️"
                        type_name = "Обслуживание"
                        
                        with st.expander(f"{type_icon} {station_name} ({region}) - {type_name}", expanded=False):
                            col_info1, col_info2 = st.columns(2)
                            
                            with col_info1:
                                st.write(f"**Станция:** {station_name}")
                                st.write(f"**Регион:** {region}")
                                st.write(f"**Тип работ:** {type_name}")
                                st.write(f"**Дата:** {maint_date}")
                            
                            with col_info2:
                                st.write(f"**Пользователь:** {user_name}")
                                st.write(f"**Время записи:** {created_at}")
                                # Показываем примечания станции с заголовком и полем
                                st.write("**💡 Детали работ и запчасти:**")
                                if station_notes and station_notes.strip():
                                    # Компактное поле с примечаниями
                                    if len(station_notes) > 60:
                                        st.text_area("", value=station_notes, height=60, disabled=True, key=f"notes_display_{record_id}")
                                    else:
                                        st.text_input("", value=station_notes, disabled=True, key=f"notes_display_{record_id}")
                                else:
                                    st.text_input("", value="Не указаны", disabled=True, key=f"notes_empty_{record_id}")
                else:
                    st.info("На выбранную дату записей об обслуживании нет")
            else:
                st.info(f"На {date_str} обслуживание станций не проводилось")
            
            st.divider()
            
            # Получаем все станции для статистики
            all_stations = fetch_stations()
            
            if all_stations:
                # Статистика по регионам с toggle
                with st.expander("🗺️ Статистика по регионам", expanded=False):
                    region_stats = {}
                    for station in all_stations:
                        region = station[9] or "Неизвестно"  # region field
                        region_stats[region] = region_stats.get(region, 0) + 1
                    
                    cols = st.columns(len(region_stats))
                    for i, (region, count) in enumerate(region_stats.items()):
                        with cols[i]:
                            st.metric(region, count)
                
                # Статистика по типам станций с toggle
                with st.expander("🏗️ Статистика по типам станций", expanded=False):
                    type_stats = {}
                    for station in all_stations:
                        station_type = station[3] or "Неизвестно"  # type field
                        type_stats[station_type] = type_stats.get(station_type, 0) + 1
                    
                    cols_type = st.columns(len(type_stats))
                    for i, (s_type, count) in enumerate(type_stats.items()):
                        with cols_type[i]:
                            st.metric(s_type, count)
                
                # Статистика по статусам с toggle
                with st.expander("⚡ Статистика по статусам", expanded=False):
                    status_stats = {}
                    for station in all_stations:
                        status = station[6] or "Неизвестно"  # status field
                        status_stats[status] = status_stats.get(status, 0) + 1
                    
                    cols_status = st.columns(len(status_stats))
                    for i, (status, count) in enumerate(status_stats.items()):
                        with cols_status[i]:
                            # Цветовая индикация статусов
                            if status == "Активна":
                                st.metric(f"🟢 {status}", count)
                            elif status == "Неактивна":
                                st.metric(f"🔴 {status}", count)
                            elif status == "На обслуживании":
                                st.metric(f"🟡 {status}", count)
                            else:
                                st.metric(status, count)
                
                # Общая статистика с toggle
                with st.expander("📈 Общая информация", expanded=False):
                    total_stations = len(all_stations)
                    active_stations = len([s for s in all_stations if s[6] == "Активна"])
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Всего станций", total_stations)
                    with col2:
                        st.metric("Активных станций", active_stations)
                    with col3:
                        availability = round((active_stations / total_stations * 100), 1) if total_stations > 0 else 0
                        st.metric("Доступность", f"{availability}%")
                

                    
            else:
                st.info("📭 Пока нет данных о базовых станциях")
                
        return

    # If we are here — page == 'Сотрудники'
    st.title("Сотрудники ПБК")
    
    # Sidebar filters/actions for employees
    st.sidebar.header("Фильтр")
    region = st.sidebar.selectbox("Регион", ["Все", "РРП", "ВМКБ", "РУХО", "РУСО", "Душанбе"], index=0)
    search = st.sidebar.text_input("Поиск")
    st.sidebar.divider()
    # only admins can add
    if st.session_state.get("role") == "admin":
        add_mode = st.sidebar.toggle("Добавить нового сотрудника", value=False)
    else:
        add_mode = False
        st.sidebar.caption("Режим: только просмотр")

    # Data table or add form
    if add_mode:
        st.subheader("Добавить сотрудника")
        with st.form("add_form"):
            vals = employee_form(key_prefix="add")
            uploaded_photo = st.file_uploader("Фото (необязательно)", type=["jpg", "jpeg", "png"], accept_multiple_files=False)
            uploaded_pdf = st.file_uploader("PDF (необязательно)", type=["pdf"], accept_multiple_files=False)
            submitted = st.form_submit_button("Сохранить")
        if submitted:
            rakami_tabel = vals[0].strip()
            if not rakami_tabel:
                st.error("Табельный № обязателен")
                st.stop()
            if tabel_exists(rakami_tabel):
                st.error("Такой Табельный № уже существует")
                st.stop()
            pdf_path = vals[9]
            photo_path = vals[10]
            if uploaded_photo is not None:
                photo_path = safe_write_file(PHOTOS_DIR, uploaded_photo.name, uploaded_photo.getvalue())
            if uploaded_pdf is not None:
                pdf_path = safe_write_file(PDFS_DIR, uploaded_pdf.name, uploaded_pdf.getvalue())
            add_employee((
                rakami_tabel,
                vals[1], vals[2], vals[3], vals[4], vals[5],
                vals[6], vals[7], vals[8],
                pdf_path or "", photo_path or ""
            ))
            st.success("Добавлено")
            safe_rerun()
    else:
        rows = fetch_employees(search=search, region=region)
        # Ограничиваем увеличение шрифта только для списка сотрудников — оборачиваем в контейнер
        st.markdown("<div id=\"employees_list\">", unsafe_allow_html=True)
        st.caption(f"Найдено: {len(rows)}")

        for row in rows:
            (
                emp_id, rakami_tabel, last_name, first_name, nasab,
                makon, sanai_kabul, vazifa, phone, dog_no, pdf_file, photo_file
            ) = row
            with st.expander(f"{last_name} {first_name} — {rakami_tabel}", expanded=False):
                # Admins can edit everything; viewers see read-only info
                if st.session_state.get("role") == "admin":
                    st.markdown("**Редактировать сотрудника**")
                    with st.form(f"edit_employee_{emp_id}"):
                        vals = employee_form({
                            "rakami_tabel": rakami_tabel,
                            "last_name": last_name,
                            "first_name": first_name,
                            "nasab": nasab,
                            "makon": makon,
                            "sanai_kabul": sanai_kabul,
                            "vazifa": vazifa,
                            "phone": phone,
                            "dog_no": dog_no,
                            "pdf_file": pdf_file or "",
                            "photo_file": photo_file or "",
                        }, disabled=False, key_prefix=f"emp_{emp_id}")

                        uploaded_photo = st.file_uploader("Фото (необязательно)", type=["jpg", "jpeg", "png"], accept_multiple_files=False, key=f"up_photo_{emp_id}")
                        uploaded_pdf = st.file_uploader("PDF (необязательно)", type=["pdf"], accept_multiple_files=False, key=f"up_pdf_{emp_id}")
                        save = st.form_submit_button("Сохранить")

                    cols_btn = st.columns(2)
                    with cols_btn[0]:
                        if save:
                            new_tabel = vals[0].strip()
                            if not new_tabel:
                                st.error("Табельный № обязателен")
                            elif tabel_exists(new_tabel, exclude_id=emp_id):
                                st.error("Такой Табельный № уже существует")
                            else:
                                pdf_path = vals[9] or pdf_file or ""
                                photo_path = vals[10] or photo_file or ""
                                if uploaded_photo is not None:
                                    photo_path = safe_write_file(PHOTOS_DIR, uploaded_photo.name, uploaded_photo.getvalue())
                                if uploaded_pdf is not None:
                                    pdf_path = safe_write_file(PDFS_DIR, uploaded_pdf.name, uploaded_pdf.getvalue())
                                update_employee(emp_id, (
                                    new_tabel, vals[1], vals[2], vals[3], vals[4], vals[5], vals[6], vals[7], vals[8], pdf_path or "", photo_path or ""
                                ))
                                st.success("Сохранено")
                                safe_rerun()

                    with cols_btn[1]:
                        if st.button("Удалить сотрудника", type="primary", key=f"del_emp_{emp_id}"):
                            delete_employee(emp_id)
                            st.warning("Сотрудник удалён")
                            safe_rerun()

                else:
                    st.markdown("**Информация (только для чтения)**")

                    # Рендерим информацию в двух колонках: фото слева и поля справа (пустая рамка если фото отсутствует)
                    cols_main = st.columns([1, 3])
                    with cols_main[0]:
                        # Отобразить фото если есть, иначе показать пустую рамку с подписью
                        abs_photo = get_abs_path(photo_file)
                        if photo_file and os.path.isfile(abs_photo):
                            try:
                                st.image(Image.open(abs_photo), use_column_width=True, caption=None)
                            except Exception:
                                st.markdown('<div style="width:160px;height:160px;border:2px solid #e53e3e;border-radius:6px;display:flex;align-items:center;justify-content:center;color:#666;font-weight:600">Нет фото</div>', unsafe_allow_html=True)
                        else:
                            # placeholder box with red border (keeps layout)
                            st.markdown('<div style="width:160px;height:160px;border:2px solid #e53e3e;border-radius:6px;display:flex;align-items:center;justify-content:center;color:#666;font-weight:600">Нет фото</div>', unsafe_allow_html=True)

                    with cols_main[1]:
                        cols_left = st.columns(2)
                        with cols_left[0]:
                            st.text_input("Табельный №", value=rakami_tabel, disabled=True, key=f"view_{emp_id}_rakami_tabel")
                            st.text_input("Фамилия", value=last_name, disabled=True, key=f"view_{emp_id}_last_name")
                            st.text_input("Имя", value=first_name, disabled=True, key=f"view_{emp_id}_first_name")
                            st.text_input("Отчество", value=nasab, disabled=True, key=f"view_{emp_id}_nasab")
                            st.selectbox("Регион", ["РРП", "ВМКБ", "РУХО", "РУСО", "Душанбе"], index=["РРП", "ВМКБ", "РУХО", "РУСО", "Душанбе"].index(makon) if makon in ["РРП", "ВМКБ", "РУХО", "РУСО", "Душанбе"] else 0, disabled=True, key=f"view_{emp_id}_makon")
                            st.text_input("Дата приёма", value=sanai_kabul, disabled=True, key=f"view_{emp_id}_sanai_kabul")
                        with cols_left[1]:
                            st.text_input("Должность", value=vazifa, disabled=True, key=f"view_{emp_id}_vazifa")
                            st.text_input("Телефон", value=phone, disabled=True, key=f"view_{emp_id}_phone")
                            st.text_input("Дог №", value=dog_no, disabled=True, key=f"view_{emp_id}_dog_no")

                        # PDF: показать кнопку скачивания если есть, иначе пометку
                        abs_pdf = get_abs_path(pdf_file)
                        if pdf_file and os.path.isfile(abs_pdf):
                            st.download_button("Скачать PDF", data=open(abs_pdf, "rb").read(), file_name=os.path.basename(abs_pdf), key=f"dl_{emp_id}")
                        else:
                            st.caption("PDF не прикреплён")

        # Закрываем контейнер списка сотрудников
        st.markdown("</div>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()
