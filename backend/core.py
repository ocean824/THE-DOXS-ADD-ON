import os, uuid, hashlib
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt

load_dotenv(Path(__file__).parent / '.env')
client = AsyncIOMotorClient(os.environ['MONGO_URL'])
db = client[os.environ['DB_NAME']]
ORIGIN = os.environ['APP_ORIGIN'].rstrip('/')
SECRET = os.environ['JWT_SECRET']
bearer = HTTPBearer(auto_error=False)
def uid(): return str(uuid.uuid4())
def now(): return datetime.now(timezone.utc).isoformat()
def digest(value): return hashlib.sha256(value.encode()).hexdigest()
def clean(doc): return {k:v for k,v in doc.items() if k != '_id'} if doc else None

PERMS = {
    'OWNER': {'read','write','delete','manage','review','ai','message','internal'},
    'TEAM_MEMBER': {'read','write','ai','message','internal'},
    'CLIENT': {'read','ai'},
}
async def authorize(user, action, resource=None):
    allowed = action in (set(user.get('scopes', [])) if user.get('principal_type') == 'service' else PERMS.get(user.get('role'), set()))
    await db.authorization_logs.insert_one({'id':uid(),'user_id':user['id'],'action':action,'resource_id':(resource or {}).get('id'),'allowed':allowed,'created_at':now()})
    if not allowed: raise HTTPException(403, 'You do not have permission to perform this action')

async def current_user(request: Request, credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    token = credentials.credentials if credentials else request.cookies.get('dox_access')
    if not token: raise HTTPException(401, 'Please sign in')
    try:
        claims = jwt.decode(token, SECRET, algorithms=['HS256'], issuer='dox-workspace', audience='dox-api')
        session = await db.sessions.find_one({'id':claims['sid'],'user_id':claims['sub'],'revoked':False}, {'_id':0})
        user = await db.users.find_one({'id':claims['sub'],'active':True}, {'_id':0,'password_hash':0})
        if not user or not session or claims.get('type') != 'access': raise ValueError()
    except Exception:
        raise HTTPException(401, 'Session expired. Please sign in again')
    if not credentials and request.method not in ('GET','HEAD','OPTIONS') and request.headers.get('origin') != ORIGIN:
        raise HTTPException(403, 'Invalid request origin')
    user['_session_id'] = session['id']
    user['_expires'] = claims['exp']
    return user

def require(action):
    async def dependency(user=Depends(current_user)):
        await authorize(user, action)
        return user
    return dependency

class Repo:
    """Mandatory relationship scoping for every domain read and mutation."""
    def __init__(self, user): self.user = user
    async def scope(self, collection):
        u = self.user
        if u.get('principal_type') == 'service':
            if collection not in ('reviews','transactions','tasks','documents','review_comments'):
                raise HTTPException(403,'Service scope does not permit this resource')
            await authorize(u,'approvals:read')
            if collection == 'reviews': return {}
            review_rows=await db.reviews.find({}, {'_id':0,'transaction_id':1}).to_list(1000)
            return {'id' if collection=='transactions' else 'transaction_id':{'$in':[r['transaction_id'] for r in review_rows]}}
        if collection == 'notifications': return {'user_id':u['id']}
        if collection == 'ai_usage_logs':
            await authorize(u, 'manage'); return {}
        if collection == 'activities':
            return {} if u['role']=='OWNER' else {'audience_ids':u['id'], 'internal':{'$ne':True}} if u['role']=='CLIENT' else {'audience_ids':u['id']}
        if u['role'] == 'OWNER': return {}
        if collection == 'transactions':
            return {'client_ids' if u['role']=='CLIENT' else 'assigned_ids':u['id']}
        if collection == 'contacts':
            await authorize(u, 'internal'); return {'assigned_ids':u['id']}
        if collection == 'threads': return {'participant_ids':u['id']}
        if collection == 'meetings': return {'participant_ids':u['id']}
        if collection == 'messages':
            ids = [x['id'] for x in await self.list('threads')]
            return {'thread_id':{'$in':ids}}
        if collection in ('tasks','reviews','review_comments','documents'):
            if collection != 'documents': await authorize(u,'internal')
            txs = await self.list('transactions')
            q = {'transaction_id':{'$in':[x['id'] for x in txs]}}
            if collection == 'documents' and u['role']=='CLIENT': q['visibility']='client'
            return q
        raise HTTPException(403,'Resource not accessible')
    async def query(self, collection, query=None):
        return {'$and':[await self.scope(collection),query or {}]}
    async def list(self, collection, query=None, limit=500, sort=None):
        cursor = db[collection].find(await self.query(collection,query), {'_id':0})
        if sort: cursor=cursor.sort(*sort)
        return await cursor.to_list(limit)
    async def get(self, collection, id):
        doc=await db[collection].find_one(await self.query(collection,{'id':id}),{'_id':0})
        if not doc: raise HTTPException(404,'Record not found')
        return doc
    async def update(self, collection, id, values):
        await self.get(collection,id)
        await db[collection].update_one(await self.query(collection,{'id':id}),{'$set':values})
        return await self.get(collection,id)
    async def insert(self, collection, values):
        record={'id':uid(), **values, 'created_at':now()}
        await db[collection].insert_one(record.copy())
        return record
    async def delete(self, collection, id):
        await self.get(collection,id)
        await db[collection].delete_one(await self.query(collection,{'id':id}))

async def activity(user, text, transaction=None, kind='update', internal=True):
    audience=list(set([user['id']]+(transaction or {}).get('assigned_ids',[])+(transaction or {}).get('client_ids',[])))
    record={'id':uid(),'actor_id':user['id'],'actor_name':user.get('name','Integration'),'text':text,'transaction_id':(transaction or {}).get('id'),'audience_ids':audience,'kind':kind,'internal':internal,'created_at':now()}
    await db.activities.insert_one(record.copy())
    await db.events.insert_one({'id':uid(),'audience_ids':audience,'created_at':now()})

async def settings():
    return await db.settings.find_one({'id':'workspace'},{'_id':0})