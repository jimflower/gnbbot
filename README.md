# GNB Assist – Teams Bot

Claude-powered AI assistant for Microsoft Teams. Each user signs in with their own Microsoft 365 account to access email and calendar features.

## Deploy to VPS

### Prerequisites

- Ubuntu 22.04+ VPS (Hostinger or similar)
- Domain pointed at your VPS (e.g. `assist.yourdomain.com`)
- Azure App Registration (single-tenant, see below)
- Anthropic API key

### Install

```bash
git clone https://github.com/jamesrose/gnbbot.git
cd gnbbot
sudo bash setup.sh
```

The setup script will prompt for all required values, install dependencies, configure HTTPS via Caddy, and start the bot as a systemd service.

### After setup

Complete these steps in Azure Portal:

1. **Azure Bot** → Configuration → Messaging endpoint:
   ```
   https://your-domain.com/api/messages
   ```

2. **App Registration** → Authentication → Redirect URIs → Add:
   ```
   https://your-domain.com/auth/callback
   ```

3. **Upload Teams app** → Teams Admin Centre or sideload the generated `gnbbot-teams.zip`

---

## Azure App Registration setup

1. Azure Portal → **App registrations** → New registration
2. Name: `GNB Assist Bot`
3. Supported account types: **Single tenant**
4. Redirect URI: `https://your-domain.com/auth/callback` (Web)
5. After creation, go to **API permissions** → Add:
   - `Mail.Read` (Delegated)
   - `Calendars.Read` (Delegated)
   - `Tasks.ReadWrite` (Delegated)
   - `User.Read` (Delegated)
6. **Certificates & secrets** → New client secret → copy the value
7. Create an **Azure Bot** resource → link to this App Registration

---

## What users can do

| Say | What happens |
|-----|-------------|
| `sign in` | Connect their Microsoft 365 account |
| `sign out` | Disconnect their account |
| `what emails do I have?` | Summarises their recent inbox |
| `what's on my calendar today?` | Lists today's meetings |
| `absences` | Shows today's absence emails (if shared mailbox configured) |
| Anything else | Claude answers with GNB context |

---

## Manage the service

```bash
# View logs
journalctl -u gnbbot -f

# Restart
sudo systemctl restart gnbbot

# Status
sudo systemctl status gnbbot
```

## Update

```bash
cd /path/to/gnbbot
git pull
sudo systemctl restart gnbbot
```
