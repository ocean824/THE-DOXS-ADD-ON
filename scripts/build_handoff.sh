#!/bin/bash
# Builds /app/handoff/dox-workspace-handoff.zip (source bundle without node_modules, build, .env, caches)
set -e
cd /app
rm -f handoff/dox-workspace-handoff.zip
zip -qr handoff/dox-workspace-handoff.zip \
  backend/*.py backend/requirements.txt backend/pytest.ini backend/tests/*.py \
  frontend/src frontend/public frontend/package.json frontend/craco.config.js frontend/tailwind.config.js frontend/postcss.config.js frontend/components.json frontend/jsconfig.json \
  docs cli scripts/tokens.sh design_guidelines.json README.md \
  handoff/HANDOFF.md handoff/AUTH-ROLE-MAPPING.md handoff/MERGE-PROMPT.md handoff/env.example handoff/openapi.json \
  -x '*/__pycache__/*' -x '*.pyc'
ls -la handoff/dox-workspace-handoff.zip
