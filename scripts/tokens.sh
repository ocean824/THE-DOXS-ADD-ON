#!/bin/bash
# usage: source /app/scripts/tokens.sh  -> sets API, TOK (owner), TTOK (team), CTOK (client), UID_, CID, TX
API=$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d= -f2)
PW=$(grep INITIAL_OWNER_PASSWORD /app/backend/.env | cut -d= -f2)
login(){ curl -s -X POST $API/api/auth/login -H 'Content-Type: application/json' -d "{\"email\":\"$1\",\"password\":\"$2\",\"client\":\"desktop\"}" | python3 -c "import sys,json;print(json.load(sys.stdin).get('access_token',''))"; }
TOK=$(login xcyclone8@outlook.com "$PW")
TTOK=$(login vault.tester@example.com 'VaultTester#2026')
CTOK=$(login portal.client@example.com 'PortalClient#2026')
UID_=$(curl -s $API/api/users -H "Authorization: Bearer $TOK" | python3 -c "import sys,json;print([u for u in json.load(sys.stdin) if u['email']=='vault.tester@example.com'][0]['id'])")
CID=$(curl -s $API/api/users -H "Authorization: Bearer $TOK" | python3 -c "import sys,json;print([u for u in json.load(sys.stdin) if u['email']=='portal.client@example.com'][0]['id'])")
TX=$(curl -s $API/api/transactions -H "Authorization: Bearer $TOK" | python3 -c "import sys,json;d=json.load(sys.stdin);print([x for x in d if x['property_type']=='Condominium'][0]['id'])")
export API TOK TTOK CTOK UID_ CID TX
