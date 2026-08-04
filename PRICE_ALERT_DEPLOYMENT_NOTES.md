# Price Alert Deployment Notes

Operational reference for the live deployment. No secret values here.

## Current deployment

| | |
| --- | --- |
| Host | DigitalOcean VPS |
| Service | `jayce-bot` (systemd) |
| Working directory | `/opt/jayce` |
| Entry point | `bot.py` (registers handlers via `price_alert_telegram.py`) |
| Alert database | `/opt/jayce/data/jayce_alerts.db` |
| Telegram topic ID | `6960` (Price Alerts topic in WizTheoryLabs) |
| Poll interval | 5 seconds |
| Per-user active cap | 10 (admins exempt) |

Environment comes from `/opt/jayce/.env` via `EnvironmentFile=` in the
systemd unit. Nothing calls `load_dotenv()`, so variables set only in a
shell will not reach the service — they must be in `.env`.

## Commands

| Command | Who |
| --- | --- |
| `/alert <CA> <price>` | any member, max 10 active each |
| `/alerts` | any member |
| `/alerthistory` | any member |
| `/deletealert <ID>` | creator, or an admin |
| `/clearalerts` | admins only |

Command replies appear in the topic where the command was typed.
Triggered alerts always publish to the Price Alerts topic.

## Trigger fallback

Triggered alerts are sent to `JACE_PRICE_ALERT_TOPIC_ID`. If that topic is
unreachable — deleted, closed, or the ID is wrong — the alert is sent to the
group's main area instead and the failure is logged. Losing the topic never
means losing the alert.

If BOTH destinations fail, the alert stays `active`, its delivery claim is
released, and it retries on the next cycle. It is never marked delivered
unless a send actually succeeded.

If `JACE_PRICE_ALERT_TOPIC_ID` is unset or not a number, everything behaves
as it did before topics existed: all messages go to the main area.

## Restart

    systemctl restart jayce-bot
    sleep 12
    systemctl is-active jayce-bot
    grep "PRICE_ALERT" /opt/jayce/logs/bot.log | tail -3

Expect `[PRICE_ALERT] worker started`. If only `handlers registered` appears,
the worker did NOT start — check that `register_price_alerts(application)` is
called AFTER `application.post_init` is assigned in `bot.py`.

## Verifying a deploy

Confirm the file actually landed and the process can see its config:

    grep -c "_send_trigger" /opt/jayce/price_alert_telegram.py
    PID=$(pgrep -f "venv/bin/python3 /opt/jayce/bot.py" | head -1)
    tr '\0' '\n' < /proc/$PID/environ | grep JACE_PRICE_ALERT_TOPIC_ID

A browser that saves `file (1).py` instead of overwriting has caused a stale
upload before. Verify content, not just that a file exists.

## Rollback

Timestamped `.bak.*` copies sit next to each file that was edited. These are
gitignored and exist only on the VPS.

    cd /opt/jayce
    cp price_alert_telegram.py.bak.pre-topic price_alert_telegram.py
    cp .env.bak.pre-topic .env
    systemctl restart jayce-bot

To disable the feature entirely without touching code, set
`JACE_PRICE_ALERTS_ENABLED=false` in `.env` and restart.

## Known limitations

- Price Alerts is a forum topic, not a separate group, so Jayce's other
  commands also work there. Alert routing is controlled; command availability
  is not.
- Notification sounds are per-user and client-side. Each member sets their
  own; the bot cannot set or read them.
- Provider lookups are sequential, one per unique token per cycle. Many
  tokens means cycles longer than the poll interval.
- `/alerts` shows at most 20 entries while reporting the true total.
  Alerts beyond 20 are still monitored and still trigger.
