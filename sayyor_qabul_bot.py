#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ochiq muloqat / "Открытый диалог" registration bot
- Uzbek (Latin) + Russian
- CSV storage
- Optional Google Sheets
- Admin DMs for every submission
- /whoami to get your Telegram ID

Env (Railway → Variables):
TELEGRAM_TOKEN=123:ABC
ADMIN_IDS=111111111,222222222
CSV_PATH=registrations.csv

# Optional Sheets (either use *_JSON or *_JSON_CONTENT)
GOOGLE_SHEETS_NAME=Ochiq Muloqat/MB
GOOGLE_SHEETS_JSON=/abs/path/to/service_account.json
# or:
GOOGLE_SHEETS_JSON_CONTENT={...full json...}
"""
import os
import re
import csv
import tempfile
from datetime import datetime
from typing import Dict, Any, List

# ---------- Optional dotenv for local testing ----------
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ---------- If JSON content provided (Railway-friendly), write it to temp file ----------
json_env = os.getenv("GOOGLE_SHEETS_JSON_CONTENT")
if json_env and not os.getenv("GOOGLE_SHEETS_JSON"):
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
    tmp.write(json_env.encode("utf-8"))
    tmp.flush()
    os.environ["GOOGLE_SHEETS_JSON"] = tmp.name

# ---------- Google Sheets helper (safe, will not crash bot) ----------
def try_gs_save_row(sheet_name: str, row: Dict[str, Any]) -> str:
    """Append to Google Sheet if creds exist. Returns '' on success, error text on failure."""
    try:
        gs_path = os.environ.get("GOOGLE_SHEETS_JSON")
        if not gs_path:
            return "GOOGLE_SHEETS_JSON not set"
        import gspread
        from google.oauth2.service_account import Credentials
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_file(gs_path, scopes=scopes)
        gc = gspread.authorize(creds)
        sh = gc.open(os.environ.get("GOOGLE_SHEETS_NAME", sheet_name))
        ws = sh.sheet1
        ws.append_row([
            row["timestamp"], row["lang"], row["user_id"], row["full_name"], row["dob"],
            row["region"], row["district"], row["mode"], row["phone"], row["content"],
        ])
        return ""
    except Exception as e:
        return str(e)

def parse_admin_ids(raw: str | None) -> List[int]:
    if not raw:
        return []
    out: List[int] = []
    for p in raw.split(","):
        p = p.strip()
        if not p:
            continue
        try:
            out.append(int(p))
        except ValueError:
            pass
    return out

ADMIN_IDS: List[int] = parse_admin_ids(os.getenv("ADMIN_IDS"))

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

# ===== States =====
LANG, REGION, MODE, NAME, DOB, DISTRICT, CONTACT, CONTENT, CONFIRM = range(9)

# ===== Regions (Uz/Ru) =====
REGIONS = [
    "Qoraqalpog'iston Respublikasi",
    "Andijon viloyati",
    "Buxoro viloyati",
    "Jizzax viloyati",
    "Qashqadaryo viloyati",
    "Navoiy viloyati",
    "Namangan viloyati",
    "Samarqand viloyati",
    "Sirdaryo viloyati",
    "Surxondaryo viloyati",
    "Toshkent viloyati",
    "Toshkent shahar",
    "Farg'ona viloyati",
    "Xorazm viloyati",
]
REGIONS_RU = [
    "Республика Каракалпакстан",
    "Андижанская область",
    "Бухарская область",
    "Джизакская область",
    "Кашкадарьинская область",
    "Навоийская область",
    "Наманганская область",
    "Самаркандская область",
    "Сырдарьинская область",
    "Сурхандарьинская область",
    "Ташкентская область",
    "Город Ташкент",
    "Ферганская область",
    "Хорезмская область",
]

# ===== Texts =====
WELCOME_PREVIEW_UZ = (
    "Assalomu alaykum!\n\n"
    "Markaziy bank xodimlari bilan o'tkaziladigan «Ochiq muloqot» platformasiga xush kelibsiz!\n"
    "Sizning fikr va takliflaringiz — moliyaviy xizmatlarni yanada qulay va samarali qilishda muhim.\n"
    "Iltimos, quyidagi qadamlarni bosqichma-bosqich bajaring."
)
WELCOME_PREVIEW_RU = (
    "Ассалому алайкум!\n"
    "Добро пожаловать на платформу «Открытый диалог» с Председателем Центробанка Тимуром Аминжоновичем Ишметовым!\n"
    "Ваши мнения и предложения важны для того, чтобы сделать финансовые услуги ещё удобнее и эффективнее.\n"
    "Пожалуйста, выполните шаги ниже по порядку."
)
CHOOSE_LANG = "Iltimos, tilni tanlang / Пожалуйста, выберите язык:"
LANG_BTNS = [
    [InlineKeyboardButton("O'zbekcha 🇺🇿", callback_data="lang_uz")],
    [InlineKeyboardButton("Русский 🇷🇺", callback_data="lang_ru")],
]
PROMPTS = {
    "uz": {
        "region": "Iltimos, yashash hududingizni tanlang:",
        "mode": "Qabul shaklini tanlang:",
        "mode_off": "Ha, shaxsan qatnashaman (offline)",
        "mode_on": "Yo'q, onlayn qatnashaman (online)",
        "name": "To'liq ism-sharifingizni kiriting:",
        "dob": "Tug'ilgan sanangiz (dd.mm.yyyy, masalan 07.09.1999):",
        "district": "Yashash tumani/shahri:",
        "contact": "Telefon raqamingizni yuboring (tugma orqali):",
        "content": "Murojaat mazmuni (qisqacha va aniq):",
        "confirm": "Ma'lumotlaringizni tasdiqlaysizmi?",
        "yes": "Ha, tasdiqlayman",
        "no": "Yo'q, tahrirlayman",
        "thanks": "Hurmatli fuqaro, murojaatingiz qabul qilindi. Tez orada bog'lanamiz.",
    },
    "ru": {
        "region": "Пожалуйста, выберите ваш регион проживания:",
        "mode": "Выберите форму участия:",
        "mode_off": "Да, лично (офлайн)",
        "mode_on": "Нет, онлайн (дистанционно)",
        "name": "Введите ваше полное имя:",
        "dob": "Дата рождения (дд.мм.гггг, например 07.09.1999):",
        "district": "Район/город проживания:",
        "contact": "Отправьте ваш номер телефона (через кнопку):",
        "content": "Содержание обращения (кратко и конкретно):",
        "confirm": "Подтвердить ваши данные?",
        "yes": "Да, подтверждаю",
        "no": "Изменить",
        "thanks": "Спасибо! Обращение принято. Мы свяжемся с вами в ближайшее время.",
    },
}
CSV_PATH = os.environ.get("CSV_PATH", "registrations.csv")

# ----- Keyboards -----
def build_regions_keyboard(lang: str) -> InlineKeyboardMarkup:
    names = REGIONS if lang == "uz" else REGIONS_RU
    rows = [[InlineKeyboardButton(name, callback_data=f"reg|{name}")] for name in names]
    return InlineKeyboardMarkup(rows)

def build_mode_keyboard(lang: str) -> InlineKeyboardMarkup:
    t = PROMPTS[lang]
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t["mode_off"], callback_data="mode|offline")],
        [InlineKeyboardButton(t["mode_on"], callback_data="mode|online")],
    ])

def build_confirm_keyboard(lang: str) -> InlineKeyboardMarkup:
    t = PROMPTS[lang]
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t["yes"], callback_data="confirm|yes")],
        [InlineKeyboardButton(t["no"], callback_data="confirm|no")],
    ])

# ----- Utils -----
def parse_dob(text: str) -> str:
    m = re.fullmatch(r"\s*(\d{1,2})[./-](\d{1,2})[./-](\d{4})\s*", text or "")
    if not m:
        return ""
    d, mth, y = map(int, m.groups())
    try:
        dt = datetime(y, mth, d)
        return dt.strftime("%d.%m.%Y")
    except ValueError:
        return ""

def save_row(row: Dict[str, Any]):
    file_exists = os.path.isfile(CSV_PATH)
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "timestamp","lang","user_id","full_name","dob",
                "region","district","mode","phone","content",
            ],
        )
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

def format_summary(lang: str, ud: Dict[str, Any]) -> str:
    return (
        f"\n— Til/Язык: {'O‘zbekcha' if lang=='uz' else 'Русский'}"
        f"\n— Hudud/Регион: {ud.get('region')}"
        f"\n— Shakl/Формат: {('Offline' if ud.get('mode')=='offline' else 'Online')}"
        f"\n— F.I.Sh/Ф.И.О.: {ud.get('full_name')}"
        f"\n— Tug'ilgan sana/Дата рождения: {ud.get('dob')}"
        f"\n— Tuman/Rayon: {ud.get('district')}"
        f"\n— Telefon/Телефон: {ud.get('phone')}"
        f"\n— Murojaat/Обращение: {ud.get('content')}\n"
    )

async def notify_admins(context: ContextTypes.DEFAULT_TYPE, text: str):
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=text)
        except Exception:
            pass  # ignore individual DM errors

# ===== Handlers =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = f"{WELCOME_PREVIEW_UZ}\n\n{WELCOME_PREVIEW_RU}\n\n{CHOOSE_LANG}"
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(LANG_BTNS))
    return LANG

async def choose_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang = "uz" if q.data == "lang_uz" else "ru"
    context.user_data["lang"] = lang
    await q.edit_message_text(PROMPTS[lang]["region"], reply_markup=build_regions_keyboard(lang))
    return REGION

async def choose_region(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, name = q.data.split("|", 1)
    context.user_data["region"] = name
    lang = context.user_data["lang"]
    await q.edit_message_text(PROMPTS[lang]["mode"], reply_markup=build_mode_keyboard(lang))
    return MODE

async def choose_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, mode = q.data.split("|", 1)
    context.user_data["mode"] = mode
    lang = context.user_data["lang"]
    await q.edit_message_text(PROMPTS[lang]["name"])
    return NAME

async def full_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["full_name"] = (update.message.text or "").strip()
    lang = context.user_data["lang"]
    await update.message.reply_text(PROMPTS[lang]["dob"])
    return DOB

async def dob(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "uz")
    parsed = parse_dob(update.message.text)
    if not parsed:
        await update.message.reply_text(
            "Noto'g'ri sana formati. dd.mm.yyyy yuboring." if lang == "uz" else
            "Неверный формат даты. Используйте дд.мм.гггг."
        )
        return DOB
    context.user_data["dob"] = parsed
    await update.message.reply_text(PROMPTS[lang]["district"])
    return DISTRICT

async def district(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["district"] = (update.message.text or "").strip()
    lang = context.user_data.get("lang", "uz")
    btn = KeyboardButton(
        text=("Telefon raqamimni yuborish" if lang == "uz" else "Отправить мой номер"),
        request_contact=True,
    )
    kb = ReplyKeyboardMarkup([[btn]], resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(PROMPTS[lang]["contact"], reply_markup=kb)
    return CONTACT

async def contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "uz")
    phone = None
    if update.message.contact and update.message.contact.phone_number:
        phone = update.message.contact.phone_number
    else:
        txt = (update.message.text or "").strip()
        if re.fullmatch(r"[+]?[\d][\d\s-]{6,}", txt):
            phone = txt
    if not phone:
        await update.message.reply_text(
            "Iltimos, tugma orqali yuboring yoki +998… formatida yozing." if lang == "uz" else
            "Пожалуйста, отправьте через кнопку или в формате +998…"
        )
        return CONTACT
    context.user_data["phone"] = phone
    await update.message.reply_text(PROMPTS[lang]["content"], reply_markup=ReplyKeyboardRemove())
    return CONTENT

async def content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["content"] = (update.message.text or "").strip()
    lang = context.user_data.get("lang", "uz")
    summary = format_summary(lang, context.user_data)
    await update.message.reply_text(PROMPTS[lang]["confirm"] + "\n" + summary,
                                    reply_markup=build_confirm_keyboard(lang))
    return CONFIRM

async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang = context.user_data.get("lang", "uz")
    _, val = q.data.split("|", 1)
    if val == "no":
        await q.edit_message_text(PROMPTS[lang]["region"], reply_markup=build_regions_keyboard(lang))
        return REGION

    ud = context.user_data
    row = {
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "lang": lang,
        "user_id": q.from_user.id,
        "full_name": ud.get("full_name"),
        "dob": ud.get("dob"),
        "region": ud.get("region"),
        "district": ud.get("district"),
        "mode": ud.get("mode"),
        "phone": ud.get("phone"),
        "content": ud.get("content"),
    }

    # Save to CSV
    save_row(row)

    # Try Google Sheets (will not crash on error)
    gs_err = try_gs_save_row(os.environ.get("GOOGLE_SHEETS_NAME", "SayyorQabul"), row)

    # Notify admins regardless of Sheets result
    note = "✅ Yangi ro‘yxatdan o‘tish:" if lang == "uz" else "✅ Новая регистрация:"
    extra = f"\n⚠️ Sheets: {gs_err}" if gs_err else ""
    await notify_admins(context, note + format_summary(lang, ud) + extra)

    await q.edit_message_text(PROMPTS[lang]["thanks"])
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "uz")
    await update.message.reply_text("Bekor qilindi." if lang == "uz" else "Отменено.",
                                    reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def whoami(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Sizning user ID: {update.effective_user.id}")

# ===== Main =====
async def post_init(app: Application):
    await app.bot.set_my_commands([
        ("start", "Boshlash / Старт"),
        ("cancel", "Bekor qilish / Отмена"),
        ("whoami", "User ID ni ko‘rish"),
    ])

def main():
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        raise RuntimeError("Set TELEGRAM_TOKEN env var")

    app: Application = ApplicationBuilder().token(token).post_init(post_init).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            LANG: [CallbackQueryHandler(choose_lang, pattern=r"^lang_")],
            REGION: [CallbackQueryHandler(choose_region, pattern=r"^reg\|")],
            MODE: [CallbackQueryHandler(choose_mode, pattern=r"^mode\|")],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, full_name)],
            DOB: [MessageHandler(filters.TEXT & ~filters.COMMAND, dob)],
            DISTRICT: [MessageHandler(filters.TEXT & ~filters.COMMAND, district)],
            CONTACT: [
                MessageHandler(filters.CONTACT, contact),
                MessageHandler(filters.TEXT & ~filters.COMMAND, contact),
            ],
            CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, content)],
            CONFIRM: [CallbackQueryHandler(confirm, pattern=r"^confirm\|")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("whoami", whoami))
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
