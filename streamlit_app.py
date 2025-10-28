import os
import re
import sqlite3
from datetime import datetime
import subprocess
from io import BytesIO

import streamlit as st
from PIL import Image

# --- Paths ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_FILE = os.path.join(DATA_DIR, "employees.db")
PHOTOS_DIR = os.path.join(DATA_DIR, "photos")
PDFS_DIR = os.path.join(DATA_DIR, "pdfs")
os.makedirs(PHOTOS_DIR, exist_ok=True)
os.makedirs(PDFS_DIR, exist_ok=True)


def init_db():
    """Create the employees database and table if they don't exist."""
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
    conn.commit()
    conn.close()

APP_PASSWORD = os.getenv("HR_APP_PASSWORD", "1234")

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
    if "authed" not in st.session_state:
        st.session_state.authed = False
    if st.session_state.authed:
        return True
    st.title("Вход")
    pwd = st.text_input("Пароль", type="password")
    if st.button("Войти"):
        if pwd == APP_PASSWORD:
            st.session_state.authed = True
            st.rerun()
        else:
            st.error("Неверный пароль")
    st.stop()


# --- UI ---

def employee_form(defaults=None):
    defaults = defaults or {}
    cols = st.columns(2)
    with cols[0]:
        rakami_tabel = st.text_input("Табельный №", value=defaults.get("rakami_tabel", ""))
        last_name = st.text_input("Фамилия", value=defaults.get("last_name", ""))
        first_name = st.text_input("Имя", value=defaults.get("first_name", ""))
        nasab = st.text_input("Отчество", value=defaults.get("nasab", ""))
        makon = st.selectbox("Регион", ["РРП", "ВМКБ", "РУХО", "РУСО"], index=0 if defaults.get("makon") not in ["РРП","ВМКБ","РУХО","РУСО"] else ["РРП","ВМКБ","РУХО","РУСО"].index(defaults.get("makon")))
        sanai_kabul = st.text_input("Дата приёма", value=defaults.get("sanai_kabul", ""))
    with cols[1]:
        vazifa = st.text_input("Должность", value=defaults.get("vazifa", ""))
        phone = st.text_input("Телефон", value=defaults.get("phone", ""))
        dog_no = st.text_input("Дог №", value=defaults.get("dog_no", ""))
        pdf_file = defaults.get("pdf_file", "")
        photo_file = defaults.get("photo_file", "")
        st.write("")
    return rakami_tabel, last_name, first_name, nasab, makon, sanai_kabul, vazifa, phone, dog_no, pdf_file, photo_file


def main():
    # Ensure DB and data folders exist before any DB operations
    init_db()

    require_auth()

    st.set_page_config(page_title="Сотрудники ПБК", layout="wide")
    st.title("Сотрудники ПБК")

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

    # --- Navigation: simple main menu ---
    if "page" not in st.session_state:
        st.session_state.page = "Главная"

    st.sidebar.title("Меню")
    page = st.sidebar.radio("", ["Главная", "Сотрудники"], index=0 if st.session_state.page == "Главная" else 1, key="page")

    if page == "Главная":
        st.header("Главное меню")
        st.write("Вы вошли в систему. Используйте меню слева, чтобы перейти в разделы.")
        if st.button("Перейти к сотрудникам"):
            st.session_state.page = "Сотрудники"
            st.experimental_rerun()
        return

    # If we are here — page == 'Сотрудники'
    # Sidebar filters/actions for employees
    st.sidebar.header("Фильтр")
    region = st.sidebar.selectbox("Регион", ["Все", "РРП", "ВМКБ", "РУХО", "РУСО"], index=0)
    search = st.sidebar.text_input("Поиск")
    st.sidebar.divider()
    add_mode = st.sidebar.toggle("Добавить нового сотрудника", value=False)

    # Data table or add form
    if add_mode:
        st.subheader("Добавить сотрудника")
        with st.form("add_form"):
            vals = employee_form()
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
            st.rerun()
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
                    if photo_file and os.path.isfile(photo_file):
                        try:
                            st.image(Image.open(photo_file), width=220)
                        except Exception:
                            st.info("Нет фото")
                    else:
                        st.info("Нет фото")
                    up_new_photo = st.file_uploader(f"Заменить фото для {rakami_tabel}", type=["jpg","jpeg","png"], key=f"photo_{emp_id}")
                    if up_new_photo is not None:
                        new_path = safe_write_file(PHOTOS_DIR, up_new_photo.name, up_new_photo.getvalue())
                        update_employee(emp_id, (
                            rakami_tabel, last_name, first_name, nasab, makon, sanai_kabul, vazifa, phone, dog_no,
                            pdf_file or "", new_path
                        ))
                        st.success("Фото обновлено")
                        st.rerun()

                    up_new_pdf = st.file_uploader(f"Заменить/добавить PDF для {rakami_tabel}", type=["pdf"], key=f"pdf_{emp_id}")
                    if up_new_pdf is not None:
                        new_pdf = safe_write_file(PDFS_DIR, up_new_pdf.name, up_new_pdf.getvalue())
                        update_employee(emp_id, (
                            rakami_tabel, last_name, first_name, nasab, makon, sanai_kabul, vazifa, phone, dog_no,
                            new_pdf, photo_file or ""
                        ))
                        st.success("PDF обновлён")
                        st.rerun()

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
                        if pdf_file and os.path.isfile(pdf_file):
                            st.download_button("Скачать PDF", data=open(pdf_file, "rb").read(), file_name=os.path.basename(pdf_file), key=f"dl_{emp_id}")
                        else:
                            st.caption("PDF не прикреплён")

                    st.divider()
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
                        })
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
                        st.rerun()
                    with cols_btn[1]:
                        if st.button("Удалить", type="primary", key=f"del_{emp_id}"):
                            delete_employee(emp_id)
                            st.warning("Удалено")
                            st.rerun()


if __name__ == "__main__":
    main()
