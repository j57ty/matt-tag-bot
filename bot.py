import logging
import os
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
)

import config
import database
from handlers.admin import (
    start_command,
    help_command,
    link_command,
    unlink_command,
    demote_command,
    tag_command,
    lookup_command,
    list_command,
    myinfo_command,
    handle_text_shortcuts,
    track_activity,
)

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class HealthCheckHandler(BaseHTTPRequestHandler):
    """Simple HTTP handler to satisfy Render's port check and allow Uptime pinging."""
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Bot is alive and running!")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress ping spam in console logs


def start_health_check_server():
    """Starts HTTP server if PORT environment variable is set (used by Render/Cloud hosts)."""
    port_str = os.environ.get("PORT")
    if port_str and port_str.isdigit():
        port = int(port_str)
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        logger.info("Health check HTTP server started on port %d", port)



async def error_handler(update, context):
    """Logs uncaught exceptions that happen during updates."""
    logger.error("Exception while handling an update:", exc_info=context.error)


def main():
    if not config.BOT_TOKEN or config.BOT_TOKEN == "your_bot_token_here":
        print("\n" + "=" * 60)
        print("❌ ERROR: BOT_TOKEN is missing or not set!")
        print("Please configure your BOT_TOKEN in the '.env' file.")
        print("Example:")
        print("  BOT_TOKEN=1234567890:ABCdefGhIJKlmNoPQRsTUVwxyZ")
        print("=" * 60 + "\n")
        sys.exit(1)

    # Initialize the database schema
    database.init_db()
    logger.info("Database initialized successfully at %s", config.DB_PATH)

    # Start dummy HTTP health check server if PORT is provided (Render compatibility)
    start_health_check_server()

    # Build the Telegram Bot Application
    app = ApplicationBuilder().token(config.BOT_TOKEN).build()

    # Track user activity in the group to auto-cache usernames and IDs (group 1 so it doesn't stop group 0)
    app.add_handler(
        MessageHandler(filters.ALL & (~filters.StatusUpdate.ALL), track_activity),
        group=1
    )

    # Register admin commands (group 0)
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("link", link_command))
    app.add_handler(CommandHandler("assign", link_command))  # Alias for link
    app.add_handler(CommandHandler("unlink", unlink_command))
    app.add_handler(CommandHandler("demote", demote_command))
    app.add_handler(CommandHandler("tag", tag_command))
    app.add_handler(CommandHandler("lookup", lookup_command))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(CommandHandler("myinfo", myinfo_command))

    # Catch text triggers like #tag or !tag
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text_shortcuts))

    # Register error handler
    app.add_error_handler(error_handler)

    logger.info("Starting Telegram Bot polling...")
    app.run_polling()


if __name__ == "__main__":
    main()
