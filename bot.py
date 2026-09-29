# -*- coding: utf-8 -*-
import logging
import os
from functools import wraps

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, TelegramError
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, MessageHandler, filters)

from knowledge_base import (COMMON_STEPS, EXCHANGES, GLOSSARY, MODULES, QUIZ,
                            SECURITY_TIPS, VIDEOS)

logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("BOT_TOKEN", "ВСТАВЬ_ТОКЕН_ОТ_BOTFATHER")
HTML = ParseMode.HTML

CHANNEL_USERNAME = "@ffg3rww"
CHANNEL_URL = "https://t.me/ffg3rww"
SUB_OK = ("member", "administrator", "creator")


# ---------- Гейт: подписка на канал ----------
def gate_text(detail: str = "") -> str:
    text = ("🔒 <b>Для доступа нужна подписка</b>\n\n"
            f"Чтобы пользоваться ботом, подпишись на канал <b>{CHANNEL_USERNAME}</b>:\n"
            f"{CHANNEL_URL}\n\n"
            "После подписки нажми кнопку <b>🔴 Проверить подписку</b> — бот продолжит работу.")
    return f"{text}\n\n{detail}" if detail else text


def gate_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Перейти в канал", url=CHANNEL_URL)],
        [InlineKeyboardButton("🔴 Проверить подписку", callback_data="gate:check")],
    ])


async def is_subscribed(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    if user is None:
        return True
    try:
        member = await ctx.bot.get_chat_member(CHANNEL_USERNAME, user.id)
        return member.status in SUB_OK
    except TelegramError as e:
        logging.warning("Проверка подписки недоступна (добавь @ffg3rw_bot админом канала "
                        "%s), пускаю пользователя: %s", CHANNEL_USERNAME, e)
        return True


def subscription_required(func):
    @wraps(func)
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if await is_subscribed(update, ctx):
            return await func(update, ctx)
        if update.callback_query:
            q = update.callback_query
            await q.answer()
            try:
                await q.edit_message_text(gate_text(), parse_mode=HTML, reply_markup=gate_kb())
            except BadRequest:
                pass
        elif update.message:
            await update.message.reply_text(gate_text(), parse_mode=HTML, reply_markup=gate_kb())
    return wrapper


async def gate_check(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if await is_subscribed(update, ctx):
        ctx.user_data.pop("gate_tries", None)
        await q.edit_message_text("✅ Подписка подтверждена!", parse_mode=HTML)
        await q.message.reply_text("📚 Главное меню:", reply_markup=main_menu())
        return
    tries = ctx.user_data.get("gate_tries", 0) + 1
    ctx.user_data["gate_tries"] = tries
    detail = f"❌ Подписки пока не вижу. Проверка №{tries} — подпишись и нажми кнопку ещё раз."
    try:
        await q.edit_message_text(gate_text(detail), parse_mode=HTML, reply_markup=gate_kb())
    except BadRequest:
        await q.message.reply_text(gate_text(detail), parse_mode=HTML, reply_markup=gate_kb())


def main_menu() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(m["title"], callback_data=f"mod:{k}")]
            for k, m in MODULES.items()]
    rows.append([InlineKeyboardButton("🏦 Регистрация на биржах", callback_data="ex:list")])
    rows.append([InlineKeyboardButton("🧠 Квиз", callback_data="quiz:start")])
    rows.append([InlineKeyboardButton("📖 Словарь", callback_data="gloss")])
    return InlineKeyboardMarkup(rows)


@subscription_required
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text(
        "👋 <b>Привет! Я бот-учитель по арбитражу криптовалют.</b>\n\n"
        "Внутри: свечи и графики, виды арбитража, риск-менеджмент, квиз и калькулятор.\n"
        "Команды: /menu, /calc, /quiz, /glossary\n\n"
        "⚠️ Материалы образовательные, не финансовый совет.",
        parse_mode=HTML, reply_markup=main_menu())


@subscription_required
async def menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📚 Главное меню:", reply_markup=main_menu())


# ---------- Модули и уроки ----------
def lessons_kb(mod_id: str) -> InlineKeyboardMarkup:
    lessons = MODULES[mod_id]["lessons"]
    rows = [[InlineKeyboardButton(f"{i+1}. {l['title']}", callback_data=f"les:{mod_id}:{i}")]
            for i, l in enumerate(lessons)]
    rows.append([InlineKeyboardButton("⬅️ В меню", callback_data="home")])
    return InlineKeyboardMarkup(rows)


def lesson_kb(mod_id: str, i: int) -> InlineKeyboardMarkup:
    n = len(MODULES[mod_id]["lessons"])
    nav = []
    if i > 0:
        nav.append(InlineKeyboardButton("◀️ Назад", callback_data=f"les:{mod_id}:{i-1}"))
    if i < n - 1:
        nav.append(InlineKeyboardButton("Далее ▶️", callback_data=f"les:{mod_id}:{i+1}"))
    rows = [nav] if nav else []
    for title, url in VIDEOS.get(f"{mod_id}:{i}", []):
        rows.append([InlineKeyboardButton(f"🎥 {title}"[:60], url=url)])
    rows.append([InlineKeyboardButton("📋 К урокам", callback_data=f"mod:{mod_id}")])
    return InlineKeyboardMarkup(rows)


# ---------- Квиз ----------
def quiz_question(ctx, idx: int):
    q = QUIZ[idx]
    kb = [[InlineKeyboardButton(o, callback_data=f"ans:{idx}:{j}")] for j, o in enumerate(q["options"])]
    return f"<b>Вопрос {idx+1}/{len(QUIZ)}</b>\n\n{q['q']}", InlineKeyboardMarkup(kb)


@subscription_required
async def quiz_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["score"] = 0
    text, kb = quiz_question(ctx, 0)
    await update.message.reply_text(text, parse_mode=HTML, reply_markup=kb)


# ---------- Калькулятор ----------
@subscription_required
async def calc(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    if len(args) < 3:
        await update.message.reply_text(
            "🧮 <b>Калькулятор арбитража</b>\n\n"
            "Формат: <code>/calc цена_покупки цена_продажи объём [комиссия_% на сторону] [сеть_$]</code>\n"
            "Пример: <code>/calc 60000 60300 0.5 0.1 5</code>",
            parse_mode=HTML)
        return
    try:
        buy, sell, vol = float(args[0]), float(args[1]), float(args[2])
        fee = float(args[3]) if len(args) > 3 else 0.1
        net = float(args[4]) if len(args) > 4 else 0.0
    except ValueError:
        await update.message.reply_text("Введи числа, например: /calc 60000 60300 0.5 0.1 5")
        return
    gross = (sell - buy) * vol
    fees = (buy * vol + sell * vol) * fee / 100
    profit = gross - fees - net
    invest = buy * vol
    roi = profit / invest * 100 if invest else 0
    spread = (sell - buy) / buy * 100 if buy else 0
    emoji = "✅" if profit > 0 else "❌"
    await update.message.reply_text(
        f"🧮 <b>Результат</b>\n\n"
        f"Спред: <b>{spread:.3f}%</b>\n"
        f"Валовая прибыль: {gross:.2f} $\n"
        f"Комиссии: −{fees:.2f} $\n"
        f"Сеть: −{net:.2f} $\n"
        f"{emoji} <b>Чистая прибыль: {profit:.2f} $ ({roi:.3f}%)</b>",
        parse_mode=HTML)


@subscription_required
async def glossary(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = "📖 <b>Словарь</b>\n\n" + "\n".join(f"• <b>{k}</b> — {v}" for k, v in GLOSSARY.items())
    await update.message.reply_text(text, parse_mode=HTML)


# ---------- Обработка кнопок ----------
@subscription_required
async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data

    if data == "home":
        await q.edit_message_text("📚 Главное меню:", reply_markup=main_menu())

    elif data.startswith("mod:"):
        mod_id = data.split(":")[1]
        await q.edit_message_text(f"<b>{MODULES[mod_id]['title']}</b>\nВыбери урок:",
                                  parse_mode=HTML, reply_markup=lessons_kb(mod_id))

    elif data.startswith("les:"):
        _, mod_id, i = data.split(":")
        i = int(i)
        les = MODULES[mod_id]["lessons"][i]
        await q.edit_message_text(f"<b>📌 {les['title']}</b>\n\n{les['text']}",
                                  parse_mode=HTML, reply_markup=lesson_kb(mod_id, i))

    elif data == "ex:list":
        rows = [[InlineKeyboardButton(e["title"], callback_data=f"ex:{k}")] for k, e in EXCHANGES.items()]
        rows.append([InlineKeyboardButton("🔐 Безопасность", callback_data="ex:sec")])
        rows.append([InlineKeyboardButton("⬅️ В меню", callback_data="home")])
        await q.edit_message_text(
            "🏦 <b>Регистрация на биржах</b>\nВыбери биржу — пришлю пошаговый план:",
            parse_mode=HTML, reply_markup=InlineKeyboardMarkup(rows))

    elif data == "ex:sec":
        await q.edit_message_text(SECURITY_TIPS, parse_mode=HTML, reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ К биржам", callback_data="ex:list")]]))

    elif data.startswith("ex:"):
        e = EXCHANGES[data.split(":")[1]]
        steps = "\n\n".join(f"<b>Шаг {i+1}.</b> {t}" for i, t in enumerate(COMMON_STEPS))
        text = (f"🏦 <b>Регистрация на {e['title']}</b>\n\n{e['kz']}\n\n"
                f"ℹ️ {e['notes']}\n\n{steps}\n\n⚠️ Интерфейс бирж меняется — сверяйся с подсказками на сайте.")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🌐 Официальный сайт {e['title']}", url=e["url"])],
            [InlineKeyboardButton("⬅️ К биржам", callback_data="ex:list")]])
        await q.edit_message_text(text, parse_mode=HTML, reply_markup=kb, disable_web_page_preview=True)

    elif data == "gloss":
        text = "📖 <b>Словарь</b>\n\n" + "\n".join(f"• <b>{k}</b> — {v}" for k, v in GLOSSARY.items())
        await q.edit_message_text(text, parse_mode=HTML,
                                  reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ В меню", callback_data="home")]]))

    elif data == "quiz:start":
        ctx.user_data["score"] = 0
        text, kb = quiz_question(ctx, 0)
        await q.edit_message_text(text, parse_mode=HTML, reply_markup=kb)

    elif data.startswith("ans:"):
        _, idx, choice = data.split(":")
        idx, choice = int(idx), int(choice)
        item = QUIZ[idx]
        ok = choice == item["answer"]
        if ok:
            ctx.user_data["score"] = ctx.user_data.get("score", 0) + 1
        verdict = "✅ Верно!" if ok else f"❌ Неверно. Правильно: <b>{item['options'][item['answer']]}</b>"
        nxt = idx + 1
        if nxt < len(QUIZ):
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("Дальше ▶️", callback_data=f"nq:{nxt}")]])
            await q.edit_message_text(f"{verdict}\n\n💡 {item['explain']}", parse_mode=HTML, reply_markup=kb)
        else:
            score = ctx.user_data.get("score", 0)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔁 Ещё раз", callback_data="quiz:start")],
                                       [InlineKeyboardButton("⬅️ В меню", callback_data="home")]])
            await q.edit_message_text(
                f"{verdict}\n\n💡 {item['explain']}\n\n🏁 <b>Итог: {score}/{len(QUIZ)}</b>",
                parse_mode=HTML, reply_markup=kb)

    elif data.startswith("nq:"):
        nxt = int(data.split(":")[1])
        text, kb = quiz_question(ctx, nxt)
        await q.edit_message_text(text, parse_mode=HTML, reply_markup=kb)


# ---------- Поиск по ключевому слову ----------
@subscription_required
async def search(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    word = update.message.text.lower().strip()
    if word in GLOSSARY:
        await update.message.reply_text(f"<b>{word}</b> — {GLOSSARY[word]}", parse_mode=HTML)
        return
    hits = [(k, i, l["title"]) for k, m in MODULES.items()
            for i, l in enumerate(m["lessons"]) if word in (l["title"] + l["text"]).lower()]
    if not hits:
        await update.message.reply_text("Ничего не нашёл. Открой /menu 📚")
        return
    kb = [[InlineKeyboardButton(t, callback_data=f"les:{k}:{i}")] for k, i, t in hits[:8]]
    await update.message.reply_text("🔎 Нашёл в уроках:", reply_markup=InlineKeyboardMarkup(kb))


# ---------- Keep-alive: Render free спит без входящих запросов15 мин ----------
def _keepalive():
    if not os.getenv("RENDER_EXTERNAL_URL"):
        return
    import threading
    import time
    import urllib.request
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    port = int(os.getenv("PORT", "10000"))
    threading.Thread(
        target=lambda: ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever(),
        daemon=True).start()

    base = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")

    def ping():
        while True:
            try:
                urllib.request.urlopen(base + "/", timeout=15)
            except Exception:
                pass
            time.sleep(600)

    threading.Thread(target=ping, daemon=True).start()
    logging.info("Keep-alive включён: HTTP на порту %s, пинг каждые 10 мин", port)


def main():
    _keepalive()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("quiz", quiz_cmd))
    app.add_handler(CommandHandler("calc", calc))
    app.add_handler(CommandHandler("glossary", glossary))
    app.add_handler(CallbackQueryHandler(gate_check, pattern="^gate:"))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search))
    app.run_polling()


if __name__ == "__main__":
    main()
