# Checkout API Incident Runbook

For elevated 5xx errors, first verify service status and incident scope. A service restart is a side effect and requires explicit human approval. For a restart, the `restart_service.reason` argument is the record of the incident reason for that restart; do not create a separate incident note unless the user explicitly asks to add one. After a successful restart, verify service status again before reporting completion.
