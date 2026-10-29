# Study Tasks

A local task manager for students, built with Streamlit and SQLite. Each account sees and manages only its own tasks. Passwords are stored as salted PBKDF2 hashes.

## Run on Windows

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

Sign in with the seeded test account `admin` / `admin123`, or create another account. The SQLite database is created as `task_manager.db` in the current directory. Set `TASK_MANAGER_DB` to use a different local database path.

## Run tests

```powershell
python -m pip install -r requirements-dev.txt
pytest
```

The seeded admin credentials are intended for local testing. Change the password or remove the test account before exposing the app to other people.