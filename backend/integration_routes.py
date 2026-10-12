import secrets,json
from pathlib import Path
from datetime import datetime,timezone,timedelta
from fastapi import APIRouter,Depends,HTTPException
from fastapi.responses import PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials
from pymongo.errors import DuplicateKeyError
from pydantic import BaseModel
from core import db,uid,now,digest,bearer,require,authorize,Repo,settings,activity
from schemas import ServiceKeyIn,ServiceKeyOut,HermesDecision,ConfirmationIn,ConfirmationOut,ReviewOut,ContactIn,ContactOut,OK
from review_routes import decide_review,compliance

router=APIRouter(prefix='/api/integrations',tags=['Integration contracts'])
class IntegrationStatus(BaseModel):
    service:str
    status:str
    last_seen:str|None=None
class PromptOut(BaseModel):
    version:str
    content:str
class QueueItem(BaseModel):
    review:ReviewOut
    property_address:str
    value:float
    completed_tasks:int
    total_tasks:int
    missing_documents:list[str]
async def service_principal(credentials:HTTPAuthorizationCredentials=Depends(bearer)):
    if not credentials:raise HTTPException(401,'Service credential required')
    key=await db.service_keys.find_one({'hash':digest(credentials.credentials),'active':True},{'_id':0,'hash':0})
    if not key:raise HTTPException(401,'Invalid service credential')
    await db.service_keys.update_one({'id':key['id']},{'$set':{'last_seen':now()}})
    return {'id':key['id'],'name':key['service'].capitalize(),'principal_type':'service','scopes':key['scopes'],'service':key['service'],'role':'SERVICE'}
@router.get('/status',response_model=list[IntegrationStatus])
async def status(user=Depends(require('manage'))):
    result=[]
    for service in ['hermes','dox']:
        key=await db.service_keys.find_one({'service':service,'active':True},{'_id':0,'last_seen':1})
        result.append({'service':service,'status':'Connected' if key and key.get('last_seen') else 'Key issued' if key else 'Not connected','last_seen':key.get('last_seen') if key else None})
    return result
@router.post('/keys',response_model=ServiceKeyOut)
async def create_key(data:ServiceKeyIn,user=Depends(require('manage'))):
    key=secrets.token_urlsafe(48);scopes=['approvals:read','approvals:decide','knowledge:grant'] if data.service=='hermes' else ['contacts:ingest']
    await db.service_keys.update_many({'service':data.service},{'$set':{'active':False}})
    await db.service_keys.insert_one({'id':uid(),'service':data.service,'hash':digest(key),'scopes':scopes,'active':True,'created_by':user['id'],'created_at':now(),'last_seen':None})
    await activity(user,f'issued a new {data.service} service credential',kind='settings')
    return {'key':key,'service':data.service,'scopes':scopes}
@router.delete('/keys/{service}',response_model=OK)
async def revoke_key(service:str,user=Depends(require('manage'))):
    if service not in ('hermes','dox'):raise HTTPException(404,'Integration not found')
    await db.service_keys.update_many({'service':service},{'$set':{'active':False}})
    await activity(user,f'revoked {service} integration access',kind='settings')
    return {'message':'Integration credential revoked'}
@router.get('/prompts/{target}',response_model=PromptOut)
async def prompt(target:str,user=Depends(require('manage'))):
    if target not in ('hermes','dox','traycer'):raise HTTPException(404,'Prompt not found')
    path=Path(__file__).parent.parent/'docs'/f'{target.upper()}-v1.md'
    return {'version':f'{target.upper()}-v1','content':path.read_text()}
@router.get('/cli',response_class=PlainTextResponse,responses={200:{'content':{'text/x-python':{}},'description':'dox-vault command-line tool: syncs an Obsidian folder or Microsoft 365 (CLI for Microsoft 365) files into the knowledge vault using owner desktop tokens.'}})
async def cli(user=Depends(require('manage'))):
    return PlainTextResponse((Path(__file__).parent.parent/'cli'/'dox_vault.py').read_text(),headers={'Content-Disposition':'attachment; filename="dox_vault.py"'})
@router.post('/reviews/{id}/confirmation',response_model=ConfirmationOut)
async def confirm(id:str,data:ConfirmationIn,user=Depends(require('review'))):
    review=await Repo(user).get('reviews',id)
    if review['status']!='pending':raise HTTPException(409,'Review no longer pending')
    if review['submitted_by']==user['id']:raise HTTPException(403,'A different owner must confirm this review')
    if data.decision!='approved' and not data.note.strip():raise HTTPException(422,'A note is required')
    token=secrets.token_urlsafe(48)
    await db.approval_confirmations.insert_one({'hash':digest(token),'review_id':id,'decision':data.decision,'note_hash':digest(data.note),'owner_id':user['id'],'used':False,'expires':datetime.now(timezone.utc)+timedelta(minutes=5)})
    await activity(user,'issued a single-use mobile approval confirmation',await Repo(user).get('transactions',review['transaction_id']),'review')
    return {'confirmation_token':token,'expires_in':300}
@router.get('/hermes/queue',response_model=list[QueueItem])
async def queue(principal=Depends(service_principal)):
    await authorize(principal,'approvals:read');repo=Repo(principal);reviews=await repo.list('reviews',{'status':'pending'})
    result=[]
    for review in reviews:
        tx=await repo.get('transactions',review['transaction_id']);tasks,docs,missing=await compliance(repo,tx)
        result.append({'review':review,'property_address':tx['address'],'value':tx['value'],'completed_tasks':sum(t['completed'] for t in tasks),'total_tasks':len(tasks),'missing_documents':missing})
    return result
@router.post('/hermes/decisions',response_model=ReviewOut)
async def hermes_decision(data:HermesDecision,principal=Depends(service_principal)):
    await authorize(principal,'approvals:decide');receipt_id=f'{principal["id"]}:{data.idempotency_key}'
    request_hash=digest(json.dumps(data.model_dump(exclude={'confirmation_token'}),sort_keys=True))
    existing=await db.integration_receipts.find_one({'id':receipt_id},{'_id':0})
    if existing:
        if existing['request_hash']!=request_hash:raise HTTPException(409,'Idempotency key was used for a different request')
        if 'result' in existing:return existing['result']
        raise HTTPException(409,'Decision is already being processed')
    repo=Repo(principal);review=await repo.get('reviews',data.review_id)
    if review['status']!='pending':raise HTTPException(409,'Review already decided')
    tx=await repo.get('transactions',review['transaction_id']);mode='owner-confirmed Hermes';config=await settings()
    if data.confirmation_token:
        proof=await db.approval_confirmations.find_one_and_update({'hash':digest(data.confirmation_token),'review_id':data.review_id,'decision':data.decision,'note_hash':digest(data.note),'used':False,'expires':{'$gt':datetime.now(timezone.utc)}},{'$set':{'used':True}},projection={'_id':0})
        if not proof:raise HTTPException(403,'Owner confirmation is invalid, expired, or already used')
        owner=await db.users.find_one({'id':proof['owner_id'],'role':'OWNER','active':True},{'_id':0,'id':1})
        if not owner:raise HTTPException(403,'Owner authority has been revoked')
        principal['_confirmed_owner_id']=owner['id']
    else:
        tasks,docs,missing=await compliance(repo,tx)
        if not config['autonomous_approvals'] or data.decision!='approved' or tx['value']>config['autonomous_max_value'] or not tasks or not all(t['completed'] for t in tasks) or missing:
            raise HTTPException(403,'Explicit owner confirmation is required; autonomous policy conditions are not met')
        mode='Hermes autonomous policy';principal['_policy_hash']=digest(json.dumps(config,sort_keys=True))
    try:await db.integration_receipts.insert_one({'id':receipt_id,'request_hash':request_hash,'created_at':now(),'confirmed_owner_id':principal.get('_confirmed_owner_id'),'policy_hash':principal.get('_policy_hash')})
    except DuplicateKeyError:raise HTTPException(409,'Decision is already being processed')
    result=await decide_review(data.review_id,data,principal,mode)
    await db.integration_receipts.update_one({'id':receipt_id},{'$set':{'result':result}})
    return result
@router.post('/dox/contacts',response_model=ContactOut,status_code=201)
async def dox_contact(data:ContactIn,principal=Depends(service_principal)):
    await authorize(principal,'contacts:ingest')
    owner=await db.users.find_one({'role':'OWNER','active':True},{'_id':0,'id':1})
    if not owner:raise HTTPException(503,'No active owner')
    existing=await db.contacts.find_one({'email':data.email.lower(),'created_by':principal['id']},{'_id':0})
    if existing:return existing
    record={'id':uid(),**data.model_dump(),'email':data.email.lower(),'assigned_ids':[owner['id']],'created_by':principal['id'],'created_at':now()}
    await db.contacts.insert_one(record.copy());await activity(principal,f'received Dox referral: {data.name}',kind='contact')
    return record