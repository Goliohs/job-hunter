#!/usr/bin/env bash
# Job Hunter Bot - Setup Script
# Run this to configure the bot for production

set -e

echo "🚀 Job Hunter Bot - Production Setup"
echo "===================================="
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "Creating .env from template..."
    cp .env.example .env
    echo "Created .env from template"
    echo "⚠️  Please edit .env with your credentials before continuing"
    exit 1
fi

# Load env
set -a
source .env
set +a

# Check required variables
check_var() {
    if [ -z "${!1}" ]; then
        echo "❌ Missing: $1"
        return 1
    else
        echo "✅ $1 configured"
        return 0
    fi
}

echo "Checking configuration..."
errors=0

check_var() {
    if [ -z "${!1}" ]; then
        echo "❌ Missing: $1"
        return 1
    else
        echo "✅ $1 configured"
        return 0
    fi
}

echo "Checking required variables..."
errors=0
check_var "NIM_API_KEY" || ((errors++))
check_var "SMTP_USER" || ((errors++))
check_var "SMTP_PASS" || ((errors++))
check_var "ALERT_TO_EMAILS" || ((errors++))

# Optional
check_var "TELEGRAM_BOT_TOKEN" || echo "⚠️  TELEGRAM_BOT_TOKEN not set (optional)"
check_var "TELEGRAM_CHAT_ID" || echo "⚠️  TELEGRAM_CHAT_ID not set (optional)"

if [ $errors -gt 0 ]; then
    echo ""
    echo "❌ $errors required variables missing. Edit .env and re-run."
    exit 1
fi

echo ""
echo "✅ All required variables configured!"

# Test email
echo ""
echo "Testing email notification..."
cd /home/Helios/job-hunter
source venv/bin/activate
python3 -c "
from alerts.email_notifier import EmailNotifier
notifier = EmailNotifier()
if notifier.is_configured():
    print('Email configured - sending test...')
    notifier.send_alert('Test', 'Test from Job Hunter Bot')
    print('✅ Test email sent!')
else:
    print('⚠️  Email not configured')
"

# Test Telegram if configured
if [ -n "\$TELEGRAM_BOT_TOKEN" ] && [ -n "\$TELEGRAM_CHAT_ID" ]; then
    echo "Testing Telegram..."
    python3 -c "
from alerts.telegram import send_telegram
import os
send_telegram(os.getenv('TELEGRAM_BOT_TOKEN'), os.getenv('TELEGRAM_CHAT_ID'), '🤖 Job Hunter Bot test message')
print('Telegram test sent')
"
else
    echo "⚠️  Telegram not configured"
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Add to crontab: (crontab -l; echo '0 8 * * * cd /home/Helios/job-hunter && ./run.sh') | crontab -"
echo "2. Or run manually: ./run.sh"
echo ""
echo "Dashboard: ./run.sh web (port 5001)"