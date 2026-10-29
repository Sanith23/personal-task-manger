import hashlib
import hmac
import os
import secrets
import sqlite3
from contextlib import closing
from datetime import date

import pandas as pd
import streamlit as st


DATABASE_PATH = os.environ.get("TASK_MANAGER_DB", "task_manager.db")
PRIORITIES = ("Low", "Medium", "High")
STATUSES = ("Pending", "In Progress", "Completed")
PASSWORD_ITERATIONS = 310_000


def get_connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def hash_password(password, salt):
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )


def initialize_database():
    with closing(get_connection()) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_salt BLOB NOT NULL,
                password_hash BLOB NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL CHECK(length(trim(name)) BETWEEN 1 AND 120),
                priority TEXT NOT NULL CHECK(priority IN ('Low', 'Medium', 'High')),
                due_date TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('Pending', 'In Progress', 'Completed')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        salt = secrets.token_bytes(16)
        connection.execute(
            """INSERT OR IGNORE INTO users (username, password_salt, password_hash)
               VALUES (?, ?, ?)""",
            ("admin", salt, hash_password("admin123", salt)),
        )
        connection.commit()


def authenticate(username, password):
    with closing(get_connection()) as connection:
        user = connection.execute(
            "SELECT id, username, password_salt, password_hash FROM users WHERE username = ?",
            (username.strip(),),
        ).fetchone()
    if user is None:
        return None
    candidate = hash_password(password, user["password_salt"])
    if hmac.compare_digest(candidate, user["password_hash"]):
        return {"id": user["id"], "username": user["username"]}
    return None


def register_user(username, password):
    username = username.strip()
    if not 3 <= len(username) <= 32 or not username.replace("_", "").isalnum():
        raise ValueError("Use 3–32 letters, numbers, or underscores for your username.")
    if len(password) < 8:
        raise ValueError("Choose a password with at least 8 characters.")
    salt = secrets.token_bytes(16)
    try:
        with closing(get_connection()) as connection:
            connection.execute(
                "INSERT INTO users (username, password_salt, password_hash) VALUES (?, ?, ?)",
                (username, salt, hash_password(password, salt)),
            )
            connection.commit()
    except sqlite3.IntegrityError as error:
        raise ValueError("That username is already taken.") from error


def add_task(user_id, name, priority, due_date, status):
    name = name.strip()
    if not 1 <= len(name) <= 120:
        raise ValueError("Task names must be between 1 and 120 characters.")
    if priority not in PRIORITIES:
        raise ValueError("Choose a valid priority.")
    if status not in STATUSES:
        raise ValueError("Choose a valid status.")
    if not isinstance(due_date, date):
        raise ValueError("Choose a valid due date.")
    with closing(get_connection()) as connection:
        connection.execute(
            "INSERT INTO tasks (user_id, name, priority, due_date, status) VALUES (?, ?, ?, ?, ?)",
            (user_id, name, priority, due_date.isoformat(), status),
        )
        connection.commit()


def get_tasks(user_id):
    with closing(get_connection()) as connection:
        rows = connection.execute(
            """SELECT id, name, priority, due_date, status
               FROM tasks WHERE user_id = ? ORDER BY due_date, id""",
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def update_task_status(user_id, task_id, status):
    if status not in STATUSES:
        raise ValueError("Choose a valid status.")
    with closing(get_connection()) as connection:
        connection.execute(
            "UPDATE tasks SET status = ? WHERE id = ? AND user_id = ?",
            (status, task_id, user_id),
        )
        connection.commit()


def delete_task(user_id, task_id):
    with closing(get_connection()) as connection:
        connection.execute(
            "DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id)
        )
        connection.commit()


def render_login():
    st.markdown('<div class="login-wrap">', unsafe_allow_html=True)
    st.markdown("# Study tasks, in order.")
    st.caption("A quiet place to keep coursework moving.")
    login_tab, signup_tab = st.tabs(["Sign in", "Create account"])

    with login_tab:
        with st.form("login_form"):
            username = st.text_input("Username", autocomplete="username")
            password = st.text_input("Password", type="password", autocomplete="current-password")
            submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)
        if submitted:
            user = authenticate(username, password)
            if user:
                st.session_state.user = user
                st.rerun()
            st.error("Username or password is incorrect.")
        st.caption("Test account: admin / admin123")

    with signup_tab:
        with st.form("signup_form"):
            new_username = st.text_input("Choose a username")
            new_password = st.text_input("Choose a password", type="password")
            confirm_password = st.text_input("Confirm password", type="password")
            submitted = st.form_submit_button("Create account", use_container_width=True)
        if submitted:
            if new_password != confirm_password:
                st.error("The passwords do not match.")
            else:
                try:
                    register_user(new_username, new_password)
                    st.success("Account created. You can sign in now.")
                except ValueError as error:
                    st.error(str(error))
    st.markdown("</div>", unsafe_allow_html=True)


def render_dashboard(user):
    tasks = get_tasks(user["id"])
    total = len(tasks)
    counts = {status: sum(task["status"] == status for task in tasks) for status in STATUSES}

    st.markdown(f"## Good to see you, {user['username']}.")
    today = date.today()
    st.caption(f"Your study plan at a glance · {today:%A}, {today:%B} {today.day}")

    metric_columns = st.columns(4)
    metrics = (
        ("All tasks", total, "task" if total == 1 else "tasks"),
        ("Pending", counts["Pending"], "to get started"),
        ("In progress", counts["In Progress"], "underway"),
        ("Completed", counts["Completed"], "accomplished"),
    )
    for column, (label, value, note) in zip(metric_columns, metrics):
        with column:
            st.markdown(
                f'<div class="metric"><span>{label}</span><strong>{value}</strong><small>{note}</small></div>',
                unsafe_allow_html=True,
            )

    st.markdown("### Workload by status")
    chart_data = pd.DataFrame(
        {"Status": list(STATUSES), "Tasks": [counts[status] for status in STATUSES]}
    )
    st.bar_chart(chart_data, x="Status", y="Tasks", color="#41785d", height=240)

    if tasks:
        upcoming = [task for task in tasks if task["status"] != "Completed"][:5]
        st.markdown("### Next up")
        if upcoming:
            st.dataframe(
                pd.DataFrame(upcoming).drop(columns="id"),
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.success("Everything is complete. Nicely done.")
    else:
        st.info("Your task list is clear. Add a task when you’re ready to plan your next study session.")


def render_add_task(user):
    st.markdown("## Add a task")
    st.caption("Capture the next thing you need to move forward.")
    with st.form("add_task_form", clear_on_submit=True):
        name = st.text_input("Task name", max_chars=120, placeholder="e.g. Review biology lecture notes")
        fields = st.columns(3)
        with fields[0]:
            priority = st.selectbox("Priority", PRIORITIES, index=1)
        with fields[1]:
            due_date = st.date_input("Due date", value=date.today())
        with fields[2]:
            status = st.selectbox("Status", STATUSES)
        submitted = st.form_submit_button("Add task", type="primary")
    if submitted:
        try:
            add_task(user["id"], name, priority, due_date, status)
            st.success("Task added.")
        except ValueError as error:
            st.error(str(error))


def render_tasks(user):
    st.markdown("## Your tasks")
    tasks = get_tasks(user["id"])
    if not tasks:
        st.info("No tasks yet. Add one to start building your study plan.")
        return

    display = pd.DataFrame(tasks).rename(
        columns={"name": "Task", "priority": "Priority", "due_date": "Due date", "status": "Status"}
    )
    st.dataframe(
        display.drop(columns="id"),
        hide_index=True,
        use_container_width=True,
        column_config={
            "Priority": st.column_config.TextColumn("Priority"),
            "Due date": st.column_config.DateColumn("Due date", format="MMM D, YYYY"),
        },
    )

    st.markdown("### Update a task")
    task_by_label = {f"{task['name']} · due {task['due_date']}": task for task in tasks}
    selected_label = st.selectbox("Select task", list(task_by_label))
    selected = task_by_label[selected_label]
    with st.form("update_task_form"):
        new_status = st.selectbox(
            "Status", STATUSES, index=STATUSES.index(selected["status"]), key="updated_status"
        )
        left, right = st.columns([1, 4])
        with left:
            update_submitted = st.form_submit_button("Save status", type="primary")
        with right:
            delete_submitted = st.form_submit_button("Delete task")
    if update_submitted:
        update_task_status(user["id"], selected["id"], new_status)
        st.rerun()
    if delete_submitted:
        delete_task(user["id"], selected["id"])
        st.rerun()


def apply_styles():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=DM+Serif+Display&display=swap');
        :root { --ink: #20352d; --muted: #718078; --green: #41785d; --paper: #f7f8f4; }
        html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
        .stApp { background: var(--paper); color: var(--ink); }
        h1, h2, h3 { font-family: 'DM Serif Display', Georgia, serif !important; color: var(--ink); }
        h2 { font-size: 2rem !important; }
        [data-testid="stSidebar"] { background: #eaf0e9; border-right: 1px solid #dce5dc; }
        [data-testid="stSidebar"] h1 { font-size: 1.5rem; }
        .metric { min-height: 126px; background: #fff; border: 1px solid #e4e9e2; border-top: 3px solid #8da995; padding: 16px 18px; }
        .metric span, .metric small { display: block; color: var(--muted); font-size: .82rem; }
        .metric strong { display: block; font-size: 2rem; line-height: 1.2; color: var(--ink); margin: 8px 0 3px; }
        .login-wrap { max-width: 560px; margin: 8vh auto 0; }
        .login-wrap h1 { font-size: 2.8rem; }
        div.stButton > button[kind="primary"], div.stFormSubmitButton > button[kind="primary"] { background: var(--green); border-color: var(--green); }
        [data-testid="stDataFrame"] { border: 1px solid #e4e9e2; }
        @media (max-width: 700px) { .metric { min-height: 108px; padding: 12px; } .metric strong { font-size: 1.6rem; } }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main():
    st.set_page_config(page_title="Study Tasks", page_icon="📚", layout="wide")
    initialize_database()
    apply_styles()

    user = st.session_state.get("user")
    if user is None:
        render_login()
        return

    with st.sidebar:
        st.markdown("# Study Tasks")
        st.caption(f"Signed in as **{user['username']}**")
        section = st.radio("Workspace", ["Dashboard", "Add Task", "View Tasks"], label_visibility="collapsed")
        st.divider()
        if st.button("Sign out", use_container_width=True):
            del st.session_state.user
            st.rerun()

    if section == "Dashboard":
        render_dashboard(user)
    elif section == "Add Task":
        render_add_task(user)
    else:
        render_tasks(user)


if __name__ == "__main__":
    main()