import os
import requests
from flask import Flask, request

app = Flask(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}"


@app.route("/", methods=["GET"])
def home():
    return {"ok": True, "service": "Sport AI Telegram Bot"}


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")

        if text == "/start":
            reply = (
                "🏆 Bienvenue sur Sport AI !\n\n"
                "⚽ Pronostics sportifs\n"
                "📊 Analyse des matchs\n"
                "🔥 Sélections du jour\n\n"
                "Le système est en cours de configuration."
            )
        else:
            reply = "Utilise /start pour ouvrir le menu."

        requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": reply
            }
        )

    return {"ok": True}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
