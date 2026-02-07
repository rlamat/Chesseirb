@echo off
setlocal
if not exist venv (
    python -m venv venv
)
call venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python manage.py migrate
@echo.
@echo Environment ready. To activate later: call venv\Scripts\activate
endlocal

