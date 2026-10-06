from telegram import send_telegram_message


if __name__ == "__main__":
    message = (
        "✅ <b>Sarkari Naukri Bot Test Successful</b>\n\n"
        "Your Telegram bot is connected to the channel.\n"
        "Automatic government job alerts are ready to be enabled."
    )
    send_telegram_message(message)
