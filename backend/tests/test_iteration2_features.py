"""Iteration 2 backend tests: knowledge vault, grants, Hermes knowledge, AI knowledge template,
client uploads, meetings calendar. Uses seeded accounts in /app/memory/test_credentials.md.
"""
import base64
import io
import json
import os
import secrets
import zipfile
from datetime import datetime

import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env", override=False)
load_dotenv("/app/backend/.env", override=False)

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
OWNER_EMAIL = os.environ["INITIAL_OWNER_EMAIL"]
OWNER_PASSWORD = os.environ["INITIAL_OWNER_PASSWORD"]
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

TEAM_EMAIL = "vault.tester@example.com"
TEAM_PASSWORD = "VaultTester#2026"
CLIENT_EMAIL = "portal.client@example.com"
CLIENT_PASSWORD = "PortalClient#2026"


# ---------- fixtures ----------
@pytest.fixture(scope="session")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _login(api, email, password):
    r = api.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password, "client": "desktop"})
    assert r.status_code == 200, r.text
    return r.json()


def _h(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def owner(api):
    return _login(api, OWNER_EMAIL, OWNER_PASSWORD)


@pytest.fixture(scope="session")
def team(api):
    return _login(api, TEAM_EMAIL, TEAM_PASSWORD)


@pytest.fixture(scope="session")
def client_user(api):
    return _login(api, CLIENT_EMAIL, CLIENT_PASSWORD)


@pytest.fixture(scope="session")
def mongo():
    c = MongoClient(MONGO_URL)
    try:
        yield c[DB_NAME]
    finally:
        c.close()


@pytest.fixture(scope="session")
def meridian_tx(api, owner):
    """Locate the '38 Meridian Avenue' Condominium tx."""
    r = api.get(f"{BASE_URL}/api/transactions", headers=_h(owner["access_token"]))
    assert r.status_code == 200
    for t in r.json():
        if "Meridian" in t.get("address", "") and t.get("property_type") == "Condominium":
            return t
    pytest.fail("Meridian Avenue tx not found")


@pytest.fixture(scope="session", autouse=True)
def _cleanup(mongo):
    """Delete anything we create under TEST_IT2 prefix, revoke Hermes key, reset knowledge rules."""
    yield
    mongo.knowledge_items.delete_many({"path": {"$regex": "^TEST_IT2/"}})
    mongo.knowledge_grants.delete_many({"note": {"$regex": "^TEST_IT2"}})
    mongo.meetings.delete_many({"title": {"$regex": "^TEST_IT2"}})
    mongo.documents.delete_many({"filename": {"$regex": "^TEST_IT2"}})
    mongo.service_keys.update_many({"service": "hermes"}, {"$set": {"active": False}})
    mongo.settings.update_one({"id": "workspace"}, {"$set": {"knowledge_rules.enabled": False}})


# helper: create a minimal valid .docx (empty-ish body) via zip
def _tiny_docx(text="Title Procedures"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr("_rels/.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr("word/document.xml", f'<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>')
    return buf.getvalue()


# ---------- knowledge sync ----------
class TestKnowledgeSync:
    def test_owner_sync_md_and_docx(self, api, owner):
        md_path = "TEST_IT2/notes/alpha.md"
        docx_path = "TEST_IT2/office/manual.docx"
        docx_b64 = base64.b64encode(_tiny_docx("TEST_IT2 docx body")).decode()
        payload = {
            "items": [
                {"path": md_path, "content": "# Alpha\nHello world"},
                {"path": docx_path, "content": docx_b64, "encoding": "base64"},
            ],
            "scope": "shared",
        }
        r = api.post(f"{BASE_URL}/api/knowledge/sync", headers=_h(owner["access_token"]), json=payload)
        assert r.status_code == 200, r.text
        assert r.json()["created"] >= 2 or (r.json()["created"] + r.json()["updated"]) >= 2

    def test_resync_same_content_unchanged(self, api, owner):
        payload = {
            "items": [{"path": "TEST_IT2/notes/alpha.md", "content": "# Alpha\nHello world"}],
            "scope": "shared",
        }
        r = api.post(f"{BASE_URL}/api/knowledge/sync", headers=_h(owner["access_token"]), json=payload)
        assert r.status_code == 200
        assert r.json()["unchanged"] == 1

    def test_resync_updated_content(self, api, owner):
        payload = {
            "items": [{"path": "TEST_IT2/notes/alpha.md", "content": "# Alpha\nHello world v2"}],
            "scope": "shared",
        }
        r = api.post(f"{BASE_URL}/api/knowledge/sync", headers=_h(owner["access_token"]), json=payload)
        assert r.status_code == 200
        assert r.json()["updated"] == 1

    def test_deleted_paths_removes(self, api, owner):
        payload = {
            "items": [{"path": "TEST_IT2/notes/to_delete.md", "content": "# Delete"}],
            "scope": "shared",
        }
        api.post(f"{BASE_URL}/api/knowledge/sync", headers=_h(owner["access_token"]), json=payload)
        r = api.post(f"{BASE_URL}/api/knowledge/sync", headers=_h(owner["access_token"]), json={
            "items": [{"path": "TEST_IT2/notes/alpha.md", "content": "# Alpha\nHello world v2"}],
            "scope": "shared",
            "deleted_paths": ["TEST_IT2/notes/to_delete.md"],
        })
        assert r.status_code == 200
        assert r.json()["deleted"] == 1

    def test_team_member_sync_forbidden(self, api, team):
        r = api.post(f"{BASE_URL}/api/knowledge/sync", headers=_h(team["access_token"]), json={
            "items": [{"path": "TEST_IT2/x.md", "content": "nope"}], "scope": "shared"
        })
        assert r.status_code == 403

    def test_owner_lists_all_items(self, api, owner):
        r = api.get(f"{BASE_URL}/api/knowledge/items", headers=_h(owner["access_token"]))
        assert r.status_code == 200
        assert any(it["path"].startswith("TEST_IT2/") for it in r.json())


# ---------- grants ----------
class TestGrants:
    @pytest.fixture(autouse=True)
    def _clear_team_grants(self, mongo, team):
        # Revoke all existing team grants so prefix tests are deterministic
        mongo.knowledge_grants.update_many({"user_id": team["user"]["id"], "active": True}, {"$set": {"active": False, "revoked_at": datetime.utcnow().isoformat()}})
        yield

    def test_grant_to_owner_rejected(self, api, owner):
        r = api.post(f"{BASE_URL}/api/knowledge/grants", headers=_h(owner["access_token"]),
                     json={"user_id": owner["user"]["id"], "scope": "shared", "path_prefix": "", "note": "TEST_IT2"})
        assert r.status_code == 422

    def test_project_grant_without_types_422(self, api, owner, team):
        r = api.post(f"{BASE_URL}/api/knowledge/grants", headers=_h(owner["access_token"]),
                     json={"user_id": team["user"]["id"], "scope": "project", "path_prefix": "", "project_types": [], "note": "TEST_IT2"})
        assert r.status_code == 422

    def test_shared_prefix_grant_restricts_access(self, api, owner, team):
        # Grant only TEST_IT2/notes prefix shared
        r = api.post(f"{BASE_URL}/api/knowledge/grants", headers=_h(owner["access_token"]),
                     json={"user_id": team["user"]["id"], "scope": "shared", "path_prefix": "TEST_IT2/notes", "note": "TEST_IT2 prefix"})
        assert r.status_code == 201, r.text
        grant_id = r.json()["id"]

        # team sees only items under prefix
        items = api.get(f"{BASE_URL}/api/knowledge/items", headers=_h(team["access_token"])).json()
        paths = [i["path"] for i in items]
        assert any(p.startswith("TEST_IT2/notes/") for p in paths)
        assert not any(p.startswith("TEST_IT2/office/") for p in paths)

        # non-permitted item 404
        all_items = api.get(f"{BASE_URL}/api/knowledge/items", headers=_h(owner["access_token"])).json()
        office = next(i for i in all_items if i["path"].startswith("TEST_IT2/office/"))
        r2 = api.get(f"{BASE_URL}/api/knowledge/items/{office['id']}", headers=_h(team["access_token"]))
        assert r2.status_code == 404

        # revoke
        rev = api.delete(f"{BASE_URL}/api/knowledge/grants/{grant_id}", headers=_h(owner["access_token"]))
        assert rev.status_code == 200
        items_after = api.get(f"{BASE_URL}/api/knowledge/items", headers=_h(team["access_token"])).json()
        assert not any(p["path"].startswith("TEST_IT2/") for p in items_after)


# ---------- Hermes knowledge grants ----------
class TestHermesKnowledge:
    @pytest.fixture(scope="class")
    def hermes_key(self, api, owner):
        r = api.post(f"{BASE_URL}/api/integrations/keys", headers=_h(owner["access_token"]), json={"service": "hermes"})
        assert r.status_code == 200
        data = r.json()
        assert "knowledge:grant" in data["scopes"]
        return data["key"]

    def test_hermes_without_token_and_rules_off_403(self, api, hermes_key, team):
        r = api.post(f"{BASE_URL}/api/integrations/hermes/knowledge/grants",
                     headers={"Authorization": f"Bearer {hermes_key}", "Content-Type": "application/json"},
                     json={"user_id": team["user"]["id"], "scope": "shared", "path_prefix": "",
                           "note": "TEST_IT2 noconf", "idempotency_key": f"idem-{secrets.token_hex(5)}"})
        assert r.status_code == 403

    def test_owner_confirmation_token_flow(self, api, owner, team, hermes_key):
        body = {"user_id": team["user"]["id"], "scope": "shared", "path_prefix": "TEST_IT2/office",
                "project_types": [], "note": "TEST_IT2 confirmed", "expires_at": None}
        confirm = api.post(f"{BASE_URL}/api/integrations/knowledge/confirmation",
                           headers=_h(owner["access_token"]), json=body)
        assert confirm.status_code == 200
        token = confirm.json()["confirmation_token"]

        idem = f"idem-{secrets.token_hex(6)}"
        payload = {**body, "confirmation_token": token, "idempotency_key": idem}
        r = api.post(f"{BASE_URL}/api/integrations/hermes/knowledge/grants",
                     headers={"Authorization": f"Bearer {hermes_key}", "Content-Type": "application/json"},
                     json=payload)
        assert r.status_code == 201, r.text
        assert r.json()["authority"] == "hermes_owner_confirmed"
        grant_id = r.json()["id"]

        # same idem same body -> same result
        r2 = api.post(f"{BASE_URL}/api/integrations/hermes/knowledge/grants",
                      headers={"Authorization": f"Bearer {hermes_key}", "Content-Type": "application/json"},
                      json=payload)
        assert r2.status_code == 201
        assert r2.json()["id"] == grant_id

        # same idem different body -> 409
        r3 = api.post(f"{BASE_URL}/api/integrations/hermes/knowledge/grants",
                      headers={"Authorization": f"Bearer {hermes_key}", "Content-Type": "application/json"},
                      json={**payload, "note": "TEST_IT2 changed"})
        assert r3.status_code == 409

        # token reuse with fresh idem -> 403 (used)
        r4 = api.post(f"{BASE_URL}/api/integrations/hermes/knowledge/grants",
                      headers={"Authorization": f"Bearer {hermes_key}", "Content-Type": "application/json"},
                      json={**body, "confirmation_token": token, "idempotency_key": f"idem-{secrets.token_hex(5)}"})
        assert r4.status_code == 403

        # cleanup
        api.delete(f"{BASE_URL}/api/knowledge/grants/{grant_id}", headers=_h(owner["access_token"]))

    def test_hermes_rule_grant(self, api, owner, team, hermes_key):
        # enable rules for TEAM_MEMBER project Condominium
        rules = {"enabled": True, "roles": ["TEAM_MEMBER"], "scopes": ["project"],
                 "project_types": ["Condominium"], "path_prefixes": []}
        put = api.put(f"{BASE_URL}/api/settings", headers=_h(owner["access_token"]),
                      json={"team_daily_limit": 30, "client_daily_limit": 10,
                            "autonomous_approvals": False, "autonomous_max_value": 500000,
                            "knowledge_rules": rules})
        assert put.status_code == 200, put.text

        # Condominium -> 201 hermes_rule
        body = {"user_id": team["user"]["id"], "scope": "project", "path_prefix": "",
                "project_types": ["Condominium"], "note": "TEST_IT2 rule", "expires_at": None,
                "idempotency_key": f"idem-{secrets.token_hex(6)}"}
        r = api.post(f"{BASE_URL}/api/integrations/hermes/knowledge/grants",
                     headers={"Authorization": f"Bearer {hermes_key}", "Content-Type": "application/json"},
                     json=body)
        assert r.status_code == 201, r.text
        assert r.json()["authority"] == "hermes_rule"
        api.delete(f"{BASE_URL}/api/knowledge/grants/{r.json()['id']}", headers=_h(owner["access_token"]))

        # Land -> 403 (not in rules.project_types)
        land = api.post(f"{BASE_URL}/api/integrations/hermes/knowledge/grants",
                        headers={"Authorization": f"Bearer {hermes_key}", "Content-Type": "application/json"},
                        json={**body, "project_types": ["Land"],
                              "idempotency_key": f"idem-{secrets.token_hex(6)}"})
        assert land.status_code == 403

        # turn off
        api.put(f"{BASE_URL}/api/settings", headers=_h(owner["access_token"]),
                json={"team_daily_limit": 30, "client_daily_limit": 10,
                      "autonomous_approvals": False, "autonomous_max_value": 500000,
                      "knowledge_rules": {**rules, "enabled": False}})


# ---------- AI knowledge template ----------
class TestAIKnowledge:
    def test_knowledge_short_prompt_422(self, api, team):
        r = api.post(f"{BASE_URL}/api/ai/chat", headers=_h(team["access_token"]),
                     json={"template": "knowledge", "prompt": "hi"})
        assert r.status_code == 422

    def test_summarize_without_tx_422(self, api, team):
        r = api.post(f"{BASE_URL}/api/ai/chat", headers=_h(team["access_token"]),
                     json={"template": "summarize", "prompt": "please"})
        assert r.status_code == 422

    def test_knowledge_sse_done_with_sources(self, api, owner, team):
        # grant team a shared prefix so it has knowledge access
        g = api.post(f"{BASE_URL}/api/knowledge/grants", headers=_h(owner["access_token"]),
                     json={"user_id": team["user"]["id"], "scope": "shared",
                           "path_prefix": "TEST_IT2/notes", "note": "TEST_IT2 ai"})
        assert g.status_code == 201
        grant_id = g.json()["id"]
        try:
            r = requests.post(f"{BASE_URL}/api/ai/chat",
                              headers={"Authorization": f"Bearer {team['access_token']}", "Content-Type": "application/json"},
                              data=json.dumps({"template": "knowledge", "prompt": "What does Alpha note say?"}),
                              stream=True, timeout=90)
            assert r.status_code == 200, r.text
            done = False
            sources = None
            for line in r.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data: "):
                    continue
                payload = json.loads(line[6:])
                if payload.get("type") == "done":
                    done = True
                    sources = payload.get("sources")
                    break
            r.close()
            assert done
            assert isinstance(sources, list)
        finally:
            api.delete(f"{BASE_URL}/api/knowledge/grants/{grant_id}", headers=_h(owner["access_token"]))


# ---------- client doc uploads ----------
class TestClientUploads:
    def test_client_upload_on_linked_tx(self, api, client_user, team, meridian_tx, mongo):
        tx_id = meridian_tx["id"]
        tok = client_user["access_token"]
        r = requests.post(f"{BASE_URL}/api/transactions/{tx_id}/documents",
                          headers={"Authorization": f"Bearer {tok}"},
                          files={"file": ("TEST_IT2_clientup.txt", b"hello client", "text/plain")},
                          data={"visibility": "internal", "category": "Other"})
        assert r.status_code == 201, r.text
        doc = r.json()
        assert doc["visibility"] == "client"
        assert doc["client_submitted"] is True
        # staff notification exists
        notif = mongo.notifications.find_one({"title": {"$regex": "submitted TEST_IT2_clientup.txt"}})
        assert notif is not None
        # team sees it in list
        lst = api.get(f"{BASE_URL}/api/transactions/{tx_id}/documents", headers=_h(team["access_token"]))
        assert lst.status_code == 200
        assert any(d["id"] == doc["id"] for d in lst.json())

    def test_client_upload_unlinked_404(self, api, client_user, owner):
        # Make a fresh tx that client is NOT linked to
        tx_payload = {"address": f"TEST_IT2 Unlinked {secrets.token_hex(3)}", "city": "Austin", "state": "TX",
                      "zip": "78701", "value": 1000, "property_type": "Single family", "stage_id": "lead",
                      "buyer_id": None, "seller_id": None, "agent": "A",
                      "contract_date": "2026-06-01", "contingency_date": "2026-06-05",
                      "closing_date": "2026-06-15", "assigned_ids": [], "client_ids": [], "image_url": ""}
        tx = api.post(f"{BASE_URL}/api/transactions", headers=_h(owner["access_token"]), json=tx_payload)
        assert tx.status_code == 201
        tx_id = tx.json()["id"]
        try:
            r = requests.post(f"{BASE_URL}/api/transactions/{tx_id}/documents",
                              headers={"Authorization": f"Bearer {client_user['access_token']}"},
                              files={"file": ("TEST_IT2_x.txt", b"x", "text/plain")},
                              data={"category": "Other"})
            assert r.status_code == 404
        finally:
            # delete tx
            import pymongo
            MongoClient(MONGO_URL)[DB_NAME].transactions.delete_one({"id": tx_id})


# ---------- meetings ----------
class TestMeetings:
    @pytest.fixture
    def team_assigned_id(self, team):
        return team["user"]["id"]

    def test_client_proposes_meeting(self, api, client_user, team, meridian_tx):
        tx_id = meridian_tx["id"]
        starts = "2027-05-10T10:00"
        r = api.post(f"{BASE_URL}/api/meetings", headers=_h(client_user["access_token"]),
                     json={"transaction_id": tx_id, "title": "TEST_IT2 Meeting",
                           "starts_at": starts, "participant_ids": [team["user"]["id"]]})
        assert r.status_code == 201, r.text
        m = r.json()
        assert m["responses"][client_user["user"]["id"]] == "accepted"
        assert m["responses"][team["user"]["id"]] == "pending"
        return m

    def test_only_self_participant_422(self, api, client_user, meridian_tx):
        r = api.post(f"{BASE_URL}/api/meetings", headers=_h(client_user["access_token"]),
                     json={"transaction_id": meridian_tx["id"], "title": "TEST_IT2 Solo",
                           "starts_at": "2027-05-11T10:00", "participant_ids": []})
        assert r.status_code == 422

    def test_non_tx_participant_422(self, api, client_user, owner, meridian_tx):
        # create a temp user not on tx
        suf = secrets.token_hex(3)
        u = api.post(f"{BASE_URL}/api/users", headers=_h(owner["access_token"]),
                     json={"name": f"TEST_IT2 outsider {suf}", "email": f"test.outsider.{suf}@example.com",
                           "role": "TEAM_MEMBER", "password": "TempPass12345!"})
        assert u.status_code == 201
        outsider_id = u.json()["id"]
        try:
            r = api.post(f"{BASE_URL}/api/meetings", headers=_h(client_user["access_token"]),
                         json={"transaction_id": meridian_tx["id"], "title": "TEST_IT2 Outsider",
                               "starts_at": "2027-05-12T10:00", "participant_ids": [outsider_id]})
            assert r.status_code == 422
        finally:
            MongoClient(MONGO_URL)[DB_NAME].users.delete_one({"id": outsider_id})

    def test_respond_reschedule_cancel_flow(self, api, client_user, team, owner, meridian_tx):
        tx_id = meridian_tx["id"]
        starts = "2027-05-20T14:00"
        create = api.post(f"{BASE_URL}/api/meetings", headers=_h(client_user["access_token"]),
                          json={"transaction_id": tx_id, "title": "TEST_IT2 Flow",
                                "starts_at": starts, "participant_ids": [team["user"]["id"]]})
        assert create.status_code == 201
        mid = create.json()["id"]

        # invitee accepts
        acc = api.post(f"{BASE_URL}/api/meetings/{mid}/respond", headers=_h(team["access_token"]),
                       json={"response": "accepted"})
        assert acc.status_code == 200
        assert acc.json()["responses"][team["user"]["id"]] == "accepted"

        # non-organizer team member tries to cancel -> 403
        cancel_bad = api.patch(f"{BASE_URL}/api/meetings/{mid}", headers=_h(team["access_token"]),
                               json={"status": "cancelled"})
        assert cancel_bad.status_code == 403

        # organizer reschedules -> other responses reset
        new_starts = "2027-05-21T15:00"
        resched = api.patch(f"{BASE_URL}/api/meetings/{mid}", headers=_h(client_user["access_token"]),
                            json={"starts_at": new_starts})
        assert resched.status_code == 200
        assert resched.json()["responses"][team["user"]["id"]] == "pending"
        assert resched.json()["responses"][client_user["user"]["id"]] == "accepted"

        # owner sees in GET
        owner_list = api.get(f"{BASE_URL}/api/meetings", headers=_h(owner["access_token"]))
        assert owner_list.status_code == 200
        assert any(m["id"] == mid for m in owner_list.json())

        # cancel via DELETE
        d = api.delete(f"{BASE_URL}/api/meetings/{mid}", headers=_h(client_user["access_token"]))
        assert d.status_code == 200

        # respond to cancelled -> 409
        r409 = api.post(f"{BASE_URL}/api/meetings/{mid}/respond", headers=_h(team["access_token"]),
                        json={"response": "accepted"})
        assert r409.status_code == 409
