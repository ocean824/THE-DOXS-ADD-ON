import os, asyncio, mimetypes
from pathlib import Path
from urllib.parse import quote
import httpx
from fastapi import APIRouter, Depends, File, UploadFile, Form, HTTPException, Response
from core import db, uid, now, require, Repo, activity, authorize
from schemas import DocumentOut, OK

STORAGE_BASE=(os.environ.get('INTEGRATION_PROXY_URL') or '').strip() or 'https://integrations.emergentagent.com'
STORAGE_URL=STORAGE_BASE.rstrip('/')+'/objstore/api/v1/storage'
storage_key=None
storage_lock=asyncio.Lock()
async def init_storage(force=False):
    global storage_key
    async with storage_lock:
        if storage_key and not force: return storage_key
        async with httpx.AsyncClient(timeout=30) as client:
            response=await client.post(f'{STORAGE_URL}/init',json={'emergent_key':os.environ['EMERGENT_LLM_KEY']})
            response.raise_for_status(); storage_key=response.json()['storage_key']
        return storage_key
async def storage_request(method,path,content=None,content_type=None):
    try:
        key=await init_storage()
        async with httpx.AsyncClient(timeout=90) as client:
            response=await client.request(method,f'{STORAGE_URL}/objects/{path}',headers={'X-Storage-Key':key,'Content-Type':content_type or 'application/octet-stream'},content=content)
            if response.status_code==404:
                key=await init_storage(force=True)
                response=await client.request(method,f'{STORAGE_URL}/objects/{path}',headers={'X-Storage-Key':key,'Content-Type':content_type or 'application/octet-stream'},content=content)
            response.raise_for_status(); return response
    except httpx.HTTPError: raise HTTPException(503,'Document storage is temporarily unavailable. Please try again later.')
router=APIRouter(prefix='/api',tags=['Documents'])
ALLOWED={'pdf':'application/pdf','png':'image/png','jpg':'image/jpeg','jpeg':'image/jpeg','docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document','txt':'text/plain'}
def public(doc): return {k:v for k,v in doc.items() if k not in ('storage_path','is_deleted')}
@router.get('/transactions/{id}/documents',response_model=list[DocumentOut])
async def documents(id:str,user=Depends(require('read'))):
    repo=Repo(user);await repo.get('transactions',id)
    return [public(d) for d in await repo.list('documents',{'transaction_id':id,'is_deleted':False})]
@router.post('/transactions/{id}/documents',response_model=DocumentOut,status_code=201)
async def upload(id:str,file:UploadFile=File(...),visibility:str=Form('internal'),category:str=Form('Other'),user=Depends(require('read'))):
    repo=Repo(user);tx=await repo.get('transactions',id);client=user['role']=='CLIENT'
    if client:visibility='client'
    else:await authorize(user,'write')
    if visibility not in ('internal','client'): raise HTTPException(422,'Invalid visibility')
    if category not in tx['required_documents']+['Other']: raise HTTPException(422,'Invalid document category')
    ext=Path(file.filename or '').suffix.lower().lstrip('.')
    if ext not in ALLOWED: raise HTTPException(415,'Supported files: PDF, DOCX, PNG, JPG, TXT')
    content=await file.read(20*1024*1024+1)
    if not content or len(content)>20*1024*1024: raise HTTPException(413,'File must be between 1 byte and 20 MB')
    signatures={'pdf':b'%PDF','png':b'\x89PNG','jpg':b'\xff\xd8','jpeg':b'\xff\xd8','docx':b'PK'}
    if ext in signatures and not content.startswith(signatures[ext]): raise HTTPException(415,'File contents do not match its extension')
    path=f'dox-workspace/uploads/{user["id"]}/{uid()}.{ext}'
    result=(await storage_request('PUT',path,content,ALLOWED[ext])).json()
    record=await repo.insert('documents',{'transaction_id':id,'filename':Path(file.filename).name[:200],'content_type':ALLOWED[ext],'size':len(content),'category':category,'visibility':visibility,'uploaded_by':user['id'],'uploaded_by_name':user['name'],'client_submitted':client,'storage_path':result['path'],'is_deleted':False})
    await activity(user,f'{"submitted" if client else "uploaded"} {record["filename"]}',tx,'document',visibility!='client')
    if client:
        for member in set(tx['assigned_ids']+[o['id'] for o in await db.users.find({'role':'OWNER','active':True},{'_id':0,'id':1}).to_list(50)]):
            await db.notifications.insert_one({'id':uid(),'user_id':member,'title':f'{user["name"]} submitted {record["filename"]} · {tx["address"]}','link':f'/transactions/{id}','read':False,'created_at':now()})
    return public(record)
@router.get('/documents/{id}/download',responses={200:{'content':{'application/octet-stream':{}},'description':'Authenticated file attachment; MIME type matches document metadata.'}})
async def download(id:str,user=Depends(require('read'))):
    doc=await Repo(user).get('documents',id)
    if doc['is_deleted']: raise HTTPException(404,'Document not found')
    response=await storage_request('GET',doc['storage_path'])
    return Response(response.content,media_type=doc['content_type'],headers={'Content-Disposition':f"attachment; filename*=UTF-8''{quote(doc['filename'])}",'X-Content-Type-Options':'nosniff','Cache-Control':'private, no-store'})
@router.delete('/documents/{id}',response_model=OK)
async def delete_doc(id:str,user=Depends(require('delete'))):
    repo=Repo(user);doc=await repo.get('documents',id);tx=await repo.get('transactions',doc['transaction_id'])
    await repo.update('documents',id,{'is_deleted':True});await activity(user,f'removed {doc["filename"]}',tx,'document')
    return {'message':'Document removed'}