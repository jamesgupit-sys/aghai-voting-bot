import json
import os
import logging
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telegram.ext import ConversationHandler, MessageHandler, filters
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

VOTING_OPEN = True
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
# START
# ==========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    keyboard = [
        [InlineKeyboardButton("🗳 Begin Voting", callback_data="begin")],
        [InlineKeyboardButton("📝 Pre-Voting Registration", callback_data="prevote")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"""Welcome {user.first_name} 👋

🗳 AGHAI Official Voting Portal

Instructions:
• Tap "Begin Voting"
• You may vote only once
• You may change your vote before deadline
• Only admins can view results
""",
        reply_markup=reply_markup
    )

# ==========================
# SHOW MAIN MENU
# ==========================

async def show_main_menu(query_or_update, context):
    user = query_or_update.from_user if hasattr(query_or_update, "from_user") else query_or_update.effective_user

    keyboard = [
        [InlineKeyboardButton("🗳 Begin Voting", callback_data="begin")],
        [InlineKeyboardButton("📝 Pre-Voting Registration", callback_data="prevote")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = f"""Welcome {user.first_name} 👋

🗳 AGHAI Official Voting Portal

Instructions:
• Tap "Begin Voting"
• You may vote only once
• You may change your vote before deadline
• Only admins can view results
"""

    if hasattr(query_or_update, "callback_query"):
        await query_or_update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await query_or_update.message.reply_text(text, reply_markup=reply_markup)

# ==========================
# BUTTON HANDLER
# ==========================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global VOTING_OPEN

    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)

    # Auto deadline check (March 1, 2026)
    if datetime.now() >= datetime(2026, 3, 1, 0, 0):
        VOTING_OPEN = False

    if not VOTING_OPEN:
        await query.edit_message_text("Voting is currently CLOSED.")
        return

    # ================= BEGIN BUTTON =================
    if query.data == "begin":
        await handle_begin(query, user_id, context)
        return
    # ================= REVOTE BUTTON =================
    if query.data == "revote_button":
        if has_voted(user_id):
            clear_user_vote(user_id)

        keyboard = [[InlineKeyboardButton("🗳 Begin Voting Again", callback_data="begin")]]
        await query.edit_message_text(
            "Your previous vote has been cleared.\n\nClick below to vote again.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

# ================= PRE-VOTE =================
    if query.data == "prevote":
        await prevote_start(update, context)
        return

# ================= VOTING ANSWERS =================
    # Handles q1|APPROVE, q2|REJECT, etc.
    if "|" in query.data:
        q_key, answer = query.data.split("|")

        if "voting_answers" not in context.user_data:
            context.user_data["voting_answers"] = {}

        context.user_data["voting_answers"][q_key] = answer

        next_q = get_next_question(q_key)
        if next_q:
            await ask_question(query, next_q)
        else:
            # Save votes to Google Sheet
            answers = context.user_data["voting_answers"]
            voting_sheet.append_row([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                user_id,
                query.from_user.full_name,
                answers.get("q1", ""),
                answers.get("q2", ""),
                answers.get("q3", ""),
                answers.get("q4", "")
            ])

            keyboard = [[InlineKeyboardButton("🔁 Change My Vote", callback_data="revote_button")]]
            await query.edit_message_text(
                "✅ Thank you. Your vote has been recorded securely.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        return

# ================= BACK TO MENU =================
if query.data == "menu":
    await show_main_menu(query, context)
    return

# ================= HANDLE BEGIN =================

async def handle_begin(query, user_id, context):
    # 🔐 Require Pre-Voting Registration first
    if not has_submitted_prevote(user_id):
        keyboard = [[InlineKeyboardButton("📝 Complete Pre-Voting First", callback_data="prevote")]]
        await query.edit_message_text(
            "⚠️ You must complete Pre-Voting Registration before you can vote.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if has_voted(user_id):
        keyboard = [[InlineKeyboardButton("🔁 Change My Vote", callback_data="revote_button")]]
        await query.edit_message_text(
            "⚠️ You have already voted.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    context.user_data["voting_answers"] = {}
    await ask_question(query, "q1")

# ==========================
# ASK QUESTION
# ==========================

async def ask_question(query, q_key):
    keyboard = [
        [InlineKeyboardButton(opt, callback_data=f"{q_key}|{opt}")]
        for opt in OPTIONS[q_key]
    ]
    await query.edit_message_text(
        QUESTIONS[q_key],
        reply_markup=InlineKeyboardMarkup(keyboard)
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
# RESULTS (ADMIN ONLY)
# ==========================

async def results(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    records = voting_sheet.get_all_records()

    summary = {q: {opt: 0 for opt in OPTIONS[q]} for q in QUESTIONS}

    for row in records:
        if row.get("Q1") in summary["q1"]:
            summary["q1"][row["Q1"]] += 1
        if row.get("Q2") in summary["q2"]:
            summary["q2"][row["Q2"]] += 1
        if row.get("Q3") in summary["q3"]:
            summary["q3"][row["Q3"]] += 1
        if row.get("Q4") in summary["q4"]:
            summary["q4"][row["Q4"]] += 1

    message = "📊 VOTING SUMMARY\n\n"

    for q in QUESTIONS:
        message += f"{q.upper()}:\n"
        for opt in OPTIONS[q]:
            message += f"{opt}: {summary[q][opt]}\n"
        message += "\n"

    message += "👥 WHO VOTED:\n\n"

    for row in records:
        message += f"{row['Name']}\n"
        message += f"  q1: {row.get('Q1')}\n"
        message += f"  q2: {row.get('Q2')}\n"
        message += f"  q3: {row.get('Q3')}\n"
        message += f"  q4: {row.get('Q4')}\n\n"

    await update.message.reply_text(message)
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
# REMINDER
# ==========================

async def reminder(context: ContextTypes.DEFAULT_TYPE):
    for admin in ADMIN_IDS:
        await context.bot.send_message(
            chat_id=admin,
            text="Reminder: Voting is ongoing."
        )
# --------------------
# GOOGLE SHEETS SETUP
# --------------------
scope = ["https://spreadsheets.google.com/feeds",
         "https://www.googleapis.com/auth/drive"]

# Replace this path with Render secret file path
creds = ServiceAccountCredentials.from_json_keyfile_name("/etc/secrets/credentials.json", scope)
gs_client = gspread.authorize(creds)
prevote_sheet = gs_client.open("AGHAI_PreVoting_Records").worksheet("pre_voting_registration")
voting_sheet = gs_client.open("AGHAI_PreVoting_Records").worksheet("voting_records")
# --------------------
# CONVERSATION STATES
# --------------------
FULL_NAME, ADDRESS, MOBILE, EMAIL, MEMBERSHIP_STATUS, ATTENDANCE, NOMINATION_DECISION, NOMINEE_NAMES, DECLARATION = range(9)

# --------------------
# HELPER
# --------------------
def has_submitted_prevote(user_id: int):
    records = prevote_sheet.get_all_records()
    for row in records:
        if str(row.get("Telegram ID")) == str(user_id):
            return True
    return False

def has_voted(user_id: int):
    records = voting_sheet.get_all_records()
    for row in records:
        if str(row.get("Telegram ID")) == str(user_id):
            return True
    return False


def clear_user_vote(user_id: int):
    records = voting_sheet.get_all_records()
    for idx, row in enumerate(records, start=2):  # row 2 because header is row 1
        if str(row.get("Telegram ID")) == str(user_id):
            voting_sheet.delete_rows(idx)
            return
# --------------------
# /prevote START
# --------------------
async def prevote_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if has_submitted_prevote(user_id):
        keyboard = [[InlineKeyboardButton("🏠 Back to Menu", callback_data="menu")]]
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.message.edit_text(
                "⚠️ You have already submitted your Pre-Voting Registration.",
                reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            "⚠️ You have already submitted your Pre-Voting Registration.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    return ConversationHandler.END

# --------------------
# CONVERSATION HANDLERS
# --------------------
async def prevote_full_name(update, context):
    context.user_data['full_name'] = update.message.text
    await update.message.reply_text("Enter your Lot Number / Street Address:")
    return ADDRESS

async def prevote_address(update, context):
    context.user_data['address'] = update.message.text
    await update.message.reply_text("Enter your Contact Mobile Number:")
    return MOBILE

async def prevote_mobile(update, context):
    context.user_data['mobile'] = update.message.text
    await update.message.reply_text("Enter your Email Address:")
    return EMAIL

async def prevote_email(update, context):
    context.user_data['email'] = update.message.text
    keyboard = [
        [InlineKeyboardButton("Registered Owner", callback_data="Registered Owner")],
        [InlineKeyboardButton("Authorized Assignee", callback_data="Authorized Assignee")]
    ]
    await update.message.reply_text("Select your Membership Status:", reply_markup=InlineKeyboardMarkup(keyboard))
    return MEMBERSHIP_STATUS

async def prevote_membership_status(update, context):
    query = update.callback_query
    await query.answer()
    context.user_data['membership_status'] = query.data
    keyboard = [
        [InlineKeyboardButton("Yes, I will attend personally", callback_data="Yes")],
        [InlineKeyboardButton("I cannot attend but will appoint a proxy", callback_data="Proxy")],
        [InlineKeyboardButton("Undecided", callback_data="Undecided")]
    ]
    await query.edit_message_text("Will you attend the Special Membership Meeting?", reply_markup=InlineKeyboardMarkup(keyboard))
    return ATTENDANCE

async def prevote_attendance(update, context):
    query = update.callback_query
    await query.answer()
    context.user_data['attendance'] = query.data
    keyboard = [
        [InlineKeyboardButton("Yes", callback_data="Yes")],
        [InlineKeyboardButton("No", callback_data="No")]
    ]
    await query.edit_message_text("Do you wish to nominate members for COMELEC?", reply_markup=InlineKeyboardMarkup(keyboard))
    return NOMINATION_DECISION

async def prevote_nomination_decision(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data.strip().lower()  # normalize

    if data == "no":
        context.user_data['nomination_yes_no'] = "No"
        context.user_data['nominee_names'] = ""
        return await prevote_declaration_prompt(update, context)

    # If Yes
    context.user_data['nomination_yes_no'] = "Yes"
    official_names = ["Manny de Leon", "Annabelle Yong", "Conrad Alampay", "Ernie Manansala", "Elvie Guzman"]
    await query.edit_message_text(
        f"You may nominate any of the following:\n{', '.join(official_names)}\n\n"
        "You may also enter additional nominee(s). Enter name(s), separated by commas if multiple:"
    )
    return NOMINEE_NAMES

async def prevote_nominee_names(update, context):
    context.user_data['nominee_names'] = update.message.text
    return await prevote_declaration_prompt(update, context)

async def prevote_declaration_prompt(update, context):
    keyboard = [[InlineKeyboardButton("I Agree and Confirm", callback_data="Agree")]]
    await update.message.reply_text(
        "“I certify that I am a Member/Assignee in good standing of AGHAI and that the above information is true and correct.”",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return DECLARATION

async def prevote_declaration(update, context):
    query = update.callback_query
    await query.answer()
    context.user_data['declaration_confirmed'] = "YES"
    user_id = update.effective_user.id

    prevote_sheet.append_row([
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        user_id,
        context.user_data['full_name'],
        context.user_data['address'],
        context.user_data['mobile'],
        context.user_data['email'],
        context.user_data['membership_status'],
        context.user_data['attendance'],
        context.user_data.get('nomination_yes_no', "No"),
        context.user_data.get('nominee_names', ""),
        context.user_data['declaration_confirmed']
    ])

    # Show success message with "Back to Menu" button
    keyboard = [[InlineKeyboardButton("🏠 Back to Menu", callback_data="menu")]]
    await query.edit_message_text(
        "✅ Submission Successful!\nThank you for completing your Pre-Voting Registration.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ConversationHandler.END

# --------------------
# CONVERSATION HANDLER
# --------------------
prevote_conv = ConversationHandler(
    entry_points=[
        CommandHandler('prevote', prevote_start),
        CallbackQueryHandler(prevote_start, pattern="^prevote$")
    ],
    states={
        FULL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, prevote_full_name)],
        ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, prevote_address)],
        MOBILE: [MessageHandler(filters.TEXT & ~filters.COMMAND, prevote_mobile)],
        EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, prevote_email)],
        MEMBERSHIP_STATUS: [CallbackQueryHandler(prevote_membership_status)],
        ATTENDANCE: [CallbackQueryHandler(prevote_attendance)],
        NOMINATION_DECISION: [CallbackQueryHandler(prevote_nomination_decision)],
        NOMINEE_NAMES: [MessageHandler(filters.TEXT & ~filters.COMMAND, prevote_nominee_names)],
        DECLARATION: [CallbackQueryHandler(prevote_declaration)]
    },
    fallbacks=[CommandHandler('cancel', lambda u,c: ConversationHandler.END)]
)

# ==========================
# MAIN
# ==========================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("results", results))
    app.add_handler(CommandHandler("openvote", open_vote))
    app.add_handler(CommandHandler("closevote", close_vote))
    app.add_handler(CommandHandler("clearvotes", clear_votes))
    app.add_handler(CommandHandler("getid", get_id))
    app.add_handler(prevote_conv)
    app.add_handler(CallbackQueryHandler(button_handler))

    app.job_queue.run_repeating(reminder, interval=REMINDER_INTERVAL_SECONDS)

    # Web server for Render
    import threading
    from flask import Flask

    def run_web():
        web_app = Flask(__name__)

        @web_app.route("/")
        def home():
            return "Aghai Elections Bot is running!"

        port = int(os.environ.get("PORT", 10000))
        web_app.run(host="0.0.0.0", port=port)

    threading.Thread(target=run_web).start()

    print("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()















