"""Registrierung, Anmeldung, eigenes Konto."""

import logging
import re
from datetime import date, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from core.deps import require_user
from core.security import (
    create_access_token, hash_action_token, hash_password, lock_duration,
    new_action_token, verify_password,
)
from database import get_db
from models import AthleteProfile, AuthAction, User
from services.account_mail import (
    RESET_HOURS, VERIFY_HOURS, send_password_reset, send_verification,
)
from services.welcome_mail import send_welcome

logger = logging.getLogger(__name__)
router = APIRouter()


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EmailMixin(BaseModel):
    """Nur Formatprüfung — die echte Bestätigung ist, dass die Anmeldung klappt."""

    # Das Feld gehört in den Mixin, sonst hängt der Validator an nichts.
    email: str

    @field_validator("email")
    @classmethod
    def _check_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not EMAIL_RE.match(value):
            raise ValueError("Keine gültige E-Mail-Adresse")
        return value


class Credentials(EmailMixin):
    password: str = Field(min_length=8, description="Mindestens 8 Zeichen")
    name: str | None = None


class LoginIn(EmailMixin):
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    email: str
    name: str | None


def _token_for(user: User) -> TokenOut:
    return TokenOut(
        access_token=create_access_token(user.id, user.email),
        user_id=user.id,
        email=user.email,
        name=user.name,
    )


@router.post("/auth/register", response_model=TokenOut)
def register(
    body: Credentials,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Konto anlegen — oder ein passwortloses Altkonto übernehmen.

    Vor der Anmeldung angelegte Konten haben keinen Passwort-Hash. Sie hier
    übernehmen zu lassen ist der einzige Weg, bestehende Trainingsdaten
    weiterzubenutzen, ohne sie zu kopieren.
    """
    existing = db.query(User).filter(User.email == body.email).first()

    # Kein Übernehmen bestehender Konten. Vor der Anmeldung angelegte Konten
    # haben keinen Passwort-Hash — sie hier belegen zu lassen bedeutete, dass
    # jeder mit Kenntnis der E-Mail ein fremdes Konto samt aller
    # Trainingsdaten übernimmt. Für solche Altkonten gibt es
    # `scripts/set_password.py`, das nur mit Zugriff auf den Server läuft.
    if existing:
        raise HTTPException(status_code=409, detail="E-Mail ist bereits vergeben")

    user = User(
        email=body.email,
        name=body.name,
        password_hash=hash_password(body.password),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Ohne Profil hätte der neue Nutzer weder Zonen noch Planstart, und jede
    # Berechnung liefe in einen Sonderfall.
    # Planstart auf heute, sonst landet ein frisch angelegtes Konto in
    # Woche 33 eines fremden Saisonplans. Das Renndatum ist ein Platzhalter,
    # bis ein echtes Ziel gesetzt wird.
    today = date.today()
    db.add(AthleteProfile(
        user_id=user.id,
        name=body.name,
        plan_start_date=today,
        race_date=today + timedelta(days=180),
        zones_source="default",
    ))
    db.commit()

    logger.info("Neues Konto angelegt: %s", user.email)

    # Bestätigungslink direkt in die Willkommensmail: zwei Mails unmittelbar
    # nach der Registrierung wären eine zu viel, und die Bestätigung ist
    # ohnehin der nächste Schritt.
    verify_token = _issue_action(db, user, "email_verify", VERIFY_HOURS)

    # Im Hintergrund: ein langsamer oder kaputter Mailserver darf die
    # Registrierung nicht aufhalten, und ein Fehlschlag ist kein Grund, ein
    # bereits angelegtes Konto zu verwerfen.
    background.add_task(send_welcome, user.email, user.name, verify_token)

    return _token_for(user)


@router.post("/auth/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()

    # Gesperrte Konten zuerst: ohne diese Prüfung ließe sich weiterraten,
    # solange man nur das richtige Passwort trifft.
    if user and user.locked_until and user.locked_until > datetime.utcnow():
        wartezeit = int((user.locked_until - datetime.utcnow()).total_seconds() // 60) + 1
        raise HTTPException(
            status_code=429,
            detail=f"Zu viele Fehlversuche. Bitte in {wartezeit} Minuten erneut versuchen.",
        )

    # Gleiche Meldung für falsche Adresse und falsches Passwort, damit sich
    # nicht herausfinden lässt, welche Konten existieren.
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        if user:
            user.failed_logins = (user.failed_logins or 0) + 1
            dauer = lock_duration(user.failed_logins)
            if dauer:
                user.locked_until = datetime.utcnow() + dauer
                logger.warning(
                    "Konto %s nach %s Fehlversuchen für %s gesperrt",
                    user.id, user.failed_logins, dauer,
                )
            db.commit()
        raise HTTPException(status_code=401, detail="E-Mail oder Passwort ist falsch")

    if user.failed_logins or user.locked_until:
        user.failed_logins = 0
        user.locked_until = None
        db.commit()
    return _token_for(user)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, description="Mindestens 8 Zeichen")


@router.post("/auth/change-password", response_model=TokenOut)
def change_password(
    body: PasswordChange,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Passwort ändern — nur mit dem alten.

    Ein gültiges Token allein reicht nicht: wer ein fremdes Gerät offen
    vorfindet, könnte sonst den Zugang übernehmen und den Besitzer
    aussperren.
    """
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=401, detail="Aktuelles Passwort ist falsch")
    if body.new_password == body.current_password:
        raise HTTPException(status_code=422, detail="Das neue Passwort ist mit dem alten identisch")

    user.password_hash = hash_password(body.new_password)
    # Alle bisherigen Sitzungen verfallen. Wer das Passwort ändert, will in
    # aller Regel genau das — etwa weil ein Gerät abhandengekommen ist.
    user.tokens_valid_from = datetime.utcnow()
    db.commit()
    db.refresh(user)
    logger.info("Passwort geändert für Nutzer %s, andere Sitzungen beendet", user.id)
    # Frisches Token zurückgeben, damit die eigene Sitzung weiterläuft.
    return _token_for(user)


@router.get("/auth/me")
def me(user: User = Depends(require_user)):
    return {
        "user_id": user.id,
        "email": user.email,
        "name": user.name,
        "email_verified": user.email_verified_at is not None,
        "is_admin": bool(user.is_admin),
    }


# --- Einmal-Token ------------------------------------------------------------

def _issue_action(db: Session, user: User, kind: str, hours: int) -> str:
    """Neues Einmal-Token anlegen und den Klartext zurückgeben.

    Offene Token derselben Art werden entwertet: sonst blieben ältere Links
    aus früheren Anforderungen gültig, und ein abgefangener alter Link
    öffnete das Konto noch Stunden später.
    """
    db.query(AuthAction).filter(
        AuthAction.user_id == user.id,
        AuthAction.kind == kind,
        AuthAction.used_at.is_(None),
    ).update({"used_at": datetime.utcnow()})

    klartext, token_hash = new_action_token()
    db.add(AuthAction(
        user_id=user.id,
        kind=kind,
        token_hash=token_hash,
        expires_at=datetime.utcnow() + timedelta(hours=hours),
    ))
    db.commit()
    return klartext


def _consume_action(db: Session, token: str, kind: str) -> User:
    """Token einlösen. Wirft 400, wenn es ungültig, abgelaufen oder benutzt ist."""
    eintrag = (
        db.query(AuthAction)
        .filter(
            AuthAction.token_hash == hash_action_token(token),
            AuthAction.kind == kind,
        )
        .first()
    )
    if eintrag is None or eintrag.used_at is not None or eintrag.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=400,
            detail="Der Link ist ungültig oder abgelaufen. Fordere einen neuen an.",
        )

    user = db.query(User).filter(User.id == eintrag.user_id).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=400, detail="Das Konto existiert nicht mehr")

    eintrag.used_at = datetime.utcnow()
    return user


# --- E-Mail bestätigen -------------------------------------------------------

class TokenIn(BaseModel):
    token: str


@router.post("/auth/verify-email", response_model=TokenOut)
def verify_email(body: TokenIn, db: Session = Depends(get_db)):
    """Adresse bestätigen. Meldet gleich an, damit der Link direkt in die App führt."""
    user = _consume_action(db, body.token, "email_verify")
    if user.email_verified_at is None:
        user.email_verified_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    logger.info("E-Mail bestätigt für Nutzer %s", user.id)
    return _token_for(user)


@router.post("/auth/resend-verification")
def resend_verification(
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    if user.email_verified_at is not None:
        return {"status": "bereits_bestaetigt"}
    token = _issue_action(db, user, "email_verify", VERIFY_HOURS)
    background.add_task(send_verification, user.email, user.name, token)
    return {"status": "verschickt", "gueltig_stunden": VERIFY_HOURS}


# --- Passwort vergessen ------------------------------------------------------

class ForgotIn(EmailMixin):
    pass


@router.post("/auth/forgot-password")
def forgot_password(
    body: ForgotIn,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Link zum Zurücksetzen anfordern.

    Antwortet immer gleich, egal ob die Adresse existiert. Andernfalls ließe
    sich über dieses Feld herausfinden, wer ein Konto hat.
    """
    user = db.query(User).filter(User.email == body.email).first()
    if user and user.is_active:
        token = _issue_action(db, user, "password_reset", RESET_HOURS)
        background.add_task(send_password_reset, user.email, user.name, token)
        logger.info("Passwort-Zurücksetzen angefordert für Nutzer %s", user.id)
    else:
        logger.info("Zurücksetzen für unbekannte Adresse angefordert: %s", body.email)

    return {
        "status": "ok",
        "message": (
            "Falls ein Konto mit dieser Adresse existiert, ist eine E-Mail unterwegs. "
            f"Der Link gilt {RESET_HOURS} Stunden."
        ),
    }


class ResetIn(BaseModel):
    token: str
    new_password: str = Field(min_length=8, description="Mindestens 8 Zeichen")


@router.post("/auth/reset-password", response_model=TokenOut)
def reset_password(body: ResetIn, db: Session = Depends(get_db)):
    """Neues Passwort setzen und sofort anmelden."""
    user = _consume_action(db, body.token, "password_reset")

    user.password_hash = hash_password(body.new_password)
    # Wer das Passwort zurücksetzt, hat es vermutlich nicht mehr allein in
    # der Hand: alle bestehenden Sitzungen verfallen.
    user.tokens_valid_from = datetime.utcnow()
    # Die Sperre entfällt — der Zugang ist über die Mailadresse belegt.
    user.failed_logins = 0
    user.locked_until = None
    # Wer den Link in seinem Postfach öffnen konnte, hat die Adresse belegt.
    if user.email_verified_at is None:
        user.email_verified_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    logger.info("Passwort zurückgesetzt für Nutzer %s", user.id)
    return _token_for(user)


# --- Sitzungen ---------------------------------------------------------------

@router.post("/auth/logout")
def logout(db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Abmelden — auf allen Geräten.

    Das Token im Browser zu löschen reicht nicht: eine Kopie davon gilt sonst
    noch bis zum Ablauf weiter. Hier wird die Marke am Konto gesetzt, gegen
    die jede Anfrage geprüft wird.
    """
    user.tokens_valid_from = datetime.utcnow()
    db.commit()
    logger.info("Nutzer %s hat alle Sitzungen beendet", user.id)
    return {"status": "abgemeldet"}


# --- Daten mitnehmen und Konto löschen ---------------------------------------

@router.get("/auth/export")
def export_data(db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Alle eigenen Daten als JSON.

    Auskunft und Übertragbarkeit sind kein Zusatz, sondern Pflicht — und ohne
    Export wäre das Löschen unten eine Sackgasse.
    """
    from services.account_export import build_export

    return build_export(db, user)


class DeleteIn(BaseModel):
    password: str
    confirm: str = Field(description='Zur Bestätigung "LÖSCHEN" eintippen')


@router.delete("/auth/account")
def delete_account(
    body: DeleteIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Konto und alle Daten löschen. Endgültig.

    Passwort und ein getipptes Wort: ein Klick allein soll Jahre an
    Trainingsdaten nicht auslöschen können.
    """
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Passwort ist falsch")
    if body.confirm.strip().upper() != "LÖSCHEN":
        raise HTTPException(status_code=422, detail='Bitte "LÖSCHEN" zur Bestätigung eintippen')

    from services.account_export import delete_user_data

    zusammenfassung = delete_user_data(db, user)
    logger.info("Konto %s gelöscht: %s", user.id, zusammenfassung)
    return {"status": "geloescht", "entfernt": zusammenfassung}
