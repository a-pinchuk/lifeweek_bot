import logging
import json
import time
import numpy as np
import matplotlib.pyplot as plt
import os
from matplotlib.patches import Rectangle
from io import BytesIO
from datetime import datetime, time as dtime
from dateutil import parser
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
    JobQueue,
)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DATA_FILE = "users_data.json"

TOTAL_YEARS = 85
WEEKS_PER_YEAR = 52
TOTAL_WEEKS = TOTAL_YEARS * WEEKS_PER_YEAR
TOTAL_DAYS = TOTAL_YEARS * 365

ASK_BIRTHDATE = 1

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def load_users():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_users(users):
    with open(DATA_FILE, "w") as f:
        json.dump(users, f)

users_data = load_users()

# Храним в памяти число прожитых недель для отслеживания новой недели
last_weeks_lived = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Привет! Введи свою дату рождения в формате ДД.ММ.ГГГГ:")
    return ASK_BIRTHDATE

async def ask_birthdate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        birthdate = parser.parse(update.message.text, dayfirst=True)
        user_id = str(update.effective_chat.id)
        users_data[user_id] = birthdate.strftime("%Y-%m-%d")
        save_users(users_data)

        await update.message.reply_text(
            "Дата рождения сохранена.\n"
            "Предположим что ты проживёшь 85 лет.\n"
            "Теперь я буду каждый день в 10:00 присылать тебе статистику о прожитых и оставшихся неделях.\n"
            "Ниже список доступных команд:"
        )
        await help_command(update, context)

        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Ошибка! Введи дату в формате ДД.ММ.ГГГГ.")
        return ASK_BIRTHDATE

def calculate_weeks_days(birthdate_str):
    birthdate = datetime.strptime(birthdate_str, "%Y-%m-%d")
    now = datetime.now()
    days_lived = (now - birthdate).days
    weeks_lived = days_lived // 7

    days_left = TOTAL_DAYS - days_lived
    weeks_left = TOTAL_WEEKS - weeks_lived

    return weeks_lived, days_lived, max(weeks_left, 0), max(days_left, 0)

def calculate_age(birthdate_str):
    birthdate = datetime.strptime(birthdate_str, "%Y-%m-%d")
    now = datetime.now()
    age = now.year - birthdate.year
    if (now.month, now.day) < (birthdate.month, birthdate.day):
        age -= 1
    return age

async def weeks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_chat.id)
    if user_id not in users_data:
        await update.message.reply_text("Сначала введи дату рождения через /start.")
        return

    weeks_lived, days_lived, weeks_left, days_left = calculate_weeks_days(users_data[user_id])
    msg = (
        f"Прожито недель: {weeks_lived}\n"
        f"Прожито дней: {days_lived}\n"
        f"Осталось недель (из {TOTAL_WEEKS}): {weeks_left}\n"
        f"Осталось дней (из {TOTAL_DAYS}): {days_left}"
    )
    await update.message.reply_text(msg)

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_chat.id)
    if user_id in users_data:
        del users_data[user_id]
        save_users(users_data)
        await update.message.reply_text("Данные сброшены! Введи новую дату рождения с помощью /start.")
    else:
        await update.message.reply_text("Данные не найдены. Введи дату рождения через /start.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Команды:\n"
        "/start — Ввести или изменить дату рождения\n"
        "/weeks — Сколько недель и дней прожито, а сколько осталось\n"
        "/reset — Сбросить дату рождения и ввести заново\n"
        "/help — Справка\n"
        "/stats — График прожитых и оставшихся недель"
    )

def create_life_matrix(weeks_lived: int, total_years=85, weeks_in_year=52):
    matrix = np.zeros((total_years, weeks_in_year))
    for i in range(weeks_lived):
        row = i // weeks_in_year
        col = i % weeks_in_year
        if row < total_years:
            matrix[row, col] = 1
    return matrix

def generate_life_chart(birthdate_str) -> BytesIO:
    weeks_lived, _, _, _ = calculate_weeks_days(birthdate_str)
    matrix = create_life_matrix(weeks_lived, TOTAL_YEARS, WEEKS_PER_YEAR)

    fig, ax = plt.subplots(figsize=(8, 14))

    for row in range(TOTAL_YEARS):
        for col in range(WEEKS_PER_YEAR):
            if matrix[row, col] == 1:
                color_fill = "lightcoral"
            else:
                color_fill = "whitesmoke"
            rect = Rectangle(
                (col, row),
                1, 1,
                facecolor=color_fill,
                edgecolor="silver",
                linewidth=0.5
            )
            ax.add_patch(rect)

    ax.set_xlim(0, WEEKS_PER_YEAR)
    ax.set_ylim(0, TOTAL_YEARS)
    ax.invert_yaxis()
    ax.set_aspect("equal")

    ax.set_xlabel("Недели")
    ax.set_ylabel("Возраст")

    x_ticks = [1, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50]
    ax.set_xticks(x_ticks)
    ax.set_xticklabels([str(x) for x in x_ticks])

    y_ticks = list(range(0, TOTAL_YEARS + 1, 5))
    ax.set_yticks(y_ticks)
    ax.set_yticklabels([str(y) for y in y_ticks])

    img_stream = BytesIO()
    plt.savefig(img_stream, format='png', bbox_inches='tight')
    img_stream.seek(0)
    plt.close(fig)
    return img_stream

async def send_life_chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_chat.id)
    if user_id not in users_data:
        await update.message.reply_text("Сначала введи дату рождения /start.")
        return

    chart_stream = generate_life_chart(users_data[user_id])
    await update.message.reply_photo(photo=chart_stream, caption="Твой график жизни в неделях")

async def send_daily_message(context: ContextTypes.DEFAULT_TYPE):
    """
    Вызывается каждый день в 10:00.
    Если началась новая неделя (weeks_lived выросло), дополнительно присылаем диаграмму.
    """
    now = datetime.now()
    today_str = now.strftime("%d.%m.%Y")

    for user_id, birthdate in users_data.items():
        weeks_lived, days_lived, weeks_left, days_left = calculate_weeks_days(birthdate)
        age = calculate_age(birthdate)

        message = (
            f"Привет, сегодня {today_str}\n"
            f"Тебе - {age} лет\n"
            f"Прожито недель: {weeks_lived}\n"
            f"Прожито дней: {days_lived}\n"
            f"Осталось недель (из {TOTAL_WEEKS}): {weeks_left}\n"
            f"Осталось дней (из {TOTAL_DAYS}): {days_left}"
        )
        try:
            await context.bot.send_message(chat_id=int(user_id), text=message)
        except Exception as e:
            logging.error(f"Ошибка отправки сообщения пользователю {user_id}: {e}")
            continue

        # Проверяем, началась ли новая неделя
        old_weeks = last_weeks_lived.get(user_id, -1)
        if weeks_lived > old_weeks:
            chart_stream = generate_life_chart(birthdate)
            caption = (
                f"Началась новая неделя (#{weeks_lived}).\n"
                f"Ниже актуальный график прожитых недель."
            )
            try:
                await context.bot.send_photo(chat_id=int(user_id), photo=chart_stream, caption=caption)
            except Exception as e:
                logging.error(f"Ошибка отправки диаграммы пользователю {user_id}: {e}")

        last_weeks_lived[user_id] = weeks_lived

# В JobQueue достаточно объявить асинхронную функцию, которую мы назначим на run_daily.
async def daily_job(context: ContextTypes.DEFAULT_TYPE):
    await send_daily_message(context)

def main():
    application = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={ASK_BIRTHDATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_birthdate)]},
        fallbacks=[]
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("weeks", weeks_command))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", send_life_chart))

    # Создаем job_queue и регистрируем задачу, которая будет вызываться
    # каждый день в 10:00 по локальному времени
    job_queue = application.job_queue
    job_queue.run_daily(
        daily_job,                # функция, которую выполняем
        time=dtime(hour=10, minute=0)  # время 10:00
    )

    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
