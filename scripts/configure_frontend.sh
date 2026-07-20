#!/usr/bin/env bash
set -euo pipefail

: "${API_BASE_URL:?API_BASE_URL is required, e.g. https://your-api.onrender.com}"
: "${PUBLIC_HTML_DIR:?PUBLIC_HTML_DIR is required, e.g. /var/www/vetector/public_html}"

CONFIG_FILE="$PUBLIC_HTML_DIR/js/config.js"
mkdir -p "$(dirname "$CONFIG_FILE")"

cat > "$CONFIG_FILE" <<EOF
// vet.ector generated production config
window.API_BASE_URL_DEFAULT = '$API_BASE_URL';
window.VECTOR_TERRITORIAL_BACKEND_ENABLED = true;
window.VECTOR_TERRITORIAL_BACKEND_EMPTY_FALLBACK = true;
window.VECTOR_TERRITORIAL_ERROR_FALLBACK = true;
window.VECTOR_PUBLIC_DEMO_MODE = true;
EOF

echo "[OK] wrote $CONFIG_FILE"
