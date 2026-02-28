#!/usr/bin/env python3
"""
🎬 Oscar 2026 Prediction Bot — 98th Academy Awards (15 марта 2026)

- Голосование закрывается 14 марта 2026 в 19:00 МСК (за 24ч до церемонии)
- Переголосовать можно до дедлайна, после — нельзя
- Два вопроса на категорию: кто победит (🔮) и кого хочешь (❤️)
- Admin: /admin — ввод результатов кнопками во время церемонии
         /set_deadline — изменить дедлайн если нужно
"""

import json, os, logging
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler
)

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── НОМИНАЦИИ ────────────────────────────────
CATEGORIES = [
    {"id": "best_picture", "title": "🎬 Лучший фильм",
     "options": ["Bugonia","F1","Frankenstein","Hamnet","Marty Supreme",
                 "One Battle After Another","The Secret Agent","Sentimental Value","Sinners","Train Dreams"]},
    {"id": "best_director", "title": "🎥 Лучшая режиссура",
     "options": ["Ryan Coogler — Sinners","Paul Thomas Anderson — One Battle After Another",
                 "Josh Safdie — Marty Supreme","Joachim Trier — Sentimental Value","Chloé Zhao — Hamnet"]},
    {"id": "best_actor", "title": "👨 Лучший актёр",
     "options": ["Timothée Chalamet — Marty Supreme","Leonardo DiCaprio — One Battle After Another",
                 "Ethan Hawke — Blue Moon","Michael B. Jordan — Sinners","Wagner Moura — The Secret Agent"]},
    {"id": "best_actress", "title": "👩 Лучшая актриса",
     "options": ["Jessie Buckley — Hamnet","Rose Byrne — If I Had Legs, I'd Kick You",
                 "Kate Hudson — Song Sung Blue","Renate Reinsve — Sentimental Value","Emma Stone — Bugonia"]},
    {"id": "best_supporting_actor", "title": "👨‍🎭 Лучший актёр второго плана",
     "options": ["Benicio del Toro — One Battle After Another","Miles Caton — Sinners",
                 "Jacob Elordi — Frankenstein","Delroy Lindo — Sinners","Sean Penn — One Battle After Another"]},
    {"id": "best_supporting_actress", "title": "👩‍🎭 Лучшая актриса второго плана",
     "options": ["Elle Fanning — Sentimental Value","Inga Ibsdotter Lilleaas — Sentimental Value",
                 "Amy Madigan — Weapons","Wunmi Mosaku — Sinners","Teyana Taylor — One Battle After Another"]},
    {"id": "best_animated", "title": "🎨 Лучший анимационный фильм",
     "options": ["Arco","Elio","KPop Demon Hunters","Little Amélie or the Character of Rain","Zootopia 2"]},
    {"id": "best_adapted_screenplay", "title": "📖 Лучший адаптированный сценарий",
     "options": ["One Battle After Another — Paul Thomas Anderson","Hamnet — Chloé Zhao",
                 "Frankenstein — Guillermo del Toro et al.","Train Dreams — Clint Bentley",
                 "The Secret Agent — Paul Thomas Anderson"]},
]

TOTAL        = len(CATEGORIES)
DATA_FILE    = os.environ.get("DATA_FILE",    "votes.json")
RESULTS_FILE = os.environ.get("RESULTS_FILE", "results.json")
CONFIG_FILE  = os.environ.get("CONFIG_FILE",  "config.json")
ADMIN_IDS    = {int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()}


# Дедлайн по умолчанию: 14 марта 2026, 19:00 МСК = 16:00 UTC
from datetime import timedelta
DEFAULT_DEADLINE = datetime(2026, 3, 14, 16, 0, tzinfo=timezone.utc)
# Состояния
PREDICT, WISH           = 0, 1
ADMIN_CAT, ADMIN_WIN    = 10, 11


# ─── ХРАНИЛИЩЕ ───────────────────────────────

def load(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ─── ДЕДЛАЙН ─────────────────────────────────

def get_deadline() -> datetime:
    """Возвращает дедлайн как datetime (UTC).
    Если admin не задал вручную — возвращает DEFAULT_DEADLINE."""
    cfg = load(CONFIG_FILE)
    ts = cfg.get("deadline_utc")
    if ts:
        return datetime.fromisoformat(ts)
    return DEFAULT_DEADLINE

def voting_open() -> tuple[bool, str]:
    """(открыто?, сообщение)"""
    dl = get_deadline()
    now = datetime.now(timezone.utc)
    if now >= dl:
        # Форматируем в МСК (UTC+3) для читабельности
        dl_msk = dl.strftime("%d.%m.%Y %H:%M МСК") if dl else ""
        return False, f"⏰ Голосование закрыто — дедлайн был {dl_msk}."
    # Считаем сколько осталось
    left = dl - now
    hours  = int(left.total_seconds() // 3600)
    minutes = int((left.total_seconds() % 3600) // 60)
    if hours >= 24:
        days = hours // 24
        remaining = f"{days} д. {hours % 24} ч."
    elif hours > 0:
        remaining = f"{hours} ч. {minutes} мин."
    else:
        remaining = f"{minutes} мин."
    return True, remaining


# ─── КЛАВИАТУРЫ ──────────────────────────────

def make_keyboard(cat_index, mode):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(opt, callback_data=f"{mode}_{cat_index}_{i}")]
        for i, opt in enumerate(CATEGORIES[cat_index]["options"])
    ])

async def send_or_edit(update, text, markup):
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")
    elif update.message:
        await update.message.reply_text(text, reply_markup=markup, parse_mode="Markdown")


# ─── ГОЛОСОВАНИЕ ─────────────────────────────

async def ask_predict(update, ctx):
    idx = ctx.user_data.get("idx", 0)
    if idx >= TOTAL:
        return await finish(update, ctx)
    cat = CATEGORIES[idx]
    text = f"[{idx*2+1}/{TOTAL*2}] *{cat['title']}*\n\n🔮 *Кто, по-твоему, ПОБЕДИТ?*"
    await send_or_edit(update, text, make_keyboard(idx, "predict"))
    return PREDICT

async def ask_wish(update, ctx, predicted):
    idx = ctx.user_data.get("idx", 0)
    cat = CATEGORIES[idx]
    text = (f"[{idx*2+2}/{TOTAL*2}] *{cat['title']}*\n\n"
            f"Ты предсказал: `{predicted}`\n\n"
            f"❤️ А кого *хочешь* видеть победителем?")
    await send_or_edit(update, text, make_keyboard(idx, "wish"))
    return WISH

async def start(update, ctx):
    user = update.effective_user
    uid  = str(user.id)

    open_, info = voting_open()

    # Уже голосовал
    entry = load(DATA_FILE).get(uid, {})
    if entry.get("completed"):
        if open_:
            # Предлагаем переголосовать
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Переголосовать", callback_data="revote"),
                InlineKeyboardButton("👀 Мои ответы",    callback_data="showvotes"),
            ]])
            await update.message.reply_text(
                f"Привет, {user.first_name}! Ты уже проголосовал 🎬\n\n"
                f"⏳ До закрытия голосования: *{info}*\n\n"
                "Можешь изменить предсказания или посмотреть свои ответы:",
                reply_markup=keyboard,
                parse_mode="Markdown")
        else:
            await update.message.reply_text(
                f"Привет, {user.first_name}! {info}\n\n"
                "/my_votes — посмотреть свои предсказания\n"
                "/leaderboard — таблица лидеров")
        return ConversationHandler.END

    # Голосование закрыто, ещё не голосовал
    if not open_:
        await update.message.reply_text(f"😔 {info}\nПринять участие уже не получится.")
        return ConversationHandler.END

    # Начинаем голосование
    deadline_line = f"⏳ Успей проголосовать — осталось *{info}*\n\n" if info else ""
    await update.message.reply_text(
        "🏆 *Oscar 2026 — Угадай победителей!*\n\n"
        "98-я церемония — *15 марта 2026*\n\n"
        f"{deadline_line}"
        f"Для каждой из *{TOTAL} категорий* два вопроса:\n"
        "🔮 Кто *победит*? → таблица лидеров\n"
        "❤️ Кого *хочешь* видеть? → для фана\n\n"
        f"Итого {TOTAL*2} вопросов. Поехали! 👇",
        parse_mode="Markdown")
    ctx.user_data.update({"idx": 0, "predictions": {}, "wishes": {}})
    return await ask_predict(update, ctx)

async def handle_revote(update, ctx):
    """Нажата кнопка 'Переголосовать'."""
    query = update.callback_query
    await query.answer()
    open_, _ = voting_open()
    if not open_:
        await query.edit_message_text("⏰ Голосование уже закрыто — изменить ответы нельзя.")
        return ConversationHandler.END
    ctx.user_data.update({"idx": 0, "predictions": {}, "wishes": {}})
    await query.edit_message_text("🔄 Начинаем заново! Отвечай на вопросы 👇")
    return await ask_predict(update, ctx)

async def handle_showvotes(update, ctx):
    """Нажата кнопка 'Мои ответы' из стартового меню."""
    query = update.callback_query
    await query.answer()
    uid   = str(query.from_user.id)
    entry = load(DATA_FILE).get(uid, {})
    preds  = entry.get("predictions", {})
    wishes = entry.get("wishes", {})
    lines = []
    for cat in CATEGORIES:
        p = preds.get(cat["id"],  "—")
        w = wishes.get(cat["id"], "—")
        lines.append(f"*{cat['title']}*\n  🔮 `{p}`\n  ❤️ `{w}`" + (" ✓" if p==w else ""))
    await query.edit_message_text("🗳 *Твои предсказания:*\n\n" + "\n\n".join(lines), parse_mode="Markdown")
    return ConversationHandler.END

async def handle_predict(update, ctx):
    await update.callback_query.answer()
    _, idx_str, opt_i_str = update.callback_query.data.split("_")
    idx, opt_i = int(idx_str), int(opt_i_str)
    cat    = CATEGORIES[idx]
    chosen = cat["options"][opt_i]
    ctx.user_data["predictions"][cat["id"]] = chosen
    return await ask_wish(update, ctx, chosen)

async def handle_wish(update, ctx):
    await update.callback_query.answer()
    _, idx_str, opt_i_str = update.callback_query.data.split("_")
    idx, opt_i = int(idx_str), int(opt_i_str)
    cat = CATEGORIES[idx]
    ctx.user_data["wishes"][cat["id"]] = cat["options"][opt_i]
    ctx.user_data["idx"] = idx + 1
    return await ask_predict(update, ctx)

async def finish(update, ctx):
    user = update.effective_user
    uid  = str(user.id)
    predictions = ctx.user_data.get("predictions", {})
    wishes      = ctx.user_data.get("wishes", {})
    votes = load(DATA_FILE)
    is_revote = votes.get(uid, {}).get("completed", False)
    votes[uid] = {"name": user.first_name, "username": user.username or "",
                  "predictions": predictions, "wishes": wishes, "completed": True}
    save(DATA_FILE, votes)
    lines = []
    for cat in CATEGORIES:
        p = predictions.get(cat["id"], "—")
        w = wishes.get(cat["id"],      "—")
        lines.append(f"*{cat['title']}*\n  🔮 `{p}`\n  ❤️ `{w}`" + (" ✓" if p==w else ""))
    prefix = "🔄 *Предсказания обновлены!*" if is_revote else "✅ *Предсказания записаны!*"
    msg = update.callback_query.message if update.callback_query else update.message
    await msg.reply_text(
        f"{prefix}\n\n" + "\n\n".join(lines) +
        "\n\n🎬 Церемония — *15 марта 2026*. Удачи!\nПосле объявления победителей: /leaderboard",
        parse_mode="Markdown")
    return ConversationHandler.END

async def cancel(update, ctx):
    await update.message.reply_text("Голосование отменено. /start — начать заново.")
    return ConversationHandler.END

async def my_votes(update, ctx):
    uid   = str(update.effective_user.id)
    entry = load(DATA_FILE).get(uid)
    if not entry:
        await update.message.reply_text("Ты ещё не голосовал! /start")
        return
    preds  = entry.get("predictions", {})
    wishes = entry.get("wishes", {})
    lines  = []
    for cat in CATEGORIES:
        p = preds.get(cat["id"],  "—")
        w = wishes.get(cat["id"], "—")
        lines.append(f"*{cat['title']}*\n  🔮 `{p}`\n  ❤️ `{w}`" + (" ✓" if p==w else ""))
    open_, info = voting_open()
    footer = f"\n\n⏳ До закрытия: *{info}*" if open_ and info else ("\n\n🔒 Голосование закрыто." if not open_ else "")
    await update.message.reply_text(
        "🗳 *Твои предсказания:*\n\n" + "\n\n".join(lines) + footer,
        parse_mode="Markdown")


# ─── ДЕДЛАЙН (admin) ─────────────────────────

async def set_deadline(update, ctx):
    """
    /set_deadline 14.03.2026 22:00
    Время считается как МСК (UTC+3).
    /set_deadline off  — убрать дедлайн
    """
    uid = update.effective_user.id
    if ADMIN_IDS and uid not in ADMIN_IDS:
        await update.message.reply_text("⛔ Только для администраторов.")
        return

    if not ctx.args:
        dl = get_deadline()
        cfg = load(CONFIG_FILE)
        is_custom = "deadline_utc" in cfg
        dl_msk = dl.strftime("%d.%m.%Y %H:%M МСК")
        source = "" if is_custom else " _(по умолчанию)_"
        await update.message.reply_text(
            f"⏰ Дедлайн: *{dl_msk}*{source}\n\n"
            "Изменить: `/set_deadline 14.03.2026 22:00` (МСК)\n"
            "Сбросить к дефолту: `/set_deadline off`",
            parse_mode="Markdown")
        return

    if ctx.args[0].lower() == "off":
        cfg = load(CONFIG_FILE)
        cfg.pop("deadline_utc", None)
        save(CONFIG_FILE, cfg)
        await update.message.reply_text(
            "✅ Дедлайн сброшен к дефолту: *14.03.2026 19:00 МСК*",
            parse_mode="Markdown")
        return

    # Парсим дату и время
    try:
        if len(ctx.args) >= 2:
            dt_str = f"{ctx.args[0]} {ctx.args[1]}"
        else:
            dt_str = ctx.args[0]
        naive = datetime.strptime(dt_str, "%d.%m.%Y %H:%M")
        # МСК = UTC+3
        from datetime import timedelta
        utc_dt = naive.replace(tzinfo=timezone.utc) - timedelta(hours=3)
        cfg = load(CONFIG_FILE)
        cfg["deadline_utc"] = utc_dt.isoformat()
        save(CONFIG_FILE, cfg)
        await update.message.reply_text(
            f"✅ Дедлайн установлен: *{naive.strftime('%d.%m.%Y %H:%M')} МСК*",
            parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат. Используй: `/set_deadline 14.03.2026 22:00`",
            parse_mode="Markdown")


# ─── ADMIN — ввод результатов кнопками ───────

def _admin_cat_keyboard(results):
    rows = []
    for cat in CATEGORIES:
        done = "✅ " if cat["id"] in results else "⬜ "
        rows.append([InlineKeyboardButton(done + cat["title"], callback_data=f"acat_{cat['id']}")])
    rows.append([InlineKeyboardButton("🏁 Готово — показать лидеров", callback_data="adone")])
    return InlineKeyboardMarkup(rows)

def _admin_win_keyboard(cat_id):
    cat  = next(c for c in CATEGORIES if c["id"] == cat_id)
    rows = [[InlineKeyboardButton(opt, callback_data=f"awin_{cat_id}_{i}")]
            for i, opt in enumerate(cat["options"])]
    rows.append([InlineKeyboardButton("« Назад", callback_data="aback")])
    return InlineKeyboardMarkup(rows)

async def admin(update, ctx):
    uid = update.effective_user.id
    if ADMIN_IDS and uid not in ADMIN_IDS:
        await update.message.reply_text("⛔ Только для администраторов.")
        return ConversationHandler.END
    results = load(RESULTS_FILE)
    await update.message.reply_text(
        f"🎬 *Панель результатов* ({len(results)}/{TOTAL} введено)\n\nВыбери категорию:",
        reply_markup=_admin_cat_keyboard(results), parse_mode="Markdown")
    return ADMIN_CAT

async def admin_pick_cat(update, ctx):
    query = update.callback_query
    await query.answer()
    if query.data == "adone":
        results = load(RESULTS_FILE)
        lines = "\n".join(
            f"• {next(c['title'] for c in CATEGORIES if c['id']==k)}: `{v}`"
            for k,v in results.items())
        await query.edit_message_text(
            f"✅ *Введено {len(results)}/{TOTAL}:*\n\n{lines or '—'}\n\nТеперь /leaderboard доступен всем.",
            parse_mode="Markdown")
        return ConversationHandler.END
    cat_id = query.data[len("acat_"):]
    ctx.user_data["admin_cat"] = cat_id
    cat     = next(c for c in CATEGORIES if c["id"] == cat_id)
    results = load(RESULTS_FILE)
    note    = f"\n\nСейчас: `{results[cat_id]}`" if cat_id in results else ""
    await query.edit_message_text(
        f"*{cat['title']}*{note}\n\n🏆 Кто победил?",
        reply_markup=_admin_win_keyboard(cat_id), parse_mode="Markdown")
    return ADMIN_WIN

async def admin_pick_winner(update, ctx):
    query = update.callback_query
    await query.answer()
    if query.data == "aback":
        results = load(RESULTS_FILE)
        await query.edit_message_text(
            f"🎬 *Панель результатов* ({len(results)}/{TOTAL} введено)\n\nВыбери категорию:",
            reply_markup=_admin_cat_keyboard(results), parse_mode="Markdown")
        return ADMIN_CAT
    # awin_<cat_id>_<opt_index>
    parts  = query.data.split("_")
    opt_i  = int(parts[-1])
    cat_id = "_".join(parts[1:-1])
    cat    = next(c for c in CATEGORIES if c["id"] == cat_id)
    winner = cat["options"][opt_i]
    results = load(RESULTS_FILE)
    results[cat_id] = winner
    save(RESULTS_FILE, results)
    await query.edit_message_text(
        f"✅ *{cat['title']}*\nПобедитель: `{winner}`\n\nВведено {len(results)}/{TOTAL}:",
        reply_markup=_admin_cat_keyboard(results), parse_mode="Markdown")
    return ADMIN_CAT

async def admin_cancel(update, ctx):
    await update.message.reply_text("Ввод результатов отменён.")
    return ConversationHandler.END


# ─── ЛИДЕРЫ / СТАТИСТИКА ─────────────────────

async def leaderboard(update, ctx):
    results = load(RESULTS_FILE)
    votes   = load(DATA_FILE)
    if not results:
        await update.message.reply_text("⏳ Результаты ещё не загружены.\nПриходи после 15 марта! 🎬")
        return
    graded = len(results)
    scores = []
    for uid, data in votes.items():
        if not data.get("completed"): continue
        preds  = data.get("predictions", {})
        wishes = data.get("wishes", {})
        correct = sum(1 for cid,w in results.items() if preds.get(cid,"").strip().lower()==w.strip().lower())
        wish_ok = sum(1 for cid,w in results.items() if wishes.get(cid,"").strip().lower()==w.strip().lower())
        scores.append({"name": data.get("name","???"), "username": data.get("username",""),
                       "correct": correct, "wish_ok": wish_ok, "total": graded,
                       "pct": round(100*correct/graded) if graded else 0})
    scores.sort(key=lambda x: x["correct"], reverse=True)
    medals = ["🥇","🥈","🥉"]
    lines  = []
    for i, s in enumerate(scores[:20]):
        tag  = f"@{s['username']}" if s["username"] else s["name"]
        wish = f"  ❤️ {s['wish_ok']}/{s['total']}" if s["wish_ok"] else ""
        lines.append(f"{medals[i] if i<3 else str(i+1)+'.'} {tag}: 🔮 {s['correct']}/{s['total']} ({s['pct']}%){wish}")
    dream = sorted(scores, key=lambda x: x["wish_ok"], reverse=True)
    dreamer = ""
    if dream and dream[0]["wish_ok"] > 0:
        d   = dream[0]
        tag = f"@{d['username']}" if d["username"] else d["name"]
        dreamer = f"\n\n❤️ *Лучший мечтатель:* {tag} ({d['wish_ok']}/{d['total']} желаний сбылось!)"
    await update.message.reply_text(
        f"🏆 *Таблица лидеров* ({graded}/{TOTAL} категорий)\n\n" +
        ("\n".join(lines) or "Никто не проголосовал!") + dreamer,
        parse_mode="Markdown")

async def stats(update, ctx):
    votes = load(DATA_FILE)
    total_voters = sum(1 for v in votes.values() if v.get("completed"))
    if not total_voters:
        await update.message.reply_text("Пока никто не проголосовал!")
        return
    open_, info = voting_open()
    status = f"⏳ До закрытия: *{info}*" if open_ and info else ("🔒 Голосование закрыто." if not open_ else "🟢 Голосование открыто.")
    lines = [f"👥 *Проголосовало: {total_voters} чел.*  {status}\n"]
    for cat in CATEGORIES:
        pt, wt = {}, {}
        for data in votes.values():
            if not data.get("completed"): continue
            pp = data.get("predictions",{}).get(cat["id"],"")
            ww = data.get("wishes",{}).get(cat["id"],"")
            if pp: pt[pp] = pt.get(pp,0)+1
            if ww: wt[ww] = wt.get(ww,0)+1
        top_p = sorted(pt.items(), key=lambda x:-x[1])[:2]
        top_w = sorted(wt.items(), key=lambda x:-x[1])[:2]
        p_str = "  |  ".join(f"{k.split('—')[0].strip()} ({v})" for k,v in top_p)
        w_str = "  |  ".join(f"{k.split('—')[0].strip()} ({v})" for k,v in top_w)
        lines.append(f"*{cat['title']}*\n  🔮 {p_str}\n  ❤️ {w_str}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ─── ЗАПУСК ──────────────────────────────────

def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError("Нет BOT_TOKEN!")

    app = Application.builder().token(token).build()

    user_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            PREDICT: [
                CallbackQueryHandler(handle_predict, pattern=r"^predict_\d+_\d+$"),
                CallbackQueryHandler(handle_revote,    pattern=r"^revote$"),
                CallbackQueryHandler(handle_showvotes, pattern=r"^showvotes$"),
            ],
            WISH: [CallbackQueryHandler(handle_wish, pattern=r"^wish_\d+_\d+$")],
            ConversationHandler.END: [
                CallbackQueryHandler(handle_revote,    pattern=r"^revote$"),
                CallbackQueryHandler(handle_showvotes, pattern=r"^showvotes$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
        allow_reentry=True,
    )

    admin_conv = ConversationHandler(
        entry_points=[CommandHandler("admin", admin)],
        states={
            ADMIN_CAT: [CallbackQueryHandler(admin_pick_cat,    pattern=r"^(acat_|adone)")],
            ADMIN_WIN: [CallbackQueryHandler(admin_pick_winner, pattern=r"^(awin_|aback)")],
        },
        fallbacks=[CommandHandler("admin_cancel", admin_cancel)],
        per_message=False,
    )

    app.add_handler(user_conv)
    app.add_handler(admin_conv)
    app.add_handler(CommandHandler("my_votes",     my_votes))
    app.add_handler(CommandHandler("leaderboard",  leaderboard))
    app.add_handler(CommandHandler("stats",        stats))
    app.add_handler(CommandHandler("set_deadline", set_deadline))

    logger.info("🎬 Oscar Bot запущен!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
