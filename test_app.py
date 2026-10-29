import pytest

import app


@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATABASE_PATH", str(tmp_path / "tasks.sqlite3"))
    app.initialize_database()


def test_seeded_account_authenticates(database):
    user = app.authenticate("admin", "admin123")

    assert user is not None
    assert user["username"] == "admin"
    assert app.authenticate("admin", "wrong-password") is None


def test_tasks_are_isolated_by_user(database):
    app.register_user("student_one", "password-one")
    app.register_user("student_two", "password-two")
    first = app.authenticate("student_one", "password-one")
    second = app.authenticate("student_two", "password-two")

    app.add_task(first["id"], "Essay", "High", app.date(2026, 11, 3), "Pending")
    app.add_task(second["id"], "Lab report", "Medium", app.date(2026, 11, 5), "In Progress")

    assert [task["name"] for task in app.get_tasks(first["id"])] == ["Essay"]
    assert [task["name"] for task in app.get_tasks(second["id"])] == ["Lab report"]

    task_id = app.get_tasks(first["id"])[0]["id"]
    app.update_task_status(second["id"], task_id, "Completed")
    app.delete_task(second["id"], task_id)
    assert app.get_tasks(first["id"])[0]["status"] == "Pending"


@pytest.mark.parametrize(
    ("name", "priority", "status", "due_date"),
    [
        ("  ", "Low", "Pending", app.date(2026, 11, 3)),
        ("Essay", "Urgent", "Pending", app.date(2026, 11, 3)),
        ("Essay", "Low", "Blocked", app.date(2026, 11, 3)),
        ("Essay", "Low", "Pending", "not-a-date"),
    ],
)
def test_invalid_task_values_are_rejected(database, name, priority, status, due_date):
    with pytest.raises(ValueError):
        app.add_task(1, name, priority, due_date, status)