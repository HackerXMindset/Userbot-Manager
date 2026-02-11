-- Migration 066: Add gain alert template storage
-- Created: 2025-02-21

ALTER TABLE monitored_sources
    ADD COLUMN IF NOT EXISTS template_text TEXT;

INSERT INTO settings (key, value)
VALUES (
    'gain_alert_template',
    to_jsonb($${gain_emoji} ${token_symbol} {multiplier} | 💹From {first_market_cap} ↗️ {current_market_cap} within {elapsed_time}
🔗 CA: {address}
⚠️ Gain alerts are in beta and may be inaccurate.$$::text)
)
ON CONFLICT (key) DO NOTHING;
