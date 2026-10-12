import asyncio, json, time
from datetime import date,timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from core import db,uid,now,require,Repo,activity
from schemas import ThreadIn,ThreadOut,MessageIn,MessageOut,NotificationOut,OK
router=APIRouter(prefix='/api',tags=['Messaging & notifications'])
@router.get('/threads',response_model=list[ThreadOut])
async def threads(user=Depends(require('read'))):
    repo=Repo(user);records=await repo.list('threads',sort=('last_message_at',-1))
    for thread in records:
        thread['unread']=await db.messages.count_documents(await repo.query('messages',{'thread_id':thread['id'],'read_by':{'$ne':user['id']}}))
    return records
@router.post('/threads',response_model=ThreadOut,status_code=201)
async def create_thread(data:ThreadIn,user=Depends(require('message'))):
    repo=Repo(user);tx=None;contact=None
    if data.transaction_id:tx=await repo.get('transactions',data.transaction_id)
    if data.contact_id:contact=await repo.get('contacts',data.contact_id)
    if not tx and not contact:raise HTTPException(422,'Attach a transaction or contact to the conversation')
    participants=list(set(data.participant_ids+[user['id']]))
    owners=await db.users.find({'role':'OWNER','active':True},{'_id':0,'id':1}).to_list(100)
    allowed=set([user['id']]+[o['id'] for o in owners]+(tx or {}).get('assigned_ids',[])+(tx or {}).get('client_ids',[])+(contact or {}).get('assigned_ids',[]))
    for id in participants:
        person=await db.users.find_one({'id':id,'active':True},{'_id':0})
        if not person:raise HTTPException(422,'Participant is unavailable')
        if user['role']!='OWNER' and id not in allowed:raise HTTPException(403,'Participant is not assigned to this record')
        if person['role']=='CLIENT' and (not tx or id not in tx['client_ids']):raise HTTPException(422,'Client must be linked to this transaction')
    record=await repo.insert('threads',{**data.model_dump(),'participant_ids':participants,'created_by':user['id'],'last_message':'','last_message_at':now()})
    await activity(user,f'started conversation: {data.title}',tx,'message');return record
@router.get('/threads/{id}/messages',response_model=list[MessageOut])
async def messages(id:str,user=Depends(require('read'))):
    repo=Repo(user);await repo.get('threads',id);return await repo.list('messages',{'thread_id':id},sort=('created_at',1))
@router.post('/threads/{id}/messages',response_model=MessageOut,status_code=201)
async def send_message(id:str,data:MessageIn,user=Depends(require('message'))):
    repo=Repo(user);thread=await repo.get('threads',id)
    if not data.body.strip():raise HTTPException(422,'Message cannot be empty')
    if not set(data.mention_ids).issubset(set(thread['participant_ids'])):raise HTTPException(422,'Mentions must be conversation participants')
    record=await repo.insert('messages',{**data.model_dump(),'thread_id':id,'sender_id':user['id'],'sender_name':user['name'],'read_by':[user['id']]})
    await repo.update('threads',id,{'last_message':data.body[:150],'last_message_at':now()})
    for member in thread['participant_ids']:
        if member==user['id']:continue
        person=await db.users.find_one({'id':member,'active':True},{'_id':0})
        if not person:continue
        mentioned=member in data.mention_ids; prefs=person.get('notification_preferences',{})
        if prefs.get('mentions' if mentioned else 'messages',True):
            await db.notifications.insert_one({'id':uid(),'user_id':member,'title':f'{user["name"]} {"mentioned you in" if mentioned else "replied to"} {thread["title"]}','link':f'/messages?thread={id}','read':False,'created_at':now()})
    await db.events.insert_one({'id':uid(),'audience_ids':thread['participant_ids'],'created_at':now()})
    return record
@router.post('/threads/{id}/read',response_model=OK)
async def mark_read(id:str,user=Depends(require('read'))):
    repo=Repo(user);thread=await repo.get('threads',id)
    result=await db.messages.update_many(await repo.query('messages',{'thread_id':id,'read_by':{'$ne':user['id']}}),{'$addToSet':{'read_by':user['id']}})
    if result.modified_count:await db.events.insert_one({'id':uid(),'audience_ids':thread['participant_ids'],'created_at':now()})
    return {'message':'Conversation marked as read'}
@router.get('/notifications',response_model=list[NotificationOut])
async def notifications(user=Depends(require('read'))):
    repo=Repo(user);items=await repo.list('notifications',sort=('created_at',-1))
    if user['role']!='CLIENT' and user.get('notification_preferences',{}).get('tasks',True):
        tasks=await repo.list('tasks',{'completed':False,'assignee_id':user['id'],'due_date':{'$lte':(date.today()+timedelta(days=1)).isoformat()}})
        items=[{'id':'task-'+t['id'],'user_id':user['id'],'title':f'{t["title"]} · due {t["due_date"]}','link':f'/transactions/{t["transaction_id"]}','read':False,'created_at':t['created_at']} for t in tasks]+items
    return items
@router.patch('/notifications/{id}/read',response_model=OK)
async def read_notification(id:str,user=Depends(require('read'))):
    await Repo(user).update('notifications',id,{'read':True});return {'message':'Notification read'}
@router.get('/events',responses={200:{'content':{'text/event-stream':{}},'description':'SSE events: ready, change {timestamp}, expired. Cookie or bearer authentication. Reconnect after token refresh.'}})
async def events(request:Request,user=Depends(require('read'))):
    async def stream():
        since=now(); ticks=0
        yield 'event: ready\ndata: {}\n\n'
        while not await request.is_disconnected():
            if time.time()>=user['_expires']:
                yield 'event: expired\ndata: {}\n\n';break
            if ticks%5==0:
                session=await db.sessions.find_one({'id':user['_session_id'],'revoked':False},{'_id':0,'id':1})
                if not session:yield 'event: expired\ndata: {}\n\n';break
            query={'created_at':{'$gt':since}}
            if user['role']!='OWNER':query['audience_ids']=user['id']
            changes=await db.events.find(query,{'_id':0}).sort('created_at',-1).to_list(1)
            if changes:
                since=changes[0]['created_at'];yield f'event: change\ndata: {json.dumps({"timestamp":since})}\n\n'
            elif ticks%10==0:yield ': heartbeat\n\n'
            ticks+=1;await asyncio.sleep(2)
    return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})