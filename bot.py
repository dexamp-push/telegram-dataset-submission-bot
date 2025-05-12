import logging
import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler

# Google Sheets API
import gspread
from google.oauth2.service_account import Credentials

# Import the google_search tool
from google_search import search as google_search

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Define states for the data collection conversation
GET_DATA = range(1)

# Define states for the search conversation
ASKING_FOR_SEARCH_QUERY, RECEIVING_SEARCH_QUERY = range(2)


# --- Google Sheets Setup ---
# Replace with the path to your service account credentials JSON file
# It's recommended to use environment variables or a secure method for credentials in production
GOOGLE_SHEETS_CREDENTIALS_FILE = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_FILE", "credentials.json")
# Replace with the name or ID of your Google Sheet
GOOGLE_SHEET_NAME = os.environ.get("GOOGLE_SHEET_NAME", "AI Training Dataset")
# Replace with the name of the specific worksheet (tab) you want to use
WORKSHEET_NAME = os.environ.get("WORKSHEET_NAME", "Sheet1")

try:
    # Authenticate with Google Sheets
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    credentials = Credentials.from_service_account_file(
        GOOGLE_SHEETS_CREDENTIALS_FILE, scopes=scopes)
    client = gspread.authorize(credentials)
    spreadsheet = client.open(GOOGLE_SHEET_NAME)
    worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
    logger.info("Successfully connected to Google Sheets.")
except Exception as e:
    logger.error(f"Error connecting to Google Sheets: {e}")
    worksheet = None # Set worksheet to None if connection fails

# --- Data Collection Command Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the data collection conversation and asks for the first piece of data."""
    user = update.effective_user
    await update.message.reply_html(
        f"Hi {user.mention_html()}! I'm a bot to help you collect data for your AI model."
        "Send me the data you want to add to the dataset. Type /cancel to stop at any time.",
    )

    # Example of an inline keyboard to guide input
    keyboard = [
        [
            InlineKeyboardButton("Submit Data Point", callback_data="submit_data"),
            InlineKeyboardButton("Cancel", callback_data="cancel_submission"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Please select an action:",
        reply_markup=reply_markup
    )

    return GET_DATA # Move to the GET_DATA state

async def get_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receives the data from the user and processes it."""
    user_data = context.user_data
    data_point = update.message.text

    if 'current_data' not in user_data:
        user_data['current_data'] = []

    user_data['current_data'].append(data_point)

    await update.message.reply_text("Received your data point. Add another one or use the buttons.")

    # You could offer more specific inline keyboard options here based on the data you expect
    keyboard = [
        [
            InlineKeyboardButton("Add More Data", callback_data="add_more_data"),
            InlineKeyboardButton("Finish Submission", callback_data="finish_submission"),
            InlineKeyboardButton("Cancel", callback_data="cancel_submission"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "What would you like to do next?",
        reply_markup=reply_markup
    )

    return GET_DATA # Stay in the GET_DATA state to receive more input

async def data_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles inline keyboard button presses for data collection."""
    query = update.callback_query
    await query.answer() # Acknowledge the button press

    user_data = context.user_data

    if query.data == 'submit_data' or query.data == 'add_more_data':
        await query.edit_message_text(text="Okay, send me the data point.")
        return GET_DATA # Stay or move to GET_DATA state

    elif query.data == 'finish_submission':
        if 'current_data' in user_data and user_data['current_data']:
            if worksheet:
                try:
                    # Append the collected data to the Google Sheet
                    worksheet.append_row(user_data['current_data'])
                    await query.edit_message_text(text="Data successfully added to the dataset!")
                    logger.info(f"Data added to sheet: {user_data['current_data']}")
                except Exception as e:
                    await query.edit_message_text(text="Sorry, there was an error adding data to the sheet.")
                    logger.error(f"Error appending data to Google Sheet: {e}")
            else:
                 await query.edit_message_text(text="Sorry, could not connect to Google Sheets. Data not saved.")

            user_data.pop('current_data', None) # Clear the collected data
        else:
            await query.edit_message_text(text="No data collected yet.")

        return ConversationHandler.END # End the conversation

    elif query.data == 'cancel_submission':
        user_data.pop('current_data', None) # Clear any collected data
        await query.edit_message_text(text="Data submission cancelled.")
        return ConversationHandler.END # End the conversation

async def cancel_data_collection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels and ends the data collection conversation."""
    user_data = context.user_data
    user_data.pop('current_data', None) # Clear any collected data
    await update.message.reply_text(
        "Data submission cancelled. Bye!"
    )
    return ConversationHandler.END # End the conversation

# --- Search Command Handlers ---

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the search conversation and asks for the query."""
    await update.message.reply_text("What would you like to search for?")
    return RECEIVING_SEARCH_QUERY # Move to the state to receive the query

async def perform_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receives the search query and performs the search."""
    search_query = update.message.text
    await update.message.reply_text(f"Searching for '{search_query}'...")

    try:
        # Use the google_search tool
        search_results = google_search(queries=[search_query])

        if search_results and search_results[0].results:
            reply_text = "Search Results:\n\n"
            for result in search_results[0].results:
                reply_text += f"Title: {result.source_title or 'N/A'}\n"
                reply_text += f"URL: {result.url or 'N/A'}\n"
                reply_text += f"Snippet: {result.snippet or 'N/A'}\n\n"
        else:
            reply_text = "No search results found."

        await update.message.reply_text(reply_text)

    except Exception as e:
        logger.error(f"Error during search: {e}")
        await update.message.reply_text("Sorry, an error occurred while performing the search.")

    return ConversationHandler.END # End the search conversation

async def cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels and ends the search conversation."""
    await update.message.reply_text("Search cancelled.")
    return ConversationHandler.END # End the search conversation


def main() -> None:
    """Runs the bot."""
    # Replace with your actual bot token
    # It's recommended to use environment variables for the token in production
    TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN")
    if TOKEN == "YOUR_BOT_TOKEN":
        logger.error("Please replace 'YOUR_BOT_TOKEN' with your actual Telegram bot token or set the TELEGRAM_BOT_TOKEN environment variable.")
        return

    application = Application.builder().token(TOKEN).build()

    # Create the data collection conversation handler
    data_collection_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            GET_DATA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_data),
                CallbackQueryHandler(data_button), # Handle button presses in this state
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_data_collection)],
    )

    # Create the search conversation handler
    search_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("search", search_command)],
        states={
            RECEIVING_SEARCH_QUERY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, perform_search),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_search)],
    )


    application.add_handler(data_collection_conv_handler)
    application.add_handler(search_conv_handler)

    # Run the bot until the user presses Ctrl-C
    application.run_polling(poll_interval=3)

if __name__ == "__main__":
    main()
