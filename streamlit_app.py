import os
import re
import sqlite3
from datetime import datetime
import subprocess
from io import BytesIO

import streamlit as st
from PIL import Image

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
    conn.commit()
    conn.close()

# Authentication: two levels
# Admin password(s) (can add/edit/delete). Supports comma-separated list in env.
# По умолчанию изменён на 4321 — можно переопределить через секреты/переменные окружения
ADMIN_PASSWORD = os.getenv("HR_APP_PASSWORD", "4321")
ADMIN_PASSWORDS = [p.strip() for p in ADMIN_PASSWORD.split(",") if p.strip()]
# Viewer/read-only password(s). Supports comma-separated list in env.
VIEWER_PASSWORD = os.getenv("HR_VIEWER_PASSWORD", "123456789")
VIEWER_PASSWORDS = [p.strip() for p in VIEWER_PASSWORD.split(",") if p.strip()]

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
        if p in ADMIN_PASSWORDS:
            st.session_state.authed = True
            st.session_state.role = "admin"
            st.success("Вход выполнен: администратор")
            safe_rerun()
        elif p in VIEWER_PASSWORDS:
            st.session_state.authed = True
            st.session_state.role = "viewer"
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
        regions = ["РРП", "ВМКБ", "РУХО", "РУСО"]
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
        regions = ["РРП", "ВМКБ", "РУХО", "РУСО"]
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
    # Ensure DB and data folders exist before any DB operations
    init_db()

    require_auth()

    st.set_page_config(page_title="Сотрудники ПБК", layout="wide")

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

        return

    elif page == "⌁ Базовые станции":
        st.header("Базовые станции")
        
        # Show view-only info for non-admin users
        if st.session_state.get("role") != "admin":
            st.info("👁️ Режим только для просмотра - добавление и удаление недоступно")

        # Sidebar filters/actions for stations  
        st.sidebar.header("Фильтр")
        region = st.sidebar.selectbox("Регион", ["Все", "РРП", "ВМКБ", "РУХО", "РУСО"], index=0)
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
                    st.markdown("**Информация о станции**")
                    info_cols = st.columns(2)
                    with info_cols[0]:
                        st.text(f"Тип: {s_type}")
                        st.text(f"Частота: {frequency}")
                        st.text(f"Мощность: {power}")
                    with info_cols[1]:
                        st.text(f"Статус: {status}")
                        st.text(f"Регион: {region}")
                        st.text(f"Контакт: {contact}")
                        if notes:
                            st.text(f"Примечания: {notes}")
                        abs_pdf = get_abs_path(pdf_file)
                        if pdf_file and os.path.isfile(abs_pdf):
                            st.download_button("Скачать PDF", data=open(abs_pdf, "rb").read(), file_name=os.path.basename(abs_pdf), key=f"station_dl_{station_id}")
                        else:
                            st.caption("PDF не прикреплён")

                        st.divider()
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
                            st.markdown("**Информация (только для чтения)**")
                            # render the same fields but disabled so user can view values
                            station_form({
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
                            }, disabled=True, key_prefix=f"view_station_{station_id}")
                            st.caption("У вас права только для просмотра. Редактирование, удаление и загрузка файлов недоступны.")
        return

    # If we are here — page == 'Сотрудники'
    # Sidebar filters/actions for employees
    st.sidebar.header("Фильтр")
    region = st.sidebar.selectbox("Регион", ["Все", "РРП", "ВМКБ", "РУХО", "РУСО"], index=0)
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
        st.caption(f"Найдено: {len(rows)}")

        for row in rows:
            (
                emp_id, rakami_tabel, last_name, first_name, nasab,
                makon, sanai_kabul, vazifa, phone, dog_no, pdf_file, photo_file
            ) = row
            with st.expander(f"{last_name} {first_name} — {rakami_tabel}", expanded=False):
                cols_top = st.columns([1,2])
                with cols_top[0]:
                    # display photo if present
                    abs_photo = get_abs_path(photo_file)
                    if photo_file and os.path.isfile(abs_photo):
                        try:
                            st.image(Image.open(abs_photo), width=220)
                        except Exception:
                            st.info("Нет фото")
                    else:
                        st.info("Нет фото")

                    # only admins can upload/replace files
                    if st.session_state.get("role") == "admin":
                        up_new_photo = st.file_uploader(f"Заменить фото для {rakami_tabel}", type=["jpg","jpeg","png"], key=f"photo_{emp_id}")
                        if up_new_photo is not None:
                            new_path = safe_write_file(PHOTOS_DIR, up_new_photo.name, up_new_photo.getvalue())
                            update_employee(emp_id, (
                                rakami_tabel, last_name, first_name, nasab, makon, sanai_kabul, vazifa, phone, dog_no,
                                pdf_file or "", new_path
                            ))
                            st.success("Фото обновлено")
                            safe_rerun()

                        up_new_pdf = st.file_uploader(f"Заменить/добавить PDF для {rakami_tabel}", type=["pdf"], key=f"pdf_{emp_id}")
                        if up_new_pdf is not None:
                            new_pdf = safe_write_file(PDFS_DIR, up_new_pdf.name, up_new_pdf.getvalue())
                            update_employee(emp_id, (
                                rakami_tabel, last_name, first_name, nasab, makon, sanai_kabul, vazifa, phone, dog_no,
                                new_pdf, photo_file or ""
                            ))
                            st.success("PDF обновлён")
                            safe_rerun()
                    else:
                        st.caption("Только просмотр — загрузка файлов недоступна")

                with cols_top[1]:
                    st.markdown("**Информация**")
                    info_cols = st.columns(2)
                    with info_cols[0]:
                        st.text(f"Регион: {makon}")
                        st.text(f"Дата приёма: {sanai_kabul}")
                        st.text(f"Телефон: {phone}")
                    with info_cols[1]:
                        st.text(f"Должность: {vazifa}")
                        st.text(f"Дог №: {dog_no}")
                        abs_pdf = get_abs_path(pdf_file)
                        if pdf_file and os.path.isfile(abs_pdf):
                            st.download_button("Скачать PDF", data=open(abs_pdf, "rb").read(), file_name=os.path.basename(abs_pdf), key=f"dl_{emp_id}")
                        else:
                            st.caption("PDF не прикреплён")

                    st.divider()
                    # Edit block: only admins may edit/delete. Viewers see read-only fields.
                    if st.session_state.get("role") == "admin":
                        st.markdown("**Редактировать**")
                        with st.form(f"edit_{emp_id}"):
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
                            save = st.form_submit_button("Сохранить изменения")
                        cols_btn = st.columns(2)
                        if save:
                            new_tabel = vals[0].strip()
                            if not new_tabel:
                                st.error("Табельный № обязателен")
                                st.stop()
                            if tabel_exists(new_tabel, exclude_id=emp_id):
                                st.error("Такой Табельный № уже существует")
                                st.stop()
                            update_employee(emp_id, (
                                new_tabel, vals[1], vals[2], vals[3], vals[4], vals[5], vals[6], vals[7], vals[8], vals[9] or "", vals[10] or ""
                            ))
                            st.success("Сохранено")
                            safe_rerun()
                        with cols_btn[1]:
                            if st.button("Удалить", type="primary", key=f"del_{emp_id}"):
                                delete_employee(emp_id)
                                st.warning("Удалено")
                                safe_rerun()
                    else:
                        st.markdown("**Информация (только для чтения)**")
                        # render the same fields but disabled so user can view values
                        employee_form({
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
                        }, disabled=True, key_prefix=f"view_{emp_id}")
                        st.caption("У вас права только для просмотра. Редактирование, удаление и загрузка файлов недоступны.")

if __name__ == "__main__":
    main()
