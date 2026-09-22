from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://amir:localdev@localhost:5433/ironcoach"
    ANTHROPIC_API_KEY: str = ""

    # --- Guthaben für die Claude-API ---
    # Alle Athleten laufen über einen Schlüssel; abgerechnet wird je Konto.
    API_BUDGET_EUR: float = 5.0
    API_BUDGET_ENFORCED: bool = True
    # Preise in Dollar je Million Token, getrennt nach Ein- und Ausgabe.
    # Als Text konfigurierbar, damit eine Preisänderung keine Codeänderung
    # verlangt: "modell:eingabe:ausgabe,modell:eingabe:ausgabe".
    MODEL_PRICES: str = "claude-sonnet-4-6:3.0:15.0"
    MODEL_PRICE_FALLBACK: str = "3.0:15.0"
    USD_TO_EUR: float = 0.92
    STRAVA_CLIENT_ID: str = ""
    STRAVA_CLIENT_SECRET: str = ""
    STRAVA_VERIFY_TOKEN: str = "ironcoach_webhook_secret"
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 50

    # --- Obsidian Local REST API ---
    # Leere BASE_URL oder fehlender Key = Integration deaktiviert. Der Sync
    # darf nie blockieren; ohne Konfiguration verhält sich alles wie bisher.
    OBSIDIAN_BASE_URL: str = ""
    OBSIDIAN_API_KEY: str = ""
    OBSIDIAN_VAULT_SUBDIR: str = "Training"
    # Self-signed Cert des Plugins. Läuft der Zugriff über `tailscale serve`,
    # gibt es ein echtes Zertifikat und das hier kann auf True.
    OBSIDIAN_VERIFY_TLS: bool = False
    OBSIDIAN_TIMEOUT_S: float = 5.0
    # SOCKS5-Proxy für den Weg ins private Netz. Wird vom Startskript gesetzt,
    # sobald Tailscale verbunden ist. Ausdrücklich nur für Obsidian und nicht
    # als ALL_PROXY: Sonst liefe auch der Verkehr zu Anthropic, Strava und zum
    # Mailserver durch den Tunnel — langsamer, fehleranfälliger, und bei einem
    # Tailscale-Ausfall stünde die ganze Anwendung statt nur der Vault-Abgleich.
    OBSIDIAN_PROXY: str = ""

    # Öffentliche Adresse dieser Installation — die Adresse, unter der die
    # App erreichbar ist, nicht die eines einzelnen Athleten. Nur für den
    # Strava-Webhook nötig; leer bedeutet lokaler Betrieb.
    PUBLIC_BASE_URL: str = ""

    # Adresse, unter der der Athlet die App im Browser hat. Getrennt von
    # PUBLIC_BASE_URL, weil die beiden auseinanderfallen können: Der
    # Strava-Webhook muss die **API** erreichen, ein Link in einer Mail und
    # die Rückleitung nach einer OAuth-Freigabe dagegen das **Frontend**.
    # Leer heisst: aus PUBLIC_BASE_URL bzw. CORS_ORIGINS ableiten.
    FRONTEND_URL: str = ""

    # --- E-Mail ---
    # Zwei Wege, weil einer allein nicht überall funktioniert:
    #
    # "smtp"  — der klassische Weg, gut für lokalen Betrieb und eigene Server.
    # "brevo" — Versand über HTTPS. Nötig, sobald die Anwendung bei einem
    #           Anbieter läuft, der ausgehendes SMTP sperrt. Railway tut das
    #           auf allen Tarifen unterhalb von Pro: die Verbindung zu
    #           smtp.gmail.com:587 scheitert dort mit "Network is
    #           unreachable", bevor der Mailserver überhaupt antwortet. Port
    #           443 ist davon nicht betroffen.
    #
    # Leer heißt: aus MAIL_HOST bzw. MAIL_API_KEY ableiten, was gesetzt ist.
    MAIL_PROVIDER: str = ""
    MAIL_API_KEY: str = ""

    # Ohne MAIL_HOST und MAIL_FROM wird nichts versendet — die App läuft
    # trotzdem vollständig, Mails werden dann nur protokolliert.
    MAIL_HOST: str = ""
    MAIL_PORT: int = 587
    MAIL_USER: str = ""
    MAIL_PASSWORD: str = ""
    MAIL_FROM: str = ""
    MAIL_FROM_NAME: str = "IronCoach"
    MAIL_STARTTLS: bool = True
    MAIL_SSL: bool = False

    # --- Anmeldung ---
    # Ohne gesetztes Geheimnis gelten Tokens nur bis zum nächsten Neustart.
    JWT_SECRET: str = ""
    # Woher das Frontend kommen darf, kommagetrennt. Lokal reicht die
    # Vorgabe; nach dem Deploy muss die Adresse des Frontends hier stehen,
    # sonst blockiert der Browser jede Anfrage — und zwar stumm, mit einer
    # Meldung, die nur in der Entwicklerkonsole auftaucht.
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    JWT_EXPIRE_HOURS: int = 24 * 14
    # Ausschalten nur für lokale Entwicklung: dann fällt jede Anfrage auf den
    # ersten Nutzer zurück, wie vor der Anmeldung.
    AUTH_REQUIRED: bool = True

    # --- Reconciliation ---
    # Standardmäßig aus: der Job schreibt in die DB und ruft Strava auf.
    RECONCILE_ENABLED: bool = False
    RECONCILE_WINDOW_DAYS: int = 14
    # Wie weit beim **ersten** Verbinden mit Strava zurückgeholt wird.
    #
    # 90 Tage und nicht 14 wie beim laufenden Abgleich: Die Fitness (CTL)
    # ist ein Mittel über 42 Tage. Ein Athlet, der mit zwei Wochen Historie
    # startet, bekommt eine künstlich niedrige Fitness — und eine Form, die
    # daraus folgt. Drei Monate reichen, damit sich der Wert eingeschwungen
    # hat, bevor der erste Plan entsteht.
    STRAVA_BACKFILL_DAYS: int = 90
    RECONCILE_MINUTE: int = 7  # stündlich zu dieser Minute

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in (self.CORS_ORIGINS or "").split(",") if o.strip()]

    @property
    def obsidian_enabled(self) -> bool:
        return bool(self.OBSIDIAN_BASE_URL and self.OBSIDIAN_API_KEY)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


    def model_prices(self, model: str) -> dict:
        """Preise je Million Token für ein Modell.

        Unbekannte Modelle bekommen den Ersatzpreis statt null — sonst
        liefe ein neues Modell kostenlos mit, und das Guthaben wäre wertlos.
        """
        for eintrag in (self.MODEL_PRICES or "").split(","):
            teile = eintrag.strip().split(":")
            if len(teile) == 3 and teile[0] == model:
                return {"input": float(teile[1]), "output": float(teile[2])}
        ein, aus = (self.MODEL_PRICE_FALLBACK or "3.0:15.0").split(":")
        return {"input": float(ein), "output": float(aus)}


settings = Settings()
