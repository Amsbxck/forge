"""Passwort eines Kontos setzen — nur mit Zugriff auf den Server.

    docker compose exec backend python -m scripts.set_password mail@example.com

Gedacht für zwei Fälle: ein Altkonto aus der Zeit vor der Anmeldung mit einem
Passwort belegen, und ein vergessenes Passwort zurücksetzen. Beides darf nicht
über die öffentliche Schnittstelle gehen — wer die E-Mail kennt, hätte sonst
Zugriff auf fremde Trainingsdaten.
"""

import getpass
import sys

from core.security import hash_password
from database import SessionLocal
from models import User


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    email = sys.argv[1].strip().lower()
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            print(f"Kein Konto mit {email}")
            return 1

        password = sys.argv[2] if len(sys.argv) > 2 else getpass.getpass("Neues Passwort: ")
        if len(password) < 8:
            print("Mindestens 8 Zeichen")
            return 1

        from datetime import datetime

        user.password_hash = hash_password(password)
        # Wie beim Zurücksetzen über die Mail: bisherige Sitzungen verfallen,
        # und eine Sperre nach Fehlversuchen endet. Vorher blieb beides —
        # wer ausgesperrt war, kam auch mit dem neuen Passwort nicht hinein.
        user.tokens_valid_from = datetime.utcnow()
        user.failed_logins = 0
        user.locked_until = None
        db.commit()
        print(f"Passwort für {email} gesetzt (Nutzer {user.id})")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
