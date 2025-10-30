#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sayyor Qabul / "Открытый диалог" registration bot
Language: Uzbek (Latin) + Russian
Library: python-telegram-bot >= 20.7
Storage: CSV by default; optional Google Sheets (gspread) snippet included

Flow
- /start → language (UZ/RU)
- region (14 incl. Tashkent City)
- attendance (offline/online)
- full name
- date of birth
- district (tuman)
- phone (Telegram one‑tap, with fallback validation)
- appeal text (Murojaat mazmuni)
- confirmation → save → thank you

Environment variables:
TELEGRAM_TOKEN="123456:ABC..."                # required
# Optional Google Sheets:
# GOOGLE_SHEETS_JSON="/path/to/service_account.json"
# GOOGLE_SHEETS_NAME="SayyorQabul"

Run:
    python -m venv .venv
    # Windows: .venv\Scripts\activate
    # macOS/Linux:
    #   source .venv/bin/activate
    pip install python-telegram-bot==20.7
    export TELEGRAM_TOKEN="123:ABC"  # (Windows PowerShell: $env:TELEGRAM_TOKEN="123:ABC")
    python sayyor_qabul_bot.py

Note: Telegram does NOT allow sending a message before the user taps Start.
Place the pre-start welcome text in the bot's Description and Short Description.
"""
import os
import re
import csv
from datetime import datetime
from typing import Dict, Any

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
    "Markaziy bank raisi Timur Aminjonovich Ishmetov bilan o'tkaziladigan «Ochiq muloqot» platformasiga xush kelibsiz!\n"
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

# ===== Keyboards =====
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

# ===== Utils =====
def parse_dob(text: str) -> str:
    """Accepts dd.mm.yyyy (or with / or -) and returns formatted 'dd.mm.yyyy' or '' if invalid."""
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
                "timestamp",
                "lang",
                "user_id",
                "full_name",
                "dob",
                "region",
                "district",
                "mode",
                "phone",
                "content",
            ],
        )
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

# Optional Google Sheets (uncomment to enable)
"""
import gspread
from google.oauth2.service_account import Credentials

def gs_save_row(sheet_name: str, row: Dict[str, Any]):
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(
        os.environ["GOOGLE_SHEETS_JSON"], scopes=scopes
    )
    gc = gspread.authorize(creds)
    sh = gc.open(os.environ.get("GOOGLE_SHEETS_NAME", sheet_name))
    ws = sh.sheet1
    ws.append_row([
        row["timestamp"], row["lang"], row["user_id"], row["full_name"], row["dob"],
        row["region"], row["district"], row["mode"], row["phone"], row["content"],
    ])
"""

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
    ud = context.user_data
    summary = (
        f"\n— Til/Язык: {'O‘zbekcha' if lang=='uz' else 'Русский'}"
        f"\n— Hudud/Регион: {ud.get('region')}"
        f"\n— Shakl/Формат: {('Offline' if ud.get('mode')=='offline' else 'Online')}"
        f"\n— F.I.Sh/Ф.И.О.: {ud.get('full_name')}"
        f"\n— Tug'ilgan sana/Дата рождения: {ud.get('dob')}"
        f"\n— Tuman/Rayon: {ud.get('district')}"
        f"\n— Telefon/Телефон: {ud.get('phone')}"
        f"\n— Murojaat/Обращение: {ud.get('content')}\n"
    )
    await update.message.reply_text(PROMPTS[lang]["confirm"] + "\n" + summary, reply_markup=build_confirm_keyboard(lang))
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
    save_row(row)
    # Optional: also save to Google Sheets
    # gs_save_row(os.environ.get("GOOGLE_SHEETS_NAME", "SayyorQabul"), row)

    await q.edit_message_text(PROMPTS[lang]["thanks"])
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "uz")
    await update.message.reply_text("Bekor qilindi." if lang == "uz" else "Отменено.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# ===== Main =====
async def post_init(app: Application):
    await app.bot.set_my_commands([
        ("start", "Boshlash / Старт"),
        ("cancel", "Bekor qilish / Отмена"),
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
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
