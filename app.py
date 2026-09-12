import html
import io
import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, flash, jsonify, redirect, render_template, request, send_file, url_for
from PIL import Image, ImageDraw, ImageFont

VERSION = "1.0.0"
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = DATA_DIR / "state.json"
BASE_IMAGE = DATA_DIR / "oroscopo-base.jpg"
LOG_FILE = DATA_DIR / "app.log"
TZ = ZoneInfo(os.getenv("TZ", "Europe/Rome"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
log = logging.getLogger("oroscopo")

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "cambia-questa-chiave")
lock = threading.Lock()

SIGNS = [
    ("Aries", "♈", "Ariete"), ("Taurus", "♉", "Toro"),
    ("Gemini", "♊", "Gemelli"), ("Cancer", "♋", "Cancro"),
    ("Leo", "♌", "Leone"), ("Virgo", "♍", "Vergine"),
    ("Libra", "♎", "Bilancia"), ("Scorpio", "♏", "Scorpione"),
    ("Sagittarius", "♐", "Sagittario"), ("Capricorn", "♑", "Capricorno"),
    ("Aquarius", "♒", "Acquario"), ("Pisces", "♓", "Pesci"),
]


def env_bool(name, default=False):
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


def load_state():
    default = {
        "automation_enabled": env_bool("AUTOMATION_ENABLED", False),
        "last_publish": None, "last_url": None, "last_error": None,
        "image_x": 50, "image_y": 77, "font_size": 72,
        "text_color": "#ffffff", "stroke_color": "#000000", "stroke_width": 2,
    }
    if STATE_FILE.exists():
        try:
            default.update(json.loads(STATE_FILE.read_text(encoding="utf-8")))
        except Exception:
            log.exception("Stato non leggibile: uso i valori predefiniti")
    return default


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def wp_headers():
    return {"User-Agent": "OroscopoMontagnePaesi/1.0"}


def wp_auth():
    return (os.getenv("WP_USERNAME", ""), os.getenv("WP_APP_PASSWORD", ""))


def wp_base():
    return os.getenv("WP_URL", "https://www.montagneepaesi.com").rstrip("/") + "/wp-json/wp/v2"


def validate_configuration(require_image=True):
    missing = [k for k in ("WP_URL", "WP_USERNAME", "WP_APP_PASSWORD") if not os.getenv(k)]
    if missing:
        raise RuntimeError("Configurazione mancante: " + ", ".join(missing))
    if require_image and not BASE_IMAGE.exists():
        raise RuntimeError("Carica prima l'immagine base dell'oroscopo dal pannello")


def fetch_horoscope():
    response = requests.get("https://sigastra.com/api/v1/daily", params={"lang": "it"}, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if len(payload.get("items", [])) != 12:
        raise RuntimeError("L'API non ha restituito tutti i 12 segni")
    return payload


def stars(value):
    score = max(0, min(5, int(value or 0)))
    return "★" * score + "☆" * (5 - score)


def build_article(payload, day):
    by_sign = {item.get("sign"): item for item in payload["items"]}
    date_long = day.strftime("%d/%m/%Y")
    parts = [
        f"<p><strong>Oroscopo di oggi, {date_long}.</strong> Scopri cosa prevedono le stelle per amore, lavoro ed energia per tutti i dodici segni zodiacali.</p>"
    ]
    for api_name, symbol, italian_name in SIGNS:
        item = by_sign.get(api_name)
        if not item:
            raise RuntimeError(f"Segno mancante nella risposta: {api_name}")
        data = item.get("data", {})
        text = html.escape(item.get("text", "")).replace("\n", "<br>")
        parts.append(
            f'<p><strong>{symbol} {italian_name}</strong><br>'
            f'<strong>Amore:</strong> {stars(data.get("love"))} &nbsp; '
            f'<strong>Lavoro:</strong> {stars(data.get("work"))} &nbsp; '
            f'<strong>Energia:</strong> {stars(data.get("energy"))}<br>{text}</p>'
        )
    attr = payload.get("attribution", {})
    href = html.escape(attr.get("localizedHref", "https://sigastra.com/it/oroscopo-di-oggi"), quote=True)
    label = html.escape(attr.get("text", "Powered by Sigastra"))
    parts.append(f'<p><small><a href="{href}">{label}</a></small></p>')
    return "\n".join(parts)


def font_for(size):
    candidates = [
        os.getenv("DATE_FONT", ""),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    ]
    for path in candidates:
        if path and Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def render_featured_image(day):
    state = load_state()
    image = Image.open(BASE_IMAGE).convert("RGB")
    draw = ImageDraw.Draw(image)
    text = day.strftime("%d/%m/%Y")
    font = font_for(int(state["font_size"]))
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=int(state["stroke_width"]))
    width, height = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = image.width * float(state["image_x"]) / 100 - width / 2
    y = image.height * float(state["image_y"]) / 100 - height / 2
    draw.text(
        (x, y), text, font=font, fill=state["text_color"],
        stroke_fill=state["stroke_color"], stroke_width=int(state["stroke_width"]),
    )
    out = io.BytesIO()
    image.save(out, "JPEG", quality=94, optimize=True)
    out.seek(0)
    return out


def duplicate_exists(title):
    response = requests.get(
        f"{wp_base()}/posts", params={"search": title, "per_page": 20, "status": "publish,draft,future"},
        auth=wp_auth(), headers=wp_headers(), timeout=30,
    )
    response.raise_for_status()
    target = html.unescape(title).strip().lower()
    return any(html.unescape(p.get("title", {}).get("rendered", "")).strip().lower() == target for p in response.json())


def upload_image(day):
    filename = f"oroscopo-{day.strftime('%Y-%m-%d')}.jpg"
    headers = wp_headers() | {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type": "image/jpeg",
    }
    response = requests.post(f"{wp_base()}/media", data=render_featured_image(day).read(), auth=wp_auth(), headers=headers, timeout=60)
    response.raise_for_status()
    media = response.json()
    requests.post(
        f"{wp_base()}/media/{media['id']}", auth=wp_auth(), headers=wp_headers(), timeout=30,
        json={"alt_text": f"Oroscopo di Montagne & Paesi del {day.strftime('%d/%m/%Y')}", "caption": ""},
    ).raise_for_status()
    return media["id"]


def csv_ints(name):
    return [int(x.strip()) for x in os.getenv(name, "").split(",") if x.strip().isdigit()]


def publish(day=None, force=False):
    with lock:
        day = day or datetime.now(TZ)
        title = f"Oroscopo di Montagne & Paesi del {day.strftime('%d/%m/%Y')}"
        state = load_state()
        try:
            validate_configuration()
            if not force and duplicate_exists(title):
                log.info("Articolo già presente: %s", title)
                return {"ok": True, "duplicate": True, "message": "Articolo già presente: nessun duplicato creato"}
            payload = fetch_horoscope()
            content = build_article(payload, day)
            media_id = upload_image(day)
            post = {"title": title, "content": content, "status": os.getenv("WP_POST_STATUS", "publish"), "featured_media": media_id}
            categories = csv_ints("WP_CATEGORY_IDS")
            tags = csv_ints("WP_TAG_IDS")
            if categories: post["categories"] = categories
            if tags: post["tags"] = tags
            if os.getenv("WP_AUTHOR_ID", "").isdigit(): post["author"] = int(os.getenv("WP_AUTHOR_ID"))
            response = requests.post(f"{wp_base()}/posts", json=post, auth=wp_auth(), headers=wp_headers(), timeout=60)
            response.raise_for_status()
            result = response.json()
            state.update({"last_publish": datetime.now(TZ).isoformat(), "last_url": result.get("link"), "last_error": None})
            save_state(state)
            log.info("Pubblicato: %s", result.get("link"))
            return {"ok": True, "url": result.get("link"), "message": "Articolo pubblicato correttamente"}
        except Exception as exc:
            state["last_error"] = str(exc)
            save_state(state)
            log.exception("Pubblicazione fallita")
            raise


def scheduled_job():
    if load_state().get("automation_enabled"):
        try:
            publish()
        except Exception:
            pass
    else:
        log.info("Automazione disattivata: pubblicazione saltata")


@app.get("/")
def dashboard():
    state = load_state()
    now = datetime.now(TZ)
    configured = all(os.getenv(k) for k in ("WP_URL", "WP_USERNAME", "WP_APP_PASSWORD"))
    return render_template("index.html", version=VERSION, state=state, now=now, configured=configured,
                           has_image=BASE_IMAGE.exists(), publish_time=os.getenv("PUBLISH_TIME", "05:30"))


@app.post("/image")
def image_upload():
    uploaded = request.files.get("image")
    if not uploaded or not uploaded.filename:
        flash("Seleziona un'immagine JPG o PNG", "error")
        return redirect(url_for("dashboard"))
    try:
        image = Image.open(uploaded.stream).convert("RGB")
        if image.width < 600 or image.height < 315:
            raise ValueError("L'immagine deve essere almeno 600 × 315 pixel")
        image.save(BASE_IMAGE, "JPEG", quality=95)
        flash("Immagine base salvata", "success")
    except Exception as exc:
        flash(f"Immagine non valida: {exc}", "error")
    return redirect(url_for("dashboard"))


@app.post("/image-settings")
def image_settings():
    state = load_state()
    try:
        state.update({
            "image_x": max(0, min(100, float(request.form["image_x"]))),
            "image_y": max(0, min(100, float(request.form["image_y"]))),
            "font_size": max(16, min(200, int(request.form["font_size"]))),
            "text_color": request.form["text_color"], "stroke_color": request.form["stroke_color"],
            "stroke_width": max(0, min(10, int(request.form["stroke_width"]))),
        })
        save_state(state)
        flash("Impostazioni della data salvate", "success")
    except Exception as exc:
        flash(f"Impostazioni non valide: {exc}", "error")
    return redirect(url_for("dashboard"))


@app.get("/image-preview")
def image_preview():
    if not BASE_IMAGE.exists():
        return "Immagine base non caricata", 404
    return send_file(render_featured_image(datetime.now(TZ)), mimetype="image/jpeg", download_name="anteprima-oroscopo.jpg")


@app.get("/article-preview")
def article_preview():
    try:
        payload = fetch_horoscope()
        return render_template("preview.html", title=f"Oroscopo di Montagne & Paesi del {datetime.now(TZ).strftime('%d/%m/%Y')}", content=build_article(payload, datetime.now(TZ)))
    except Exception as exc:
        flash(f"Anteprima non disponibile: {exc}", "error")
        return redirect(url_for("dashboard"))


@app.post("/publish")
def publish_now():
    try:
        result = publish(force=False)
        flash(result["message"], "success")
    except Exception as exc:
        flash(f"Pubblicazione fallita: {exc}", "error")
    return redirect(url_for("dashboard"))


@app.post("/automation/<action>")
def automation(action):
    state = load_state()
    state["automation_enabled"] = action == "start"
    save_state(state)
    flash("Automazione attivata" if state["automation_enabled"] else "Automazione fermata", "success")
    return redirect(url_for("dashboard"))


@app.get("/health")
def health():
    return jsonify(status="ok", version=VERSION, automation=load_state().get("automation_enabled"))


def start_scheduler():
    hour, minute = [int(x) for x in os.getenv("PUBLISH_TIME", "05:30").split(":", 1)]
    scheduler = BackgroundScheduler(timezone=TZ)
    scheduler.add_job(scheduled_job, "cron", hour=hour, minute=minute, id="daily_horoscope", max_instances=1, coalesce=True)
    scheduler.start()
    return scheduler


scheduler = start_scheduler()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")), debug=False)
