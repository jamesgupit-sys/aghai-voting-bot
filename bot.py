import json
import os
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ==========================
# CONFIGURATION
# ==========================

TOKEN = os.getenv("BOT_TOKEN")

ADMIN_IDS = [8324041197, 1037677076]

DATA_FILE = "votes.json"

VOTING_OPEN = True
DEADLINE = None

REMINDER_INTERVAL_SECONDS = 86400  # Once per day

# ==========================
# LOGGING
# ==========================

logging.basicConfig(level=logging.INFO)

# ==========================
# QUESTIONS
# ==========================

QUESTIONS = {
    "q1": """AGHAI Members’ Special Assembly to APPROVE/REJECT the following URGENT resolution:

1. APPROVE/REJECT the conduct of immediate AGHAI Board elections to ensure continuity of governance and prevent any leadership or administrative vacuum after April 1, 2026, when the incoming Board is scheduled to officially assume responsibility.
""",

    "q2": """2. APPROVE/REJECT the appointment of the following nominees to serve as the AGHAI Election Committee:

• Manny de Leon  
• Annabelle Yong  
• Conrad Alampay  
• Ernie Manansala  
• Elvie Guzman  

All of whom have agreed to serve.
""",

    "q3": """3. APPROVE/REJECT the adoption of Electronic Online Voting for the 2026 AGHAI elections using secure platforms with identity verification, audit trails, and safeguards in compliance with RA 9904 and DHSUD guidelines.
""",

    "q4": """4. APPROVE ONE of the following proposed director term structures:

4a. All 11 directors serve 2-year terms; elections every 2 years.

OR

4b. Top 5 serve 2 years; next 6 serve 1 year to retain staggered terms.
"""
}

OPTIONS = {
    "q1": ["APPROVE", "REJECT"],
    "q2": ["APPROVE", "REJECT"],
    "q3": ["APPROVE", "REJECT"],
    "q4": ["4a", "4b"],
}

# ==========================
# STORAGE FUNCTIONS
# ==========================

def load_votes():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_votes(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

# ==========================
# START COMMAND
# ==========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    message = f"""
Welcome {user.first_name} 👋

🗳 AGHAI Official Voting Portal

Instructions:
• Tap "Begin Voting"
• You may vote only once
• You may use /revote to modify
• Voting deadline applies
• Only admins can view results

"""
    keyboard = [[InlineKeyboardButton("🗳 Begin Voting", callback_data="begin")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(message, reply_markup=reply_markup)

# ==========================
# BEGIN VOTING
# ==========================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global VOTING_OPEN

    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)

    if not VOTING_OPEN:
        await query.edit_message_text("Voting is currently CLOSED.")
        return

    if DEADLINE and datetime.now() >= DEADLINE:
        await query.edit_message_text("Voting deadline has passed.")
        return

    votes = load_votes()

    if query.data == "begin":
        if user_id in votes and votes[user_id]["answers"]:
            await query.edit_message_text(
                "⚠️ You have already voted.\nUse /revote to modify your answers."
            )
            return

        votes[user_id] = {
            "name": query.from_user.full_name,
            "answers": {}
        }
        save_votes(votes)

        await ask_question(query, context, "q1")
        return

    # Answer handling
    q_key, answer = query.data.split("|")

    votes = load_votes()
    votes[user_id]["answers"][q_key] = answer
    save_votes(votes)

    next_q = get_next_question(q_key)

    if next_q:
        await ask_question(query, context, next_q)
    else:
        await query.edit_message_text("✅ Thank you. Your vote has been recorded.")

# ==========================
# ASK QUESTION
# ==========================

async def ask_question(query, context, q_key):
    keyboard = []
    for opt in OPTIONS[q_key]:
        keyboard.append([
            InlineKeyboardButton(opt, callback_data=f"{q_key}|{opt}")
        ])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        QUESTIONS[q_key],
        reply_markup=reply_markup
    )

# ==========================
# NEXT QUESTION
# ==========================

def get_next_question(current):
    keys = list(QUESTIONS.keys())
    idx = keys.index(current)
    if idx + 1 < len(keys):
        return keys[idx + 1]
    return None

# ==========================
# REVOTE
# ==========================

async def revote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    votes = load_votes()

    if user_id not in votes:
        await update.message.reply_text("You have not voted yet.")
        return

    # FULLY remove previous vote
    del votes[user_id]
    save_votes(votes)

    keyboard = [[InlineKeyboardButton("🗳 Begin Voting Again", callback_data="begin")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Your previous vote has been completely cleared. You may vote again.",
        reply_markup=reply_markup
    )

# ==========================
# RESULTS
# ==========================

async def results(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    votes = load_votes()

    summary = {}
    for q in QUESTIONS:
        summary[q] = {}
        for opt in OPTIONS[q]:
            summary[q][opt] = 0

    for voter in votes.values():
        for q, ans in voter["answers"].items():
            if q in summary and ans in summary[q]:
                summary[q][ans] += 1

    message = "📊 VOTING SUMMARY\n\n"

    for q in QUESTIONS:
        message += f"{q.upper()}:\n"
        for opt in OPTIONS[q]:
            message += f"{opt}: {summary[q][opt]}\n"
        message += "\n"

    message += "👥 WHO VOTED:\n\n"

    for voter in votes.values():
        message += f"{voter['name']}:\n"
        for q, ans in voter["answers"].items():
            message += f"  {q.upper()}: {ans}\n"
        message += "\n"

    MAX = 4000
    for i in range(0, len(message), MAX):
        await update.message.reply_text(message[i:i+MAX])

# ==========================
# ADMIN COMMANDS
# ==========================

async def open_vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global VOTING_OPEN
    if update.effective_user.id in ADMIN_IDS:
        VOTING_OPEN = True
        await update.message.reply_text("Voting is now OPEN.")

async def close_vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global VOTING_OPEN
    if update.effective_user.id in ADMIN_IDS:
        VOTING_OPEN = False
        await update.message.reply_text("Voting is now CLOSED.")

async def clear_votes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id in ADMIN_IDS:
        save_votes({})
        await update.message.reply_text("All votes cleared.")

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Your ID: {update.effective_user.id}\nChat ID: {update.effective_chat.id}"
    )

# ==========================
# REMINDER (ONCE DAILY)
# ==========================

async def reminder(context: ContextTypes.DEFAULT_TYPE):
    votes = load_votes()
    for admin in ADMIN_IDS:
        await context.bot.send_message(
            chat_id=admin,
            text="Reminder: Voting is ongoing."
        )

# ==========================
# MAIN
# ==========================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("revote", revote))
    app.add_handler(CommandHandler("results", results))
    app.add_handler(CommandHandler("open", open_vote))
    app.add_handler(CommandHandler("close", close_vote))
    app.add_handler(CommandHandler("clearvotes", clear_votes))
    app.add_handler(CommandHandler("getid", get_id))
    app.add_handler(CallbackQueryHandler(button_handler))

    app.job_queue.run_repeating(reminder, interval=REMINDER_INTERVAL_SECONDS)
    # ==========================
    # ADD THIS SECTION BELOW
    # ==========================

    import threading
    from flask import Flask
    import os

    def run_web():
        web_app = Flask(__name__)

        @web_app.route("/")
        def home():
            return "Aghai Elections Bot is running!"

        port = int(os.environ.get("PORT", 10000))
        web_app.run(host="0.0.0.0", port=port)

    threading.Thread(target=run_web).start()

    # ==========================
    # END OF ADDED SECTION
    # ==========================

    print("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()


