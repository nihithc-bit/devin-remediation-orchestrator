#!/usr/bin/env bash
# Send a signed test webhook to the local /webhooks/github endpoint.
# Simulates a GitHub "issues.labeled" event.
#
# Usage:
#   ./scripts/send_test_webhook.sh [issue_number] [issue_title]
#
# Environment:
#   GITHUB_WEBHOOK_SECRET  (required — must match what's in .env)
#   API_URL                (default: http://localhost:8000)

set -euo pipefail

ISSUE_NUMBER="${1:-1}"
ISSUE_TITLE="${2:-fix(lint): replace == False with ~ in superset/daos/base.py}"
SECRET="${GITHUB_WEBHOOK_SECRET:?Error: GITHUB_WEBHOOK_SECRET must be set}"
API_URL="${API_URL:-http://localhost:8000}"
DELIVERY_ID="test-$(date +%s)-$(shuf -i 1000-9999 -n 1)"

PAYLOAD=$(cat <<EOF
{
  "action": "labeled",
  "issue": {
    "number": ${ISSUE_NUMBER},
    "title": "${ISSUE_TITLE}",
    "body": "This is a test issue body for local simulation.",
    "html_url": "https://github.com/${GITHUB_OWNER:-your-org}/${GITHUB_REPO:-superset}/issues/${ISSUE_NUMBER}",
    "labels": [{"name": "devin:auto-remediate"}]
  },
  "label": {"name": "devin:auto-remediate"},
  "repository": {"full_name": "${GITHUB_OWNER:-your-org}/${GITHUB_REPO:-superset}"},
  "sender": {"login": "test-user"}
}
EOF
)

# Compute HMAC-SHA256 signature
SIGNATURE="sha256=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $2}')"

echo "Sending webhook to ${API_URL}/webhooks/github"
echo "  Delivery-ID: ${DELIVERY_ID}"
echo "  Signature:   ${SIGNATURE}"

curl -sf \
  -X POST "${API_URL}/webhooks/github" \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: issues" \
  -H "X-GitHub-Delivery: ${DELIVERY_ID}" \
  -H "X-Hub-Signature-256: ${SIGNATURE}" \
  -d "$PAYLOAD" | python3 -m json.tool

echo ""
echo "✅ Webhook sent. Check FastAPI logs and GET ${API_URL}/runs for the new run."
