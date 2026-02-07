# Chesseirb - Site Django du club d''échecs ENSEIRB

## Installation rapide
- Windows : `setup_windows.bat`
- Linux/macOS : `./setup_linux.sh`

Les scripts créent `venv`, activent l'environnement, installent les dépendances (`requirements.txt`) et lancent les migrations.

## Commandes utiles
- Lancer le serveur : `python manage.py runserver`
- Créer un superuser : `python manage.py createsuperuser`
- Appliquer les migrations : `python manage.py migrate`
- Faire les migrations : `python manage.py makemigrations`

## Accès
- Page principale : `http://127.0.0.1:8000/`
- Connexion / inscription : `/login`, `/signup`
- Gestion tournois (staff) : `/staff/users/` ou `/admin/users/` (comptes inscrits), création/gestion via pages tournois

## Notes
- Le venv et la base SQLite (`db.sqlite3`) sont ignorés par git via `.gitignore`.
