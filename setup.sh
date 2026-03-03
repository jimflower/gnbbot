#!/usr/bin/env bash
# GNB Assist – One-shot setup script
# Run once after cloning: sudo bash setup.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_USER="${SUDO_USER:-$(whoami)}"

# ── Helpers ───────────────────────────────────────────────────────────────────
ask() {
    local prompt="$1"
    local default="${2:-}"
    local secret="${3:-}"
    local value
    local display_prompt

    if [[ -n "$default" ]]; then
        display_prompt="${YELLOW}?${NC} $prompt [${default}]: "
    else
        display_prompt="${YELLOW}?${NC} $prompt: "
    fi

    if [[ "$secret" == "secret" ]]; then
        read -s -rp "$(echo -e "$display_prompt")" value
        echo ""
    else
        read -rp "$(echo -e "$display_prompt")" value
    fi

    echo "${value:-$default}"
}

step() { echo -e "\n${BOLD}$1${NC}"; }
ok()   { echo -e "${GREEN}✓ $1${NC}"; }
info() { echo -e "  $1"; }

# ── Root check ────────────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}Please run as root: sudo bash setup.sh${NC}"
    exit 1
fi

echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}  GNB Assist – VPS Setup${NC}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "This will install GNB Assist and configure it to start automatically."
echo "You'll need your Azure App Registration credentials and Anthropic API key."
echo ""

# ── Collect configuration ─────────────────────────────────────────────────────
step "Azure App Registration"
AZURE_TENANT_ID=$(ask "Tenant ID")
AZURE_CLIENT_ID=$(ask "Client ID")
AZURE_CLIENT_SECRET=$(ask "Client Secret" "" secret)

step "Bot settings"
BOT_NAME=$(ask "Bot display name" "GNB Assist")
BASE_URL=$(ask "Public HTTPS URL (e.g. https://assist.yourdomain.com)")

step "Anthropic API"
ANTHROPIC_API_KEY=$(ask "API key" "" secret)
CLAUDE_MODEL=$(ask "Claude model" "claude-sonnet-4-6")

step "Microsoft 365 (optional)"
echo "  The shared mailbox is used for the 'absences' command."
echo "  Leave blank to skip this feature."
SHARED_MAILBOX=$(ask "Shared mailbox address" "")

step "System prompt (optional)"
DEFAULT_PROMPT="You are GNB Assist, an AI assistant for GNB Energy. Be professional but approachable. Keep responses concise and practical. You are running inside Microsoft Teams."
echo "  Press Enter to use the default, or type a custom prompt."
SYSTEM_PROMPT=$(ask "System prompt" "$DEFAULT_PROMPT")

# ── Write .env ────────────────────────────────────────────────────────────────
step "Writing configuration"
mkdir -p "$INSTALL_DIR/data"

cat > "$INSTALL_DIR/.env" <<EOF
AZURE_TENANT_ID=${AZURE_TENANT_ID}
AZURE_CLIENT_ID=${AZURE_CLIENT_ID}
AZURE_CLIENT_SECRET=${AZURE_CLIENT_SECRET}
BOT_NAME=${BOT_NAME}
BOT_PORT=3978
BASE_URL=${BASE_URL}
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
CLAUDE_MODEL=${CLAUDE_MODEL}
SHARED_MAILBOX=${SHARED_MAILBOX}
DATA_DIR=${INSTALL_DIR}/data
SYSTEM_PROMPT=${SYSTEM_PROMPT}
EOF

chmod 600 "$INSTALL_DIR/.env"
ok ".env written (permissions: 600)"

# ── System packages ───────────────────────────────────────────────────────────
step "Installing system packages"
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip curl zip

# Install Caddy
if ! command -v caddy &>/dev/null; then
    apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        | tee /etc/apt/sources.list.d/caddy-stable.list > /dev/null
    apt-get update -qq
    apt-get install -y -qq caddy
fi
ok "System packages ready"

# ── Python environment ────────────────────────────────────────────────────────
step "Setting up Python environment"
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install -q --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt"
ok "Python venv ready"

# ── Caddy ─────────────────────────────────────────────────────────────────────
step "Configuring Caddy (HTTPS)"
DOMAIN="${BASE_URL#https://}"
DOMAIN="${DOMAIN#http://}"
DOMAIN="${DOMAIN%%/*}"

cat > /etc/caddy/Caddyfile <<EOF
${DOMAIN} {
    reverse_proxy localhost:3978
}
EOF

systemctl enable caddy
systemctl reload caddy 2>/dev/null || systemctl restart caddy
ok "Caddy configured for ${DOMAIN}"

# ── Generate Teams app icons ──────────────────────────────────────────────────
step "Generating Teams app package"
python3 << 'PYEOF'
import struct, zlib, os

def make_png(width, height, r, g, b):
    def chunk(name, data):
        c = struct.pack('>I', len(data)) + name + data
        return c + struct.pack('>I', zlib.crc32(name + data) & 0xffffffff)
    raw = b''
    for _ in range(height):
        raw += b'\x00' + bytes([r, g, b] * width)
    return (
        b'\x89PNG\r\n\x1a\n'
        + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
        + chunk(b'IDAT', zlib.compress(raw))
        + chunk(b'IEND', b'')
    )

os.makedirs('teams-app', exist_ok=True)
with open('teams-app/color.png',   'wb') as f: f.write(make_png(192, 192, 0, 66, 130))
with open('teams-app/outline.png', 'wb') as f: f.write(make_png(32,  32,  255, 255, 255))
PYEOF

# Fill manifest template
sed -e "s|{{CLIENT_ID}}|${AZURE_CLIENT_ID}|g" \
    -e "s|{{BOT_NAME}}|${BOT_NAME}|g" \
    -e "s|{{BASE_URL}}|${BASE_URL}|g" \
    -e "s|{{DOMAIN}}|${DOMAIN}|g" \
    "$INSTALL_DIR/teams-app/manifest.template.json" \
    > "$INSTALL_DIR/teams-app/manifest.json"

# Create zip
(cd "$INSTALL_DIR/teams-app" && zip -qj "$INSTALL_DIR/gnbbot-teams.zip" manifest.json color.png outline.png)
ok "Teams app package: gnbbot-teams.zip"

# ── systemd service ───────────────────────────────────────────────────────────
step "Installing systemd service"
cat > /etc/systemd/system/gnbbot.service <<EOF
[Unit]
Description=GNB Assist Teams Bot
After=network.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=${INSTALL_DIR}/.env
ExecStart=${INSTALL_DIR}/venv/bin/python ${INSTALL_DIR}/bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable gnbbot
systemctl restart gnbbot
ok "gnbbot service installed and started"

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}${BOLD}  Setup complete!${NC}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  Health check:  ${BOLD}${BASE_URL}/health${NC}"
echo ""
echo -e "${BOLD}Now complete these steps in Azure Portal:${NC}"
echo ""
echo -e "  1. ${BOLD}Azure Bot${NC} → Configuration → Messaging endpoint:"
echo -e "     ${GREEN}${BASE_URL}/api/messages${NC}"
echo ""
echo -e "  2. ${BOLD}App Registration${NC} → Authentication → Redirect URIs → Add:"
echo -e "     ${GREEN}${BASE_URL}/auth/callback${NC}"
echo ""
echo -e "  3. ${BOLD}Upload Teams app${NC} → Teams Admin Centre or sideload:"
echo -e "     ${GREEN}${INSTALL_DIR}/gnbbot-teams.zip${NC}"
echo ""
echo -e "  Logs:  ${BOLD}journalctl -u gnbbot -f${NC}"
echo ""
