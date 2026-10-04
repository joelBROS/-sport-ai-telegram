import os
import requests
from flask import Flask, request

app = Flask(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}"

# Ligues suivies
LEAGUES = {
    "Premier League": "eng.1",
    "La Liga": "esp.1",
    "Serie A": "ita.1",
    "Bundesliga": "ger.1",
    "Ligue 1": "fra.1",
    "Champions League": "uefa.champions",
}


def send_message(chat_id, text, keyboard=None):
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }

    if keyboard:
        data["reply_markup"] = {
            "inline_keyboard": keyboard
        }

    try:
        requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json=data,
            timeout=15
        )
    except Exception as e:
        print("Telegram error:", e)


def get_matches():
    matches = []

    for league_name, league_code in LEAGUES.items():
        try:
            url = (
                "https://site.api.espn.com/apis/site/v2/"
                f"sports/soccer/{league_code}/scoreboard"
            )

            response = requests.get(url, timeout=10)

            if response.status_code != 200:
                continue

            data = response.json()

            for event in data.get("events", []):
                competition = event.get("competitions", [{}])[0]
                competitors = competition.get("competitors", [])

                if len(competitors) < 2:
                    continue

                home = None
                away = None

                for team in competitors:
                    if team.get("homeAway") == "home":
                        home = team
                    elif team.get("homeAway") == "away":
                        away = team

                if not home or not away:
                    continue

                status = event.get("status", {}).get(
                    "type", {}
                ).get("shortDetail", "")

                matches.append({
                    "league": league_name,
                    "home": home.get("team", {}).get("displayName", "Équipe"),
                    "away": away.get("team", {}).get("displayName", "Équipe"),
                    "status": status
                })

        except Exception as e:
            print(f"Erreur {league_name}:", e)

    return matches


def matches_message():
    matches = get_matches()

    if not matches:
        return (
            "⚽ <b>Matchs du jour</b>\n\n"
            "Aucun match n'a pu être récupéré actuellement.\n\n"
            "Réessaie dans quelques instants."
        )

    text = "⚽ <b>MATCHS DU JOUR</b>\n\n"

    current_league = ""

    for match in matches[:30]:

        if match["league"] != current_league:
            current_league = match["league"]
            text += f"\n🏆 <b>{current_league}</b>\n"

        text += (
            f"⚽ {match['home']} - {match['away']}\n"
            f"🕐 {match['status']}\n\n"
        )

    return text


def main_menu():
    return [
        [
            {
                "text": "⚽ Matchs du jour",
                "callback_data": "matches"
            }
        ],
        [
            {
                "text": "🔮 Pronostics",
                "callback_data": "predictions"
            },
            {
                "text": "📊 Analyse",
                "callback_data": "analysis"
            }
        ],
        [
            {
                "text": "🔥 Sélections du jour",
                "callback_data": "selections"
            }
        ]
    ]


@app.route("/", methods=["GET"])
def home():
    return {
        "ok": True,
        "service": "Sport AI",
        "status": "online"
    }


@app.route("/webhook", methods=["POST"])
def webhook():

    data = request.get_json(silent=True) or {}

    # Message Telegram
    if "message" in data:

        message = data["message"]
        chat_id = message["chat"]["id"]
        text = message.get("text", "")

        if text == "/start":

            welcome = (
                "🏆 <b>Bienvenue sur Sport AI !</b>\n\n"
                "⚽ Données football\n"
                "📊 Analyse des matchs\n"
                "🔮 Pronostics\n"
                "🔥 Sélections du jour\n\n"
                "<i>Choisis une option :</i>"
            )

            send_message(
                chat_id,
                welcome,
                main_menu()
            )

        else:

            send_message(
                chat_id,
                "Utilise /start pour ouvrir le menu de Sport AI.",
                main_menu()
            )

    # Boutons Telegram
    if "callback_query" in data:

        callback = data["callback_query"]
        chat_id = callback["message"]["chat"]["id"]
        callback_id = callback["id"]
        action = callback.get("data")

        # Accuser réception du bouton
        try:
            requests.post(
                f"{TELEGRAM_API}/answerCallbackQuery",
                json={"callback_query_id": callback_id},
                timeout=10
            )
        except Exception:
            pass

        if action == "matches":

            send_message(
                chat_id,
                matches_message(),
                main_menu()
            )

        elif action == "predictions":

            text = (
                "🔮 <b>PRONOSTICS</b>\n\n"
                "Le moteur de pronostics est en préparation.\n\n"
                "Nous allons combiner :\n"
                "• forme récente\n"
                "• résultats domicile/extérieur\n"
                "• buts marqués/encaissés\n"
                "• statistiques des équipes\n"
                "• cotes disponibles\n\n"
                "⚠️ Aucun pourcentage ne sera inventé."
            )

            send_message(
                chat_id,
                text,
                main_menu()
            )

        elif action == "analysis":

            text = (
                "📊 <b>ANALYSE D'UN MATCH</b>\n\n"
                "Envoie-moi ensuite un match sous cette forme :\n\n"
                "<code>Real Madrid vs Barcelona</code>\n\n"
                "Le moteur pourra alors préparer l'analyse."
            )

            send_message(
                chat_id,
                text,
                main_menu()
            )

        elif action == "selections":

            text = (
                "🔥 <b>SÉLECTIONS DU JOUR</b>\n\n"
                "Cette section sera alimentée avec les données "
                "réelles des matchs disponibles.\n\n"
                "🎯 Objectif : proposer uniquement les sélections "
                "pour lesquelles les données sont suffisantes."
            )

            send_message(
                chat_id,
                text,
                main_menu()
            )

    return {"ok": True}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(
        host="0.0.0.0",
        port=port
    )
