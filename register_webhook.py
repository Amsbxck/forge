import subprocess

# Hier die ngrok URL eintragen (nach jedem ngrok Neustart anpassen)
NGROK_URL = "https://unfogging-nippily-nena.ngrok-free.dev"

CLIENT_ID = "216990"
CLIENT_SECRET = "6796073f0f357a35610609d7648db11a25a9ccfc"
VERIFY_TOKEN = "ironcoach_webhook_secret"

callback_url = f"{NGROK_URL}/webhook"

result = subprocess.run([
    "curl", "-X", "POST",
    "https://www.strava.com/api/v3/push_subscriptions",
    "-F", f"client_id={CLIENT_ID}",
    "-F", f"client_secret={CLIENT_SECRET}",
    "-F", f"callback_url={callback_url}",
    "-F", f"verify_token={VERIFY_TOKEN}",
], capture_output=True, text=True)

print(result.stdout)
if result.stderr:
    print(result.stderr)
