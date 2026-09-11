from datetime import date, datetime
from sqlalchemy import (
    Integer, String, Float, Date, DateTime, Text, BigInteger, ARRAY, Boolean, ForeignKey,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from database import Base


class User(Base):
    """Ein Konto. Alles Trainingsbezogene hängt daran.

    Bis die Anmeldung steht, gibt es genau einen Nutzer und alle Zugriffe
    lösen auf ihn auf — die Datenstruktur ist aber bereits mandantenfähig,
    damit später nur die Auflösung getauscht werden muss.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String)
    # Erst mit der Anmeldung befüllt; vorher existiert der Nutzer ohne Passwort.
    password_hash: Mapped[str | None] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Betreiber der Installation. Betrifft nur Einstellungen, die für alle
    # gelten — etwa den Strava-Webhook, von dem es je Anwendung nur einen gibt.
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # --- Kontosicherheit ---
    # Bestätigte Adresse. Ohne sie kann sich jemand mit einer fremden E-Mail
    # anmelden und der eigentliche Inhaber bekommt das nie mit.
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Ausgegebene Tokens gelten nur, wenn sie nach diesem Zeitpunkt erstellt
    # wurden. Ein JWT lässt sich nicht einsammeln — über diese Marke werden
    # alle Sitzungen auf einmal ungültig: beim Abmelden, beim Passwortwechsel
    # und nach einem Zurücksetzen.
    tokens_valid_from: Mapped[datetime | None] = mapped_column(DateTime)

    # Fehlversuche und Sperre. Ohne Bremse lässt sich ein Passwort beliebig
    # oft raten — bei einer öffentlich erreichbaren Anmeldung reicht das aus.
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime)

    # Zugeteiltes Guthaben für die Claude-API in Euro. Leer heißt: der
    # Standardbetrag aus der Konfiguration gilt. Aufladen bedeutet, diesen
    # Wert zu erhöhen — der Verbrauch selbst wird nie zurückgesetzt, sonst
    # ginge die Historie verloren.
    api_budget_eur: Mapped[float | None] = mapped_column(Float)
    # Bei welchem Schwellenwert zuletzt gewarnt wurde (0.1 = 10 %, 0.0 = leer).
    # Ohne diese Marke ginge nach jedem Aufruf eine Mail raus.
    api_warned_at: Mapped[float | None] = mapped_column(Float)


class AuthAction(Base):
    """Einmal-Token für Passwort-Zurücksetzen und E-Mail-Bestätigung.

    Gespeichert wird nur der Hash: Wer die Datenbank liest, kann damit kein
    Konto übernehmen. Der Klartext existiert genau einmal — im Link, der
    verschickt wird.
    """

    __tablename__ = "auth_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String, nullable=False)   # password_reset | email_verify
    token_hash: Mapped[str] = mapped_column(String, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AthleteProfile(Base):
    __tablename__ = "athlete_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    name: Mapped[str | None] = mapped_column(String)
    # Neutrale Platzhalter, keine echten Werte: bis hierher standen hier
    # Amirs persönliche Zahlen als Vorgabe, sodass jeder neue Athlet mit
    # dessen FTP und dessen Herzfrequenzzonen startete. Was hier steht, gilt
    # nur bis zur Benchmark-Woche — zones_source hält fest, ob gemessen wurde.
    ftp_watts: Mapped[int] = mapped_column(Integer, default=200)

    # Schwellenpace im Wasser (Sekunden je 100 m) aus dem CSS-Test.
    # `css_source` hält fest, woher sie stammt: aus den Runden abgeleitet
    # ("auto") oder eingetragen ("manual"). Ein abgeleiteter Wert ist ein
    # Vorschlag und wird in der Oberfläche als solcher gekennzeichnet.
    css_pace_s_per_100m: Mapped[float | None] = mapped_column(Float)
    # Schwellenpuls im Wasser. Getrennt vom Laufwert, weil der Puls beim
    # Schwimmen bauchlage- und wasserbedingt rund 10 Schläge niedriger liegt:
    # mit dem Laufwert gerechnet fiele jede Schwimm-TSS zu niedrig aus.
    swim_threshold_hr: Mapped[int | None] = mapped_column(Integer)
    swim_threshold_source: Mapped[str | None] = mapped_column(String)

    # Eigene Normalspanne der Herzratenvariabilität. Ohne sie galt für jeden
    # Athleten dieselbe feste Schwelle — bei einer Normallage um 45 stünde
    # die Ampel dauerhaft auf Rot und der Coach striche dauerhaft Intensität.
    # `hrv_green_min` ist die untere Grenze des grünen Bereichs, `hrv_band_high`
    # die obere — so, wie Garmin den ausgeglichenen Bereich anzeigt.
    # `hrv_red_below` wird daraus abgeleitet und mitgespeichert, damit die
    # Bewertung nicht bei jedem Aufruf neu rechnen muss.
    hrv_green_min: Mapped[float | None] = mapped_column(Float)
    hrv_band_high: Mapped[float | None] = mapped_column(Float)
    hrv_red_below: Mapped[float | None] = mapped_column(Float)
    hrv_range_source: Mapped[str | None] = mapped_column(String)
    css_source: Mapped[str | None] = mapped_column(String)
    css_t400_s: Mapped[int | None] = mapped_column(Integer)
    css_t200_s: Mapped[int | None] = mapped_column(Integer)
    max_hr: Mapped[int] = mapped_column(Integer, default=190)
    z1_hr_max: Mapped[int] = mapped_column(Integer, default=133)
    z2_hr_min: Mapped[int] = mapped_column(Integer, default=134)
    z2_hr_max: Mapped[int] = mapped_column(Integer, default=162)
    z3_hr_min: Mapped[int] = mapped_column(Integer, default=163)
    z3_hr_max: Mapped[int] = mapped_column(Integer, default=171)
    z4_hr_min: Mapped[int] = mapped_column(Integer, default=172)
    z4_hr_max: Mapped[int] = mapped_column(Integer, default=181)
    race_date: Mapped[date] = mapped_column(Date, default=date(2026, 8, 31))
    race_goal: Mapped[str] = mapped_column(String, default="sub 5:30h 70.3")
    plan_start_date: Mapped[date] = mapped_column(Date, default=date(2026, 1, 19))

    # Individuelle Trainingsregeln — was bisher als Schienbein-Protokoll fest
    # im Prompt stand. Jeder Athlet pflegt seine eigenen Einschränkungen
    # (Schienbein, Knie, Asthma, Wiedereinstieg), statt fremde aufgedrängt
    # zu bekommen.
    coaching_constraints: Mapped[str | None] = mapped_column(Text)

    # --- Aus Benchmark-Tests abgeleitet ---
    # Die HF-Zonen stehen schon oben; hier kommt dazu, was sich nicht in
    # Herzschlägen ausdrücken lässt: Schwellenpace und Schwimm-CSS.
    threshold_pace_s_per_km: Mapped[int | None] = mapped_column(Integer)

    # Schwellenpuls beim Laufen. Bis hierher gab es dafür kein Feld, und die
    # pulsbasierte TSS rechnete ersatzweise gegen die Obergrenze von Zone 2 —
    # das ist die aerobe Schwelle, nicht die Laktatschwelle, und lag damit
    # systematisch zu niedrig. Ein zu niedriger Bezugswert bläht jede TSS auf.
    threshold_hr: Mapped[int | None] = mapped_column(Integer)
    # "manual" schützt vor dem Überschreiben durch die Ableitung.
    threshold_source: Mapped[str | None] = mapped_column(String)

    # --- Körperdaten ---
    # Merker für das Willkommensfenster. Als einziger Onboarding-Zustand
    # gespeichert statt abgeleitet: Überspringen hinterlässt keine Spur, aus
    # der sich „schon gezeigt" erschließen ließe.
    intake_done_at: Mapped[datetime | None] = mapped_column(DateTime)
    # "manual" | "benchmark" — damit erkennbar bleibt, ob die Zonen gemessen
    # oder von Hand gesetzt wurden.
    zones_source: Mapped[str | None] = mapped_column(String)
    zones_updated_at: Mapped[datetime | None] = mapped_column(DateTime)

    # --- Obsidian je Athlet ---
    # Bis hierher stand die Vault-Anbindung in der .env und zeigte auf genau
    # einen Rechner. Ein zweiter Athlet hätte in fremde Notizen geschrieben.
    obsidian_base_url: Mapped[str | None] = mapped_column(String)
    obsidian_api_key: Mapped[str | None] = mapped_column(String)
    obsidian_vault_subdir: Mapped[str | None] = mapped_column(String)

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class RaceGoal(Base):
    """Worauf hin trainiert wird.

    Ersetzt die festen Felder race_date/race_goal im Profil: Sportart und
    Distanz bestimmen Planlänge, Phasenstruktur und erlaubte Disziplinen.
    Es kann mehrere Ziele geben (vergangene und kommende), aktiv ist eines.
    """

    __tablename__ = "race_goals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    sport: Mapped[str] = mapped_column(String, nullable=False)      # triathlon | running
    distance: Mapped[str] = mapped_column(String, nullable=False)   # sprint | olympic | middle | full | 10k | half_marathon | marathon
    race_date: Mapped[date] = mapped_column(Date, nullable=False)
    race_name: Mapped[str | None] = mapped_column(String)
    goal_time: Mapped[str | None] = mapped_column(String)           # "sub 5:30h"

    # A, B oder C. Nur das A-Rennen bestimmt Planlänge, Phasen und
    # Wochenzählung; B- und C-Rennen liegen in derselben Saison und wirken
    # nur auf die Woche, in die sie fallen. Ohne diese Unterscheidung kapert
    # jeder eingetragene Zwischenwettkampf die gesamte Vorbereitung.
    priority: Mapped[str] = mapped_column(String, default="A")

    # Aus der Distanz vorbelegt, aber überschreibbar: wer 30 Wochen Zeit hat,
    # soll sie nutzen dürfen, auch wenn 24 empfohlen sind.
    plan_weeks: Mapped[int | None] = mapped_column(Integer)
    plan_start_date: Mapped[date | None] = mapped_column(Date)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    @property
    def total_weeks(self) -> int:
        from core.race_types import default_weeks
        return self.plan_weeks or default_weeks(self.sport, self.distance)

    @property
    def label(self) -> str:
        from core.race_types import race_label
        return race_label(self.sport, self.distance)


class RaceResult(Base):
    """Ein absolviertes Rennen.

    Zwei Zwecke: die Achievement-Kachel im Frontend, und Kontext für den
    Coach — bisherige Wettkampfzeiten sind die belastbarste Grundlage für
    eine realistische Zielzeit.
    """

    __tablename__ = "race_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    goal_id: Mapped[int | None] = mapped_column(
        ForeignKey("race_goals.id", ondelete="SET NULL")
    )

    race_date: Mapped[date] = mapped_column(Date, nullable=False)
    race_name: Mapped[str] = mapped_column(String, nullable=False)
    sport: Mapped[str] = mapped_column(String, nullable=False)
    distance: Mapped[str] = mapped_column(String, nullable=False)
    location: Mapped[str | None] = mapped_column(String)

    # Zeiten in Sekunden — als Text ("5:28:14") wäre nichts vergleichbar.
    finish_time_s: Mapped[int | None] = mapped_column(Integer)
    swim_time_s: Mapped[int | None] = mapped_column(Integer)
    t1_time_s: Mapped[int | None] = mapped_column(Integer)
    bike_time_s: Mapped[int | None] = mapped_column(Integer)
    t2_time_s: Mapped[int | None] = mapped_column(Integer)
    run_time_s: Mapped[int | None] = mapped_column(Integer)

    overall_rank: Mapped[int | None] = mapped_column(Integer)
    age_group_rank: Mapped[int | None] = mapped_column(Integer)
    age_group: Mapped[str | None] = mapped_column(String)
    finishers: Mapped[int | None] = mapped_column(Integer)

    notes: Mapped[str | None] = mapped_column(Text)
    # Foto vom Rennen. Nur der Dateiname, nicht der volle Pfad — sonst hinge
    # der Datensatz am Ablageort und ein Umzug bräche jede Verknüpfung.
    image_file: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    @property
    def label(self) -> str:
        from core.race_types import race_label
        return race_label(self.sport, self.distance)


class TrainingSession(Base):
    __tablename__ = "training_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    session_date: Mapped[date] = mapped_column(Date, nullable=False)
    week_number: Mapped[int] = mapped_column(Integer, nullable=False)
    discipline: Mapped[str] = mapped_column(String, nullable=False)
    # Die ursprüngliche Bezeichnung von Strava oder aus der FIT-Datei, etwa
    # "StairStepper" oder "Rowing". `discipline` trägt nur die Kategorie —
    # ohne diese Spalte wäre nach dem Einlesen nicht mehr erkennbar, was es
    # tatsächlich war.
    sport_type: Mapped[str | None] = mapped_column(String)
    duration_min: Mapped[int | None] = mapped_column(Integer)
    distance_km: Mapped[float | None] = mapped_column(Float)
    avg_hr: Mapped[int | None] = mapped_column(Integer)
    max_hr: Mapped[int | None] = mapped_column(Integer)
    avg_watts: Mapped[int | None] = mapped_column(Integer)
    normalized_power: Mapped[int | None] = mapped_column(Integer)
    avg_pace_min_km: Mapped[float | None] = mapped_column(Float)
    tss: Mapped[float | None] = mapped_column(Float)
    rpe: Mapped[int | None] = mapped_column(Integer)
    hr_zones: Mapped[dict | None] = mapped_column(JSONB)
    strava_activity_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    notes: Mapped[str | None] = mapped_column(Text)
    fit_file_path: Mapped[str | None] = mapped_column(String)
    streams: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # --- Ist/Soll-Abgleich (Modul 4) ---
    # Aus den Ist-Daten klassifizierter Trainingstyp; weicht er von der
    # geplanten Session ab, steht der Grund in deviation_note.
    actual_type: Mapped[str | None] = mapped_column(String)
    planned_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("planned_sessions.id", ondelete="SET NULL")
    )
    match_confidence: Mapped[float | None] = mapped_column(Float)
    deviation_note: Mapped[str | None] = mapped_column(Text)

    # --- Obsidian-Sync (Modul 3) ---
    # obsidian_path wird beim ersten Sync gesetzt und danach eingefroren:
    # er ist die Wahrheit, auch wenn sich actual_type später ändert.
    # obsidian_synced_at IS NULL = offene Arbeit für den Reconcile-Job (Outbox).
    obsidian_path: Mapped[str | None] = mapped_column(String)
    obsidian_synced_at: Mapped[datetime | None] = mapped_column(DateTime)
    obsidian_content_hash: Mapped[str | None] = mapped_column(String)

    # Was der Athlet selbst zur Einheit sagt. Bis hierher gab es das nur in
    # Obsidian — wer keinen Vault betreibt, konnte gar nichts festhalten und
    # bekam Pläne allein aus Zahlen. Die Reflexion gehört zur Einheit, nicht
    # zu einem Notizprogramm.
    reflection: Mapped[str | None] = mapped_column(Text)
    reflection_updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Fingerabdruck der zuletzt abgeglichenen Fassung. Ohne ihn lässt sich
    # nicht unterscheiden, ob die App oder der Vault sich geändert hat — und
    # eine Seite überschriebe die andere stillschweigend.
    reflection_sync_hash: Mapped[str | None] = mapped_column(String)

    @property
    def intensity(self) -> str | None:
        """Intensitätsstufe aus den Ist-Daten (base|sweet_spot|threshold|vo2max).

        Die FTP kommt aus dem Athletenprofil, nicht aus einem Standardwert:
        mit 238 statt der echten 264 W rutscht jede Ausfahrt eine Stufe zu
        hoch, und die Anzeige widerspricht dem gespeicherten actual_type.
        """
        from sqlalchemy.orm import object_session
        from services.classification import intensity_from_session

        ftp = 238
        session = object_session(self)
        if session is not None:
            # Profil des Besitzers dieser Einheit — nicht irgendeines.
            query = session.query(AthleteProfile)
            if self.user_id:
                query = query.filter(AthleteProfile.user_id == self.user_id)
            profile = query.first()
            if profile and profile.ftp_watts:
                ftp = profile.ftp_watts
        return intensity_from_session(self, ftp)

    @property
    def intensity_label(self) -> str | None:
        from core.training_types import intensity_label
        return intensity_label(self.intensity)


class HrvMeasurement(Base):
    __tablename__ = "hrv_measurements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    measured_at: Mapped[date] = mapped_column(Date, nullable=False)
    rmssd: Mapped[float] = mapped_column(Float, nullable=False)
    hrv_status: Mapped[str | None] = mapped_column(String)
    readiness_score: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)


class WeeklyPlan(Base):
    __tablename__ = "weekly_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    week_number: Mapped[int] = mapped_column(Integer, nullable=False)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    week_end: Mapped[date] = mapped_column(Date, nullable=False)
    plan_phase: Mapped[str | None] = mapped_column(String)
    plan_content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    plan_text: Mapped[str | None] = mapped_column(Text)
    claude_prompt: Mapped[str | None] = mapped_column(Text)
    adjustments_applied: Mapped[list | None] = mapped_column(ARRAY(Text))
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PlannedSession(Base):
    """Normalisierte Projektion von WeeklyPlan.plan_content["days"].

    plan_content bleibt der Claude-Rohoutput und die Quelle für Anzeige und PDF.
    Diese Tabelle gibt jeder geplanten Einheit eine eigene Identität — nötig für:
      - Drag & Drop, das die Verschiebung persistieren soll (Modul 2)
      - den Ist/Soll-Abgleich, der ein Join-Target braucht (Modul 4)
    Beim Speichern eines Plans wird projiziert; die Projektion ist idempotent
    und ersetzt die Zeilen des jeweiligen Plans komplett.
    """

    __tablename__ = "planned_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("weekly_plans.id", ondelete="CASCADE"), nullable=False
    )
    week_number: Mapped[int] = mapped_column(Integer, nullable=False)

    planned_date: Mapped[date] = mapped_column(Date, nullable=False)
    day_name: Mapped[str | None] = mapped_column(String)

    discipline: Mapped[str] = mapped_column(String, nullable=False)  # bike|run|swim|gym|brick|rest
    training_type: Mapped[str | None] = mapped_column(String)  # sweet_spot|walk_run|...

    duration_min: Mapped[int | None] = mapped_column(Integer)
    target_tss: Mapped[float | None] = mapped_column(Float)
    target_watts_low: Mapped[int | None] = mapped_column(Integer)
    target_watts_high: Mapped[int | None] = mapped_column(Integer)
    target_pace_low_s_per_km: Mapped[int | None] = mapped_column(Integer)
    target_pace_high_s_per_km: Mapped[int | None] = mapped_column(Integer)
    target_hr_zone: Mapped[str | None] = mapped_column(String)
    target_distance_km: Mapped[float | None] = mapped_column(Float)

    details: Mapped[dict | None] = mapped_column(JSONB)  # blocks/warmup/cooldown, frei
    notes: Mapped[str | None] = mapped_column(Text)

    # planned|completed|moved|skipped|replaced
    # "replaced" heißt: an dem Tag wurde etwas anderes gemacht, nicht nichts.
    # Der Unterschied zu "skipped" entscheidet, ob der Plan zurückgefahren
    # wird — eine Wanderung mit Freunden ist Belastung, kein Ausfall.
    status: Mapped[str] = mapped_column(String, default="planned")
    replacement: Mapped[str | None] = mapped_column(Text)
    replacement_min: Mapped[int | None] = mapped_column(Integer)
    moved_from_date: Mapped[date | None] = mapped_column(Date)
    # use_alter: training_sessions verweist zurück auf planned_sessions —
    # ohne das kann create_all() den Zyklus nicht auflösen.
    matched_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("training_sessions.id", ondelete="SET NULL", use_alter=True)
    )

    # Position im Tag-Array des Plans — hält die Projektion stabil, wenn
    # mehrere Einheiten auf denselben Tag fallen.
    day_index: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    @property
    def intensity(self) -> str | None:
        """Intensitätsstufe (base|sweet_spot|threshold|vo2max), nur Rad/Lauf.

        Bewusst abgeleitet statt gespeichert: sie folgt eindeutig aus
        training_type, und eine zweite Quelle könnte davon abweichen.
        """
        from core.training_types import intensity_for_type
        return intensity_for_type(self.discipline, self.training_type, self.target_hr_zone)

    @property
    def intensity_label(self) -> str | None:
        from core.training_types import intensity_label
        return intensity_label(self.intensity)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    context_week: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)



class StravaCredentials(Base):
    __tablename__ = "strava_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    athlete_id: Mapped[int] = mapped_column(Integer, nullable=False)
    access_token: Mapped[str] = mapped_column(String, nullable=False)
    refresh_token: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    scope: Mapped[str] = mapped_column(String, default="activity:read_all")
    connected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class HealthEvent(Base):
    """Krankheit oder Verletzung — eine Trainingsunterbrechung mit Grund.

    Warum als eigene Tabelle und nicht als Notiz: Der Plan muss darauf
    rechnen können. Wie viele Tage weg waren, ob Fieber dabei war und wann es
    vorbei war, entscheidet über Wiedereinstieg und Taper. Als Freitext wäre
    das nur eine Bitte an das Sprachmodell, es zu beachten.

    Ein offenes Ereignis (`end_date is None`) bedeutet: läuft noch.
    """

    __tablename__ = "health_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    kind: Mapped[str] = mapped_column(String, default="illness")     # illness | injury | other
    # mild = über dem Hals (Schnupfen), moderate = Husten/Glieder,
    # severe = Fieber oder ärztlich verordnete Pause.
    severity: Mapped[str] = mapped_column(String, default="mild")
    fever: Mapped[bool] = mapped_column(Boolean, default=False)

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)

    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    @property
    def is_open(self) -> bool:
        return self.end_date is None

    @property
    def days(self) -> int:
        """Dauer in Tagen, angefangene mitgezählt."""
        ende = self.end_date or date.today()
        return max(1, (ende - self.start_date).days + 1)


class ApiUsage(Base):
    """Ein Aufruf der Claude-API, einem Athleten zugeordnet.

    Die Zuordnung ist der Kern der Abrechnung: Alle Athleten teilen sich
    einen Schlüssel, aber jeder verbraucht sein eigenes Guthaben. Ohne diese
    Zeilen ließe sich nicht sagen, wessen Anfrage welche Kosten erzeugt hat.

    Gespeichert werden die tatsächlichen Token aus der Antwort, nicht die
    geschätzten — sonst weicht die Summe von der Rechnung ab.
    """

    __tablename__ = "api_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String, nullable=False)   # plan | chat
    model: Mapped[str] = mapped_column(String, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_eur: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
