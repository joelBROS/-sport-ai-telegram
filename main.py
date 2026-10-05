import os
import html
import time
from datetime import datetime

import requests
from flask import Flask, request

app = Flask(__name__)

# =========================================================
# CONFIGURATION
# =========================================================

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY")

TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}"
FOOTBALL_API = "https://v3.football.api-sports.io"

# Ligues suivies
LEAGUES = {
    "Premier League": 39,
    "La Liga": 140,
    "Serie A": 135,
    "Bundesliga": 78,
    "Ligue 1": 61,
    "Champions League": 2,
}

SEASON = 2026

# Cache pour éviter de consommer inutilement les 100 requêtes/jour
MATCHES_CACHE = {
    "time": 0,
    "data": []
}

PREDICTIONS_CACHE = {}

CACHE_DURATION = 600  # 10 minutes


# =========================================================
# TELEGRAM
# =========================================================

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
        response = requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json=data,
            timeout=15
        )

        if response.status_code != 200:
            print("Telegram error:", response.text)

    except Exception as e:
        print("Telegram error:", e)


def answer_callback(callback_id):

    try:
        requests.post(
            f"{TELEGRAM_API}/answerCallbackQuery",
            json={
                "callback_query_id": callback_id
            },
            timeout=10
        )
    except Exception:
        pass


# =========================================================
# API-FOOTBALL
# =========================================================

def football_get(endpoint, params=None):

    if not API_FOOTBALL_KEY:
        print("API_FOOTBALL_KEY manquante.")
        return None

    headers = {
        "x-apisports-key": API_FOOTBALL_KEY
    }

    try:

        response = requests.get(
            f"{FOOTBALL_API}/{endpoint}",
            headers=headers,
            params=params or {},
            timeout=15
        )

        print(
            "API Football:",
            endpoint,
            response.status_code,
            response.headers.get(
                "x-ratelimit-requests-remaining",
                "?"
            ),
            "requests restantes"
        )

        if response.status_code != 200:
            print("API error:", response.text)
            return None

        data = response.json()

        if data.get("errors"):
            print("API errors:", data["errors"])
            return None

        return data

    except Exception as e:
        print("Football API error:", e)
        return None


# =========================================================
# MATCHS
# =========================================================

def get_matches():

    now = time.time()

    # Utiliser le cache pendant 10 minutes
    if (
        MATCHES_CACHE["data"]
        and now - MATCHES_CACHE["time"] < CACHE_DURATION
    ):
        return MATCHES_CACHE["data"]

    today = datetime.now().strftime("%Y-%m-%d")

    matches = []

    for league_name, league_id in LEAGUES.items():

        data = football_get(
            "fixtures",
            {
                "league": league_id,
                "season": SEASON,
                "date": today,
                "timezone": "Africa/Douala"
            }
        )

        if not data:
            continue

        for fixture in data.get("response", []):

            try:

                fixture_info = fixture.get("fixture", {})
                teams = fixture.get("teams", {})
                league = fixture.get("league", {})

                home = teams.get("home", {})
                away = teams.get("away", {})
                status = fixture_info.get("status", {})

                match = {
                    "id": fixture_info.get("id"),
                    "league": league_name,
                    "home": home.get("name", "Équipe"),
                    "away": away.get("name", "Équipe"),
                    "home_id": home.get("id"),
                    "away_id": away.get("id"),
                    "date": fixture_info.get("date"),
                    "status": status.get("short", ""),
                    "status_long": status.get(
                        "long",
                        ""
                    )
                }

                matches.append(match)

            except Exception as e:
                print("Erreur fixture:", e)

    # Trier par heure
    matches.sort(
        key=lambda x: x.get("date") or ""
    )

    MATCHES_CACHE["time"] = time.time()
    MATCHES_CACHE["data"] = matches

    return matches


# =========================================================
# FORMAT HEURE
# =========================================================

def format_time(date_string):

    if not date_string:
        return "—"

    try:

        dt = datetime.fromisoformat(
            date_string.replace("Z", "+00:00")
        )

        return dt.astimezone().strftime("%H:%M")

    except Exception:
        return "—"


# =========================================================
# PRONOSTICS
# =========================================================

def get_prediction(fixture_id):

    if not fixture_id:
        return None

    # Cache individuel
    if fixture_id in PREDICTIONS_CACHE:

        saved = PREDICTIONS_CACHE[fixture_id]

        if time.time() - saved["time"] < CACHE_DURATION:
            return saved["data"]

    data = football_get(
        "predictions",
        {
            "fixture": fixture_id
        }
    )

    if not data:
        return None

    response = data.get("response", [])

    if not response:
        return None

    prediction = response[0].get(
        "predictions",
        {}
    )

    result = {
        "winner": (
            prediction.get("winner") or {}
        ).get("name"),

        "winner_comment": (
            prediction.get("winner") or {}
        ).get("comment"),

        "advice": prediction.get("advice"),

        "home_percent": (
            prediction.get("percent") or {}
        ).get("home"),

        "draw_percent": (
            prediction.get("percent") or {}
        ).get("draw"),

        "away_percent": (
            prediction.get("percent") or {}
        ).get("away"),

        "under_over": prediction.get("under_over"),

        "home_goals": (
            prediction.get("goals") or {}
        ).get("home"),

        "away_goals": (
            prediction.get("goals") or {}
        ).get("away"),

        "win_or_draw": prediction.get("win_or_draw"),

        "both_teams_score": prediction.get(
            "under_over"
        )
    }

    PREDICTIONS_CACHE[fixture_id] = {
        "time": time.time(),
        "data": result
    }

    return result


# =========================================================
# COTES
# =========================================================

def get_odds(fixture_id):

    if not fixture_id:
        return None

    data = football_get(
        "odds",
        {
            "fixture": fixture_id
        }
    )

    if not data:
        return None

    response = data.get("response", [])

    if not response:
        return None

    home_odd = None
    draw_odd = None
    away_odd = None

    bookmakers = response[0].get(
        "bookmakers",
        []
    )

    # Chercher le marché 1X2 / Match Winner
    for bookmaker in bookmakers:

        bets = bookmaker.get("bets", [])

        for bet in bets:

            name = str(
                bet.get("name", "")
            ).lower()

            if name not in (
                "match winner",
                "1x2"
            ):
                continue

            for value in bet.get("values", []):

                value_name = str(
                    value.get("value", "")
                ).lower()

                odd = value.get("odd")

                if value_name == "home":
                    home_odd = odd

                elif value_name == "draw":
                    draw_odd = odd

                elif value_name == "away":
                    away_odd = odd

            if (
                home_odd
                or draw_odd
                or away_odd
            ):
                return {
                    "home": home_odd,
                    "draw": draw_odd,
                    "away": away_odd,
                    "bookmaker": bookmaker.get(
                        "name",
                        ""
                    )
                }

    return None


# =========================================================
# MATCHS DU JOUR
# =========================================================

def matches_message():

    matches = get_matches()

    if not matches:

        return (
            "⚽ <b>MATCHS DU JOUR</b>\n\n"
            "Aucun match disponible actuellement.\n\n"
            "Vérifie que la clé API-Football "
            "est correctement configurée."
        )

    text = "⚽ <b>MATCHS DU JOUR</b>\n\n"

    current_league = ""

    for match in matches[:30]:

        league = html.escape(
            match["league"]
        )

        home = html.escape(
            match["home"]
        )

        away = html.escape(
            match["away"]
        )

        if league != current_league:

            current_league = league

            text += (
                f"\n🏆 <b>{league}</b>\n"
            )

        status = match["status"]

        # Match terminé / en cours
        if status in (
            "FT",
            "AET",
            "PEN"
        ):
            time_text = "Terminé"

        elif status in (
            "1H",
            "2H",
            "HT",
            "ET",
            "BT",
            "P"
        ):
            time_text = "🔴 EN DIRECT"

        else:
            time_text = format_time(
                match["date"]
            )

        text += (
            f"⚽ <b>{home}</b> - "
            f"<b>{away}</b>\n"
            f"🕐 {time_text}\n\n"
        )

    return text


# =========================================================
# ANALYSE / PRONOSTICS
# =========================================================

def prediction_message():

    matches = get_matches()

    if not matches:

        return (
            "🔮 <b>PRONOSTICS</b>\n\n"
            "Aucun match disponible."
        )

    # Maximum 8 analyses pour protéger le quota
    selected = matches[:8]

    text = (
        "🔮 <b>PRONOSTICS DU JOUR</b>\n\n"
        "Analyse basée sur les données "
        "API-Football.\n\n"
    )

    count = 0

    for match in selected:

        # On ignore les matchs déjà terminés
        if match["status"] in (
            "FT",
            "AET",
            "PEN"
        ):
            continue

        prediction = get_prediction(
            match["id"]
        )

        if not prediction:
            continue

        count += 1

        home = html.escape(
            match["home"]
        )

        away = html.escape(
            match["away"]
        )

        home_percent = (
            prediction["home_percent"]
            or "?"
        )

        draw_percent = (
            prediction["draw_percent"]
            or "?"
        )

        away_percent = (
            prediction["away_percent"]
            or "?"
        )

        winner = html.escape(
            prediction["winner"]
            or "Indéterminé"
        )

        advice = html.escape(
            prediction["advice"]
            or "Aucun conseil disponible"
        )

        score_home = (
            prediction["home_goals"]
            or "?"
        )

        score_away = (
            prediction["away_goals"]
            or "?"
        )

        text += (
            f"🏆 <b>{html.escape(match['league'])}</b>\n"
            f"⚽ <b>{home} - {away}</b>\n\n"

            f"📊 <b>Probabilités</b>\n"
            f"🏠 1 : {home_percent}%\n"
            f"🤝 X : {draw_percent}%\n"
            f"✈️ 2 : {away_percent}%\n\n"

            f"🎯 <b>Favori :</b> {winner}\n"
            f"🔮 <b>Score prévu :</b> "
            f"{score_home} - {score_away}\n"
            f"💡 <b>Conseil :</b> {advice}\n"
        )

        # Essayer de récupérer les cotes
        odds = get_odds(match["id"])

        if odds:

            text += (
                f"\n💰 <b>Cotes 1X2</b>\n"
                f"🏠 1 : {odds['home'] or '—'}\n"
                f"🤝 X : {odds['draw'] or '—'}\n"
                f"✈️ 2 : {odds['away'] or '—'}\n"
            )

        text += "\n━━━━━━━━━━━━━━\n\n"

    if count == 0:

        return (
            "🔮 <b>PRONOSTICS</b>\n\n"
            "Aucune prédiction disponible "
            "pour les matchs actuellement récupérés."
        )

    text += (
        "⚠️ <i>Les probabilités sont des "
        "données de l'API et ne garantissent "
        "pas le résultat d'un match.</i>"
    )

    return text


# =========================================================
# SÉLECTIONS
# =========================================================

def selections_message():

    matches = get_matches()

    if not matches:

        return (
            "🔥 <b>SÉLECTIONS DU JOUR</b>\n\n"
            "Aucun match disponible."
        )

    candidates = []

    # On limite volontairement les appels
    for match in matches[:8]:

        if match["status"] in (
            "FT",
            "AET",
            "PEN"
        ):
            continue

        prediction = get_prediction(
            match["id"]
        )

        if not prediction:
            continue

        home_percent = float(
            prediction["home_percent"]
            or 0
        )

        draw_percent = float(
            prediction["draw_percent"]
            or 0
        )

        away_percent = float(
            prediction["away_percent"]
            or 0
        )

        best = max(
            home_percent,
            draw_percent,
            away_percent
        )

        if best >= 55:

            if best == home_percent:
                pick = "1"
            elif best == away_percent:
                pick = "2"
            else:
                pick = "X"

            candidates.append(
                (
                    best,
                    match,
                    pick,
                    prediction
                )
            )

    candidates.sort(
        key=lambda x: x[0],
        reverse=True
    )

    if not candidates:

        return (
            "🔥 <b>SÉLECTIONS DU JOUR</b>\n\n"
            "Aucune sélection n'atteint "
            "actuellement le seuil de confiance "
            "de 55%.\n\n"
            "🎯 Sport AI préfère ne rien proposer "
            "plutôt que d'inventer une sélection."
        )

    text = (
        "🔥 <b>SÉLECTIONS DU JOUR</b>\n\n"
        "Sélections filtrées à partir des "
        "probabilités disponibles.\n\n"
    )

    for score, match, pick, prediction in candidates[:5]:

        if pick == "1":
            label = "Victoire domicile"
        elif pick == "2":
            label = "Victoire extérieur"
        else:
            label = "Match nul"

        odds = get_odds(
            match["id"]
        )

        text += (
            f"⚽ <b>{html.escape(match['home'])} "
            f"- {html.escape(match['away'])}</b>\n"
            f"🎯 <b>{label}</b>\n"
            f"📊 Confiance : <b>{score:.0f}%</b>\n"
        )

        if odds:

            if pick == "1":
                odd = odds["home"]
            elif pick == "2":
                odd = odds["away"]
            else:
                odd = odds["draw"]

            if odd:
                text += (
                    f"💰 Cote : <b>{odd}</b>\n"
                )

        text += "\n"

    text += (
        "⚠️ <i>Une probabilité élevée "
        "n'est jamais une garantie de gain.</i>"
    )

    return text


# =========================================================
# MENU
# =========================================================

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


# =========================================================
# ROUTES
# =========================================================

@app.route("/", methods=["GET"])
def home():

    return {
        "ok": True,
        "service": "Sport AI",
        "status": "online",
        "api_football": bool(API_FOOTBALL_KEY)
    }


@app.route("/webhook", methods=["POST"])
def webhook():

    data = request.get_json(
        silent=True
    ) or {}

    # =====================================================
    # MESSAGE TELEGRAM
    # =====================================================

    if "message" in data:

        message = data["message"]

        chat_id = message["chat"]["id"]

        text = message.get(
            "text",
            ""
        ).strip()

        if text == "/start":

            welcome = (
                "🏆 <b>Bienvenue sur Sport AI !</b>\n\n"
                "⚽ Matchs réels\n"
                "📊 Analyse des données\n"
                "🔮 Pronostics\n"
                "💰 Cotes disponibles\n"
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
                "Utilise /start pour ouvrir "
                "le menu de Sport AI.",
                main_menu()
            )

    # =====================================================
    # BOUTONS TELEGRAM
    # =====================================================

    if "callback_query" in data:

        callback = data["callback_query"]

        chat_id = callback["message"]["chat"]["id"]

        callback_id = callback["id"]

        action = callback.get(
            "data"
        )

        answer_callback(
            callback_id
        )

        if action == "matches":

            send_message(
                chat_id,
                matches_message(),
                main_menu()
            )

        elif action == "predictions":

            send_message(
                chat_id,
                prediction_message(),
                main_menu()
            )

        elif action == "analysis":

            text = (
                "📊 <b>ANALYSE D'UN MATCH</b>\n\n"
                "La prochaine étape permettra "
                "d'analyser directement un match "
                "précis à partir de son nom.\n\n"
                "Exemple :\n"
                "<code>Real Madrid vs Barcelona</code>"
            )

            send_message(
                chat_id,
                text,
                main_menu()
            )

        elif action == "selections":

            send_message(
                chat_id,
                selections_message(),
                main_menu()
            )

    return {
        "ok": True
    }


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
