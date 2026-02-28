#!/usr/bin/env python3
"""
Oscar 2026 · Prediction Bot
98th Academy Awards · 15 марта 2026
"""

import json, os, logging
from datetime import datetime, timezone, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler
)

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ── НОМИНАЦИИ ─────────────────────────────────────────────────────────────────

CATEGORIES = [
    {"id": "best_picture", "title": "Лучший фильм",
     "options": ["Bugonia","F1","Frankenstein","Hamnet","Marty Supreme",
                 "One Battle After Another","The Secret Agent","Sentimental Value","Sinners","Train Dreams"]},
    {"id": "best_director", "title": "Лучшая режиссура",
     "options": ["Ryan Coogler — Sinners","Paul Thomas Anderson — One Battle After Another",
                 "Josh Safdie — Marty Supreme","Joachim Trier — Sentimental Value","Chloé Zhao — Hamnet"]},
    {"id": "best_actor", "title": "Лучший актёр",
     "options": ["Timothée Chalamet — Marty Supreme","Leonardo DiCaprio — One Battle After Another",
                 "Ethan Hawke — Blue Moon","Michael B. Jordan — Sinners","Wagner Moura — The Secret Agent"]},
    {"id": "best_actress", "title": "Лучшая актриса",
     "options": ["Jessie Buckley — Hamnet","Rose Byrne — If I Had Legs, I'd Kick You",
                 "Kate Hudson — Song Sung Blue","Renate Reinsve — Sentimental Value","Emma Stone — Bugonia"]},
    {"id": "best_supporting_actor", "title": "Лучший актёр второго плана",
     "options": ["Benicio del Toro — One Battle After Another","Miles Caton — Sinners",
                 "Jacob Elordi — Frankenstein","Delroy Lindo — Sinners","Sean Penn — One Battle After Another"]},
    {"id": "best_supporting_actress", "title": "Лучшая актриса второго плана",
     "options": ["Elle Fanning — Sentimental Value","Inga Ibsdotter Lilleaas — Sentimental Value",
                 "Amy Madigan — Weapons","Wunmi Mosaku — Sinners","Teyana Taylor — One Battle After Another"]},
    {"id": "best_animated", "title": "Лучший анимационный фильм",
     "options": ["Arco","Elio","KPop Demon Hunters","Little Amélie or the Character of Rain","Zootopia 2"]},
    {"id": "best_adapted_screenplay", "title": "Лучший адаптированный сценарий",
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
DEFAULT_DEADLINE = datetime(2026, 3, 14, 16, 0, tzinfo=timezone.utc)

PREDICT, WISH        = 0, 1
ADMIN_CAT, ADMIN_WIN = 10, 11

DIVIDER = "· · · · · · · · · · · · · · ·"


# ── ХРАНИЛИЩЕ ─────────────────────────────────────────────────────────────────

def load(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── ДЕДЛАЙН ───────────────────────────────────────────────────────────────────

def get_deadline():
    cfg = load(CONFIG_FILE)
    ts  = cfg.get("deadline_utc")
    return datetime.fromisoformat(ts) if ts else DEFAULT_DEADLINE

def voting_open():
    dl  = get_deadline()
    now = datetime.now(timezone.utc)
    if now >= dl:
        dl_msk = (dl + timedelta(hours=3)).strftime("%d.%m.%Y, %H:%M")
        return False, f"Приём прогнозов завершён · {dl_msk} МСК"
    left = dl - now
    h    = int(left.total_seconds() // 3600)
    m    = int((left.total_seconds() % 3600) // 60)
    if h >= 24:
        d = h // 24; remaining = f"{d} д. {h % 24} ч."
    elif h > 0:
        remaining = f"{h} ч. {m} мин."
    else:
        remaining = f"{m} мин."
    return True, remaining


# ── КЛАВИАТУРЫ ────────────────────────────────────────────────────────────────

def make_keyboard(cat_index, mode):
    rows = [
        [InlineKeyboardButton(opt, callback_data=f"{mode}_{cat_index}_{i}")]
        for i, opt in enumerate(CATEGORIES[cat_index]["options"])
    ]
    if cat_index > 0:
        rows.append([InlineKeyboardButton("← Назад", callback_data=f"back_{mode}_{cat_index}")])
    return InlineKeyboardMarkup(rows)

async def send_or_edit(update, text, markup):
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")
    elif update.message:
        await update.message.reply_text(text, reply_markup=markup, parse_mode="Markdown")


# ── ВОПРОСЫ ───────────────────────────────────────────────────────────────────

async def ask_predict(update, ctx):
    idx = ctx.user_data.get("idx", 0)
    if idx >= TOTAL:
        return await finish(update, ctx)
    cat  = CATEGORIES[idx]
    step = f"{idx + 1} / {TOTAL}"
    text = (
        f"*{cat['title'].upper()}*\n"
        f"_{step}_\n\n"
        f"★  Кто, на ваш взгляд, получит статуэтку?"
    )
    await send_or_edit(update, text, make_keyboard(idx, "predict"))
    return PREDICT

async def ask_wish(update, ctx, predicted):
    idx  = ctx.user_data.get("idx", 0)
    cat  = CATEGORIES[idx]
    step = f"{idx + 1} / {TOTAL}"
    text = (
        f"*{cat['title'].upper()}*\n"
        f"_{step}_\n\n"
        f"Ваш прогноз: `{predicted}`\n\n"
        f"✦  А кого вы хотели бы видеть победителем?"
    )
    await send_or_edit(update, text, make_keyboard(idx, "wish"))
    return WISH


# ── ГОЛОСОВАНИЕ ───────────────────────────────────────────────────────────────

async def start(update, ctx):
    user  = update.effective_user
    uid   = str(user.id)
    open_, info = voting_open()
    entry = load(DATA_FILE).get(uid, {})

    if entry.get("completed"):
        if open_:
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("Изменить прогнозы", callback_data="revote"),
                InlineKeyboardButton("Мои ответы",        callback_data="showvotes"),
            ]])
            await update.message.reply_text(
                f"*OSCAR 2026*\n\n"
                f"Ваши прогнозы уже записаны.\n"
                f"До закрытия голосования: *{info}*\n\n"
                f"Можете изменить ответы или просмотреть их:",
                reply_markup=keyboard, parse_mode="Markdown")
        else:
            await update.message.reply_text(
                f"*OSCAR 2026*\n\n{info}\n\n"
                "/my\\_votes — ваши прогнозы\n"
                "/leaderboard — таблица лидеров",
                parse_mode="Markdown")
        return ConversationHandler.END

    if not open_:
        await update.message.reply_text(
            f"*OSCAR 2026*\n\n{info}\n\nПринять участие уже не получится.",
            parse_mode="Markdown")
        return ConversationHandler.END

    deadline_line = f"Приём прогнозов закрывается через *{info}*\n\n" if info else ""
    await update.message.reply_text(
        f"*OSCAR 2026*\n"
        f"_98-я церемония · 15 марта 2026_\n\n"
        f"{DIVIDER}\n\n"
        f"{deadline_line}"
        f"Для каждой из *{TOTAL} категорий* — два вопроса:\n\n"
        f"★  Кто победит? — учитывается в рейтинге\n"
        f"✦  Кого хотите видеть? — для интереса\n\n"
        f"{DIVIDER}\n\n"
        f"Поехали →",
        parse_mode="Markdown")
    ctx.user_data.update({"idx": 0, "predictions": {}, "wishes": {}})
    return await ask_predict(update, ctx)

async def handle_back(update, ctx):
    """Кнопка ← Назад."""
    query = update.callback_query
    await query.answer()
    _, mode, idx_str = query.data.split("_")
    idx = int(idx_str) - 1
    ctx.user_data["idx"] = idx

    # Откатываем последний записанный ответ
    cat = CATEGORIES[idx]
    if mode == "predict":
        ctx.user_data["predictions"].pop(cat["id"], None)
        return await ask_predict(update, ctx)
    else:  # wish — возвращаемся к predict этой же категории
        ctx.user_data["predictions"].pop(cat["id"], None)
        return await ask_predict(update, ctx)

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

async def handle_revote(update, ctx):
    query = update.callback_query
    await query.answer()
    open_, _ = voting_open()
    if not open_:
        await query.edit_message_text("Голосование уже закрыто — изменить прогнозы нельзя.")
        return ConversationHandler.END
    ctx.user_data.update({"idx": 0, "predictions": {}, "wishes": {}})
    await query.edit_message_text("Начинаем заново →")
    return await ask_predict(update, ctx)

async def handle_showvotes(update, ctx):
    query = update.callback_query
    await query.answer()
    uid   = str(query.from_user.id)
    entry = load(DATA_FILE).get(uid, {})
    preds  = entry.get("predictions", {})
    wishes = entry.get("wishes", {})
    lines  = []
    for cat in CATEGORIES:
        p = preds.get(cat["id"],  "—")
        w = wishes.get(cat["id"], "—")
        match = " ·  совпадает" if p == w else ""
        lines.append(f"*{cat['title'].upper()}*\n  ★  `{p}`\n  ✦  `{w}`{match}")
    await query.edit_message_text(
        "ВАШИ ПРОГНОЗЫ\n\n" + f"\n{DIVIDER}\n".join(lines),
        parse_mode="Markdown")
    return ConversationHandler.END

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
        match = " ·  совпадает" if p == w else ""
        lines.append(f"*{cat['title'].upper()}*\n  ★  `{p}`\n  ✦  `{w}`{match}")
    prefix = "Прогнозы обновлены" if is_revote else "Прогнозы записаны"
    msg = update.callback_query.message if update.callback_query else update.message
    await msg.reply_text(
        f"*{prefix.upper()}*\n\n" +
        f"\n{DIVIDER}\n".join(lines) +
        f"\n\n{DIVIDER}\n\n"
        f"_Церемония — 15 марта 2026_\n"
        f"После объявления победителей: /leaderboard",
        parse_mode="Markdown")
    return ConversationHandler.END

async def cancel(update, ctx):
    await update.message.reply_text("Голосование прервано. /start — начать заново.")
    return ConversationHandler.END

async def my_votes(update, ctx):
    uid   = str(update.effective_user.id)
    entry = load(DATA_FILE).get(uid)
    if not entry:
        await update.message.reply_text("Вы ещё не голосовали. /start — начать.")
        return
    preds  = entry.get("predictions", {})
    wishes = entry.get("wishes", {})
    lines  = []
    for cat in CATEGORIES:
        p = preds.get(cat["id"],  "—")
        w = wishes.get(cat["id"], "—")
        match = " ·  совпадает" if p == w else ""
        lines.append(f"*{cat['title'].upper()}*\n  ★  `{p}`\n  ✦  `{w}`{match}")
    open_, info = voting_open()
    footer = f"\n\n_{('До закрытия: ' + info) if open_ and info else 'Голосование закрыто.'}_"
    await update.message.reply_text(
        "ВАШИ ПРОГНОЗЫ\n\n" + f"\n{DIVIDER}\n".join(lines) + footer,
        parse_mode="Markdown")


# ── ADMIN — ввод результатов ──────────────────────────────────────────────────

def _admin_cat_keyboard(results):
    rows = []
    for cat in CATEGORIES:
        mark = "✓  " if cat["id"] in results else "·  "
        rows.append([InlineKeyboardButton(mark + cat["title"], callback_data=f"acat_{cat['id']}")])
    rows.append([InlineKeyboardButton("— Готово —", callback_data="adone")])
    return InlineKeyboardMarkup(rows)

def _admin_win_keyboard(cat_id):
    cat  = next(c for c in CATEGORIES if c["id"] == cat_id)
    rows = [[InlineKeyboardButton(opt, callback_data=f"awin_{cat_id}_{i}")]
            for i, opt in enumerate(cat["options"])]
    rows.append([InlineKeyboardButton("← Назад", callback_data="aback")])
    return InlineKeyboardMarkup(rows)

async def admin(update, ctx):
    uid = update.effective_user.id
    if ADMIN_IDS and uid not in ADMIN_IDS:
        await update.message.reply_text("Доступ закрыт.")
        return ConversationHandler.END
    results = load(RESULTS_FILE)
    await update.message.reply_text(
        f"*ВВОД РЕЗУЛЬТАТОВ*  ·  {len(results)}/{TOTAL}\n\nВыберите категорию:",
        reply_markup=_admin_cat_keyboard(results), parse_mode="Markdown")
    return ADMIN_CAT

async def admin_pick_cat(update, ctx):
    query = update.callback_query
    await query.answer()
    if query.data == "adone":
        results = load(RESULTS_FILE)
        lines   = "\n".join(
            f"·  {next(c['title'] for c in CATEGORIES if c['id']==k)}: `{v}`"
            for k,v in results.items())
        await query.edit_message_text(
            f"*ИТОГО {len(results)}/{TOTAL}*\n\n{lines or '—'}\n\n_/leaderboard доступен всем_",
            parse_mode="Markdown")
        return ConversationHandler.END
    cat_id  = query.data[len("acat_"):]
    cat     = next(c for c in CATEGORIES if c["id"] == cat_id)
    results = load(RESULTS_FILE)
    note    = f"\n_Сейчас: {results[cat_id]}_" if cat_id in results else ""
    await query.edit_message_text(
        f"*{cat['title'].upper()}*{note}\n\nКто победил?",
        reply_markup=_admin_win_keyboard(cat_id), parse_mode="Markdown")
    return ADMIN_WIN

async def admin_pick_winner(update, ctx):
    query = update.callback_query
    await query.answer()
    if query.data == "aback":
        results = load(RESULTS_FILE)
        await query.edit_message_text(
            f"*ВВОД РЕЗУЛЬТАТОВ*  ·  {len(results)}/{TOTAL}\n\nВыберите категорию:",
            reply_markup=_admin_cat_keyboard(results), parse_mode="Markdown")
        return ADMIN_CAT
    parts   = query.data.split("_")
    opt_i   = int(parts[-1])
    cat_id  = "_".join(parts[1:-1])
    cat     = next(c for c in CATEGORIES if c["id"] == cat_id)
    winner  = cat["options"][opt_i]
    results = load(RESULTS_FILE)
    results[cat_id] = winner
    save(RESULTS_FILE, results)
    await query.edit_message_text(
        f"*{cat['title'].upper()}*\n`{winner}`\n\n{len(results)}/{TOTAL} введено:",
        reply_markup=_admin_cat_keyboard(results), parse_mode="Markdown")
    return ADMIN_CAT

async def admin_cancel(update, ctx):
    await update.message.reply_text("Ввод результатов прерван.")
    return ConversationHandler.END


# ── РЕЙТИНГ / СТАТИСТИКА ──────────────────────────────────────────────────────

async def leaderboard(update, ctx):
    results = load(RESULTS_FILE)
    votes   = load(DATA_FILE)
    if not results:
        await update.message.reply_text(
            "*OSCAR 2026*\n\nРезультаты ещё не объявлены.\nПриходите после 15 марта.",
            parse_mode="Markdown")
        return
    graded = len(results)
    scores = []
    for uid, data in votes.items():
        if not data.get("completed"): continue
        preds   = data.get("predictions", {})
        wishes  = data.get("wishes", {})
        correct = sum(1 for cid,w in results.items() if preds.get(cid,"").strip().lower()==w.strip().lower())
        wish_ok = sum(1 for cid,w in results.items() if wishes.get(cid,"").strip().lower()==w.strip().lower())
        scores.append({"name": data.get("name","—"), "username": data.get("username",""),
                       "correct": correct, "wish_ok": wish_ok, "total": graded,
                       "pct": round(100*correct/graded) if graded else 0})
    scores.sort(key=lambda x: x["correct"], reverse=True)
    place = ["I", "II", "III"]
    lines = []
    for i, s in enumerate(scores[:20]):
        tag  = f"@{s['username']}" if s["username"] else s["name"]
        rank = place[i] if i < 3 else f"{i+1}."
        wish = f"  ·  ✦ {s['wish_ok']}/{s['total']}" if s["wish_ok"] else ""
        lines.append(f"`{rank}`  {tag} — ★ {s['correct']}/{s['total']} ({s['pct']}%){wish}")
    dream = sorted(scores, key=lambda x: x["wish_ok"], reverse=True)
    dreamer = ""
    if dream and dream[0]["wish_ok"] > 0:
        d   = dream[0]
        tag = f"@{d['username']}" if d["username"] else d["name"]
        dreamer = f"\n\n_Лучший мечтатель: {tag} · {d['wish_ok']}/{d['total']} желаний сбылось_"
    await update.message.reply_text(
        f"*РЕЙТИНГ*  ·  {graded}/{TOTAL} категорий\n\n" +
        ("\n".join(lines) or "Никто не проголосовал.") + dreamer,
        parse_mode="Markdown")

async def stats(update, ctx):
    votes = load(DATA_FILE)
    total_voters = sum(1 for v in votes.values() if v.get("completed"))
    if not total_voters:
        await update.message.reply_text("Пока никто не проголосовал.")
        return
    open_, info = voting_open()
    status = f"до закрытия: {info}" if open_ and info else "голосование закрыто"
    lines  = [f"*{total_voters} участников*  ·  _{status}_\n"]
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
        p_str = "  ·  ".join(f"{k.split('—')[0].strip()} ({v})" for k,v in top_p)
        w_str = "  ·  ".join(f"{k.split('—')[0].strip()} ({v})" for k,v in top_w)
        lines.append(f"*{cat['title'].upper()}*\n  ★  {p_str}\n  ✦  {w_str}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── ДЕДЛАЙН (admin) ───────────────────────────────────────────────────────────

async def set_deadline(update, ctx):
    uid = update.effective_user.id
    if ADMIN_IDS and uid not in ADMIN_IDS:
        await update.message.reply_text("Доступ закрыт.")
        return
    dl = get_deadline()
    if not ctx.args:
        cfg      = load(CONFIG_FILE)
        dl_msk   = (dl + timedelta(hours=3)).strftime("%d.%m.%Y %H:%M")
        source   = "" if "deadline_utc" in cfg else " _(по умолчанию)_"
        await update.message.reply_text(
            f"Дедлайн: *{dl_msk} МСК*{source}\n\n"
            "Изменить: `/set_deadline 14.03.2026 22:00`\n"
            "Сброс: `/set_deadline off`",
            parse_mode="Markdown")
        return
    if ctx.args[0].lower() == "off":
        cfg = load(CONFIG_FILE); cfg.pop("deadline_utc", None); save(CONFIG_FILE, cfg)
        await update.message.reply_text("Дедлайн сброшен к значению по умолчанию: *14.03.2026 19:00 МСК*", parse_mode="Markdown")
        return
    try:
        dt_str = f"{ctx.args[0]} {ctx.args[1]}" if len(ctx.args) >= 2 else ctx.args[0]
        naive  = datetime.strptime(dt_str, "%d.%m.%Y %H:%M")
        utc_dt = naive.replace(tzinfo=timezone.utc) - timedelta(hours=3)
        cfg    = load(CONFIG_FILE); cfg["deadline_utc"] = utc_dt.isoformat(); save(CONFIG_FILE, cfg)
        await update.message.reply_text(f"Дедлайн: *{naive.strftime('%d.%m.%Y %H:%M')} МСК*", parse_mode="Markdown")
    except (ValueError, IndexError):
        await update.message.reply_text("Формат: `/set_deadline 14.03.2026 22:00`", parse_mode="Markdown")


# ── ЗАПУСК ────────────────────────────────────────────────────────────────────

async def post_init(app):
    """Регистрируем команды — они появятся в меню '/'."""
    await app.bot.set_my_commands([
        BotCommand("start",       "Участвовать в голосовании"),
        BotCommand("my_votes",    "Мои прогнозы"),
        BotCommand("leaderboard", "Таблица лидеров"),
        BotCommand("stats",       "Статистика голосования"),
    ])

def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError("Нет BOT_TOKEN!")

    app = Application.builder().token(token).post_init(post_init).build()

    user_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            PREDICT: [
                CallbackQueryHandler(handle_predict, pattern=r"^predict_\d+_\d+$"),
                CallbackQueryHandler(handle_back,    pattern=r"^back_predict_\d+$"),
                CallbackQueryHandler(handle_revote,    pattern=r"^revote$"),
                CallbackQueryHandler(handle_showvotes, pattern=r"^showvotes$"),
            ],
            WISH: [
                CallbackQueryHandler(handle_wish, pattern=r"^wish_\d+_\d+$"),
                CallbackQueryHandler(handle_back, pattern=r"^back_wish_\d+$"),
            ],
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

    logger.info("Oscar Bot · запущен")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
