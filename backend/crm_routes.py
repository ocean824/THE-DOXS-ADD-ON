from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from core import db, uid, now, require, Repo, activity, authorize, settings
from schemas import (ContactIn, ContactOut, StageIn, StageOut, TransactionIn, TransactionOut,
    TransactionPatch, TaskIn, TaskOut, TaskPatch, OK, ActivityOut, SettingsIn, SettingsOut,
    UserIn, UserOut, UserPatch, Preferences)
from auth_routes import hash_password

router=APIRouter(prefix='/api',tags=['CRM'])
TASK_TEMPLATE=[('Order title',2),('Schedule inspection',4),('Collect earnest money deposit',3),('Review inspection report',10),('Order payoff statement',14),('Confirm financing',18),('Review closing disclosure',24),('Confirm closing appointment',27)]
REQUIRED_DOCUMENTS=['Purchase agreement','Inspection report','Title commitment','Closing disclosure']
async def validate_users(ids,roles):
    for id in ids:
        if not await db.users.find_one({'id':id,'active':True,'role':{'$in':roles}},{'_id':0,'id':1}): raise HTTPException(422,'Invalid user assignment')
async def validate_dates(data):
    try: dates=[date.fromisoformat(data[k]) for k in ('contract_date','contingency_date','closing_date')]
    except ValueError: raise HTTPException(422,'Dates must be valid calendar dates')
    if not dates[0]<=dates[1]<=dates[2]: raise HTTPException(422,'Dates must follow contract, contingency, then closing order')

@router.get('/contacts',response_model=list[ContactOut])
async def contacts(user=Depends(require('internal'))): return await Repo(user).list('contacts',sort=('created_at',-1))
@router.post('/contacts',response_model=ContactOut,status_code=201)
async def create_contact(data:ContactIn,user=Depends(require('write'))):
    assigned=data.assigned_ids if user['role']=='OWNER' else [user['id']]
    await validate_users(assigned,['OWNER','TEAM_MEMBER'])
    record=await Repo(user).insert('contacts',{**data.model_dump(),'assigned_ids':assigned,'created_by':user['id']})
    await activity(user,f'added {data.name} to contacts',kind='contact')
    return record
@router.get('/contacts/{id}',response_model=ContactOut)
async def get_contact(id:str,user=Depends(require('internal'))): return await Repo(user).get('contacts',id)
@router.put('/contacts/{id}',response_model=ContactOut)
async def update_contact(id:str,data:ContactIn,user=Depends(require('write'))):
    repo=Repo(user); old=await repo.get('contacts',id)
    values=data.model_dump()
    if user['role']!='OWNER': values['assigned_ids']=old['assigned_ids']
    await validate_users(values['assigned_ids'],['OWNER','TEAM_MEMBER'])
    record=await repo.update('contacts',id,values)
    await activity(user,f'updated {data.name}',kind='contact')
    return record
@router.delete('/contacts/{id}',response_model=OK)
async def delete_contact(id:str,user=Depends(require('delete'))):
    contact=await Repo(user).get('contacts',id)
    if await db.transactions.find_one({'$or':[{'buyer_id':id},{'seller_id':id}]},{'_id':0,'id':1}): raise HTTPException(409,'Contact is linked to a transaction and cannot be deleted')
    await Repo(user).delete('contacts',id)
    await activity(user,f'deleted contact {contact["name"]}',kind='contact')
    return {'message':'Contact deleted'}
@router.get('/pipeline-stages',response_model=list[StageOut])
async def stages(user=Depends(require('read'))): return await db.pipeline_stages.find({},{'_id':0}).sort('position',1).to_list(30)
@router.post('/pipeline-stages',response_model=StageOut,status_code=201)
async def create_stage(data:StageIn,user=Depends(require('manage'))):
    record={'id':uid(),**data.model_dump(),'position':await db.pipeline_stages.count_documents({})}
    await db.pipeline_stages.insert_one(record.copy()); await activity(user,f'added pipeline stage {data.name}')
    return record
@router.patch('/pipeline-stages/{id}',response_model=StageOut)
async def update_stage(id:str,data:StageIn,user=Depends(require('manage'))):
    stage=await db.pipeline_stages.find_one({'id':id},{'_id':0})
    if not stage: raise HTTPException(404,'Stage not found')
    await db.pipeline_stages.update_one({'id':id},{'$set':data.model_dump()})
    await activity(user,f'renamed pipeline stage to {data.name}')
    return {**stage,**data.model_dump()}
@router.get('/transactions',response_model=list[TransactionOut])
async def transactions(user=Depends(require('read'))): return await Repo(user).list('transactions',sort=('created_at',-1))
@router.post('/transactions',response_model=TransactionOut,status_code=201)
async def create_transaction(data:TransactionIn,user=Depends(require('write'))):
    await validate_dates(data.model_dump())
    if not await db.pipeline_stages.find_one({'id':data.stage_id},{'_id':0}): raise HTTPException(422,'Invalid pipeline stage')
    values=data.model_dump(); repo=Repo(user)
    for cid in (data.buyer_id,data.seller_id):
        if cid: await repo.get('contacts',cid)
    if user['role']!='OWNER':
        if data.client_ids: raise HTTPException(403,'Only the owner can grant client access')
        values['assigned_ids']=[user['id']]
    await validate_users(values['assigned_ids'],['OWNER','TEAM_MEMBER'])
    await validate_users(values['client_ids'],['CLIENT'])
    record=await repo.insert('transactions',{**values,'created_by':user['id'],'review_status':'not_submitted','required_documents':REQUIRED_DOCUMENTS,'sample':False})
    for title,offset in TASK_TEMPLATE:
        await repo.insert('tasks',{'transaction_id':record['id'],'title':title,'due_date':(date.fromisoformat(data.contract_date)+timedelta(days=offset)).isoformat(),'assignee_id':values['assigned_ids'][0] if values['assigned_ids'] else user['id'],'completed':False})
    await activity(user,f'opened {record["address"]}',record,'transaction')
    return record
@router.get('/transactions/{id}',response_model=TransactionOut)
async def get_transaction(id:str,user=Depends(require('read'))): return await Repo(user).get('transactions',id)
@router.patch('/transactions/{id}',response_model=TransactionOut)
async def update_transaction(id:str,data:TransactionPatch,user=Depends(require('write'))):
    repo=Repo(user); tx=await repo.get('transactions',id); values=data.model_dump(exclude_none=True)
    if any(k in values for k in ('assigned_ids','client_ids')):
        await authorize(user,'manage')
        await validate_users(values.get('assigned_ids',[]),['OWNER','TEAM_MEMBER']);await validate_users(values.get('client_ids',[]),['CLIENT'])
    if 'stage_id' in values and not await db.pipeline_stages.find_one({'id':values['stage_id']},{'_id':0}): raise HTTPException(422,'Invalid pipeline stage')
    if 'closing_date' in values: await validate_dates({**tx,**values})
    record=await repo.update('transactions',id,values)
    await activity(user,f'updated {record["address"]}',record,'transaction')
    return record
@router.get('/tasks',response_model=list[TaskOut])
async def tasks(user=Depends(require('internal'))): return await Repo(user).list('tasks',sort=('due_date',1))
@router.get('/transactions/{id}/tasks',response_model=list[TaskOut])
async def transaction_tasks(id:str,user=Depends(require('internal'))):
    repo=Repo(user); await repo.get('transactions',id); return await repo.list('tasks',{'transaction_id':id},sort=('due_date',1))
@router.post('/transactions/{id}/tasks',response_model=TaskOut,status_code=201)
async def add_task(id:str,data:TaskIn,user=Depends(require('write'))):
    repo=Repo(user); tx=await repo.get('transactions',id)
    await validate_users([data.assignee_id],['OWNER','TEAM_MEMBER'])
    if data.assignee_id not in tx['assigned_ids'] and data.assignee_id != user['id']: raise HTTPException(422,'Task assignee must be on this transaction')
    try: date.fromisoformat(data.due_date)
    except ValueError: raise HTTPException(422,'Invalid due date')
    record=await repo.insert('tasks',{'transaction_id':id,**data.model_dump(),'completed':False})
    await activity(user,f'added task: {data.title}',tx,'task');return record
@router.patch('/tasks/{id}',response_model=TaskOut)
async def update_task(id:str,data:TaskPatch,user=Depends(require('write'))):
    repo=Repo(user); task=await repo.get('tasks',id); tx=await repo.get('transactions',task['transaction_id'])
    if data.assignee_id:
        await validate_users([data.assignee_id],['OWNER','TEAM_MEMBER'])
        if data.assignee_id not in tx['assigned_ids'] and data.assignee_id != user['id']: raise HTTPException(422,'Assignee must be on this transaction')
    if data.due_date:
        try: date.fromisoformat(data.due_date)
        except ValueError: raise HTTPException(422,'Invalid due date')
    record=await repo.update('tasks',id,data.model_dump(exclude_none=True))
    await activity(user,f'{"completed" if record["completed"] else "updated"} {task["title"].lower()}',tx,'task')
    return record
@router.get('/activity',response_model=list[ActivityOut])
async def feed(user=Depends(require('read'))): return await Repo(user).list('activities',limit=40,sort=('created_at',-1))
@router.get('/users',response_model=list[UserOut],tags=['Owner administration'])
async def users(user=Depends(require('manage'))): return await db.users.find({},{'_id':0,'password_hash':0}).to_list(500)
@router.get('/directory',response_model=list[UserOut])
async def directory(user=Depends(require('read'))):
    if user['role']=='OWNER': q={}
    elif user['role']=='CLIENT': q={'id':user['id']}
    else:
        txs=await Repo(user).list('transactions'); ids=list(set([i for t in txs for i in t['client_ids']+t['assigned_ids']]+[user['id']]))
        q={'$or':[{'id':{'$in':ids}},{'role':'OWNER'}]}
    return await db.users.find(q,{'_id':0,'password_hash':0}).to_list(500)
@router.post('/users',response_model=UserOut,status_code=201,tags=['Owner administration'])
async def add_user(data:UserIn,user=Depends(require('manage'))):
    if await db.users.find_one({'email':data.email.lower()},{'_id':0}): raise HTTPException(409,'Email already has an account')
    record={'id':uid(),'name':data.name,'email':data.email.lower(),'role':data.role,'active':True,'created_at':now(),'notification_preferences':Preferences().model_dump()}
    await db.users.insert_one({**record,'password_hash':await hash_password(data.password)})
    await activity(user,f'created {data.role.lower().replace("_"," ")} account for {data.name}',kind='user')
    return record
@router.patch('/users/{id}',response_model=UserOut,tags=['Owner administration'])
async def edit_user(id:str,data:UserPatch,user=Depends(require('manage'))):
    if id==user['id']: raise HTTPException(400,'You cannot change your own role or deactivate yourself')
    if not await db.users.find_one({'id':id},{'_id':0}): raise HTTPException(404,'User not found')
    await db.users.update_one({'id':id},{'$set':data.model_dump(exclude_none=True)})
    await db.sessions.update_many({'user_id':id},{'$set':{'revoked':True}})
    await activity(user,'updated account permissions',kind='user')
    return await db.users.find_one({'id':id},{'_id':0,'password_hash':0})
@router.patch('/notification-preferences',response_model=Preferences)
async def preferences(data:Preferences,user=Depends(require('read'))):
    await db.users.update_one({'id':user['id']},{'$set':{'notification_preferences':data.model_dump()}});return data
@router.get('/settings',response_model=SettingsOut,tags=['Owner administration'])
async def get_settings(user=Depends(require('manage'))): return await settings()
@router.put('/settings',response_model=SettingsOut,tags=['Owner administration'])
async def put_settings(data:SettingsIn,user=Depends(require('manage'))):
    await db.settings.update_one({'id':'workspace'},{'$set':data.model_dump()})
    await activity(user,'updated assistant limits and approval policy',kind='settings');return await settings()