# Security

This is a local experimental application, not a public multi-user service. Keep its dashboard and model worker bound to localhost. Never publish `.env`, API keys, logs, or private match records.

If a credential is exposed, revoke it with its provider and replace it locally; deleting it from the latest commit is insufficient.

Do not include credentials or exploit details in public issues. Use the hosting platform's private vulnerability reporting when enabled by the maintainer.
