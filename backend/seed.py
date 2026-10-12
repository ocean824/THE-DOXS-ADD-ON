import os,secrets
from datetime import date,timedelta
from core import db,uid,now
from auth_routes import hash_password
from crm_routes import TASK_TEMPLATE,REQUIRED_DOCUMENTS

IMAGES=[
 'https://images.unsplash.com/photo-1613977257363-707ba9348227?auto=format&fit=crop&w=900&q=85',
 'https://images.unsplash.com/photo-1580587771525-78b9dba3b914?auto=format&fit=crop&w=900&q=85',
 'https://images.unsplash.com/photo-1706808849780-7a04fbac83ef?auto=format&fit=crop&w=900&q=85',
 'https://images.unsplash.com/photo-1600596542815-ffad4c1539a9?auto=format&fit=crop&w=900&q=85',
 'https://images.unsplash.com/photo-1600047509807-ba8f99d2cdde?auto=format&fit=crop&w=900&q=85',
 'https://images.unsplash.com/photo-1600607687939-ce8a6c25118c?auto=format&fit=crop&w=900&q=85',
]
async def seed():
    await db.users.create_index('email',unique=True)
    for name in ['users','sessions','transactions','contacts','tasks','documents','reviews','threads','messages','ai_daily_usage','service_keys','integration_receipts','pipeline_stages','settings','knowledge_items','knowledge_grants','meetings']:
        await db[name].create_index('id',unique=True)
    await db.meetings.create_index([('participant_ids',1),('starts_at',1)])
    await db.knowledge_items.create_index('path',unique=True)
    await db.knowledge_items.create_index([('title','text'),('content','text'),('tags','text')],name='knowledge_text')
    await db.knowledge_grants.create_index([('user_id',1),('active',1)])
    await db.approval_confirmations.create_index('expires',expireAfterSeconds=0)
    await db.sessions.create_index('expires',expireAfterSeconds=0)
    await db.password_resets.create_index('expires',expireAfterSeconds=0)
    await db.rate_limits.create_index('expires',expireAfterSeconds=0)
    await db.transactions.create_index('assigned_ids');await db.transactions.create_index('client_ids')
    await db.contacts.create_index('assigned_ids');await db.messages.create_index([('thread_id',1),('created_at',1)])
    for name in ['tasks','documents','reviews','review_comments']:await db[name].create_index('transaction_id')
    await db.settings.update_one({'id':'workspace'},{'$setOnInsert':{'team_daily_limit':30,'client_daily_limit':10,'autonomous_approvals':False,'autonomous_max_value':500000}},upsert=True)
    await db.settings.update_one({'id':'workspace','knowledge_rules':{'$exists':False}},{'$set':{'knowledge_rules':{'enabled':False,'roles':['TEAM_MEMBER'],'scopes':['project'],'project_types':['Single family','Condominium','Townhouse','Commercial','Land'],'path_prefixes':[]}}})
    await db.service_keys.update_many({'service':'hermes','scopes':{'$ne':'knowledge:grant'}},{'$addToSet':{'scopes':'knowledge:grant'}})
    if await db.users.find_one({'role':'OWNER'}):return
    owner_id=uid();maya_id=uid();james_id=uid()
    owner={'id':owner_id,'name':'Ocean','email':os.environ['INITIAL_OWNER_EMAIL'].lower(),'password_hash':await hash_password(os.environ['INITIAL_OWNER_PASSWORD']),'role':'OWNER','active':True,'notification_preferences':{'messages':True,'mentions':True,'tasks':True},'created_at':now()}
    await db.users.insert_one(owner.copy())
    for id,name in [(maya_id,'Maya Chen'),(james_id,'James Wilson')]:
        await db.users.insert_one({'id':id,'name':name,'email':f'{name.lower().replace(" ",".")}@example.com','password_hash':await hash_password(secrets.token_urlsafe(24)),'role':'TEAM_MEMBER','active':False,'notification_preferences':{'messages':True,'mentions':True,'tasks':True},'created_at':now()})
    for pos,(id,name,color) in enumerate([('lead','Lead','#829fba'),('appointment','Appointment','#b5a0c4'),('contract','Under contract','#e5b869'),('closing','Closing','#79b99d')]):
        await db.pipeline_stages.insert_one({'id':id,'name':name,'color':color,'position':pos})
    contact_ids=[]
    for i,(name,type,tags) in enumerate([('Alexander Morgan','buyer',['Priority','Cash buyer']),('Olivia Bennett','seller',['Relocation']),('Theodore Brooks','buyer',['Investor']),('Charlotte Hayes','seller',['Luxury']),('Ethan Parker','buyer',['First-time buyer']),('Isabella Reed','seller',['Referral']),('Harbor Title Group','partner',['Title company']),('Summit Lending','partner',['Lender'])]):
        id=uid();contact_ids.append(id)
        await db.contacts.insert_one({'id':id,'name':name,'email':name.lower().replace(' ','.')+'@example.com','phone':'(305) 555-01'+str(i).zfill(2),'company':name if type=='partner' else '','type':type,'tags':tags,'notes':'Sample contact for your initial workspace. Replace with your real client details.','assigned_ids':[owner_id],'created_by':owner_id,'created_at':now()})
    properties=[('1248 Biscayne Boulevard','Miami','FL',1250000,'lead',0,'Single family'),('82 Palm Avenue','Coral Gables','FL',875000,'lead',3,'Townhouse'),('460 Ocean Drive','Miami Beach','FL',2450000,'appointment',1,'Single family'),('216 Sunset Lane','Fort Lauderdale','FL',685000,'appointment',4,'Condominium'),('1820 Bayview Terrace','Miami','FL',1850000,'contract',3,'Single family'),('95 Coral Way','Coral Gables','FL',1120000,'contract',5,'Townhouse'),('710 Harbor Point','Key Biscayne','FL',3200000,'closing',0,'Single family'),('38 Meridian Avenue','Miami Beach','FL',925000,'closing',1,'Condominium')]
    txs=[]
    for i,(address,city,state,value,stage,image,type) in enumerate(properties):
        tx_id=uid();contract=date.today()-timedelta(days=20 if i>=6 else 9 if i>=4 else 0);closing=date.today()+timedelta(days=3 if i==6 else 6 if i==7 else 16 if i>=4 else 30)
        tx={'id':tx_id,'address':address,'city':city,'state':state,'zip':'33139','value':value,'property_type':type,'stage_id':stage,'buyer_id':contact_ids[(i%3)*2],'seller_id':contact_ids[(i%3)*2+1],'agent':'Maya Chen' if i%2==0 else 'James Wilson','contract_date':contract.isoformat(),'contingency_date':(contract+timedelta(days=10)).isoformat(),'closing_date':closing.isoformat(),'assigned_ids':[owner_id],'client_ids':[],'image_url':IMAGES[image],'created_by':owner_id,'created_at':now(),'review_status':'pending' if i in [4,6] else 'not_submitted','required_documents':REQUIRED_DOCUMENTS,'sample':True}
        await db.transactions.insert_one(tx.copy());txs.append(tx)
        for j,(title,offset) in enumerate(TASK_TEMPLATE):
            await db.tasks.insert_one({'id':uid(),'transaction_id':tx_id,'title':title,'due_date':min(contract+timedelta(days=offset),closing).isoformat(),'assignee_id':owner_id,'completed':j<(6 if i>=6 else 3 if i>=4 else 1 if i>=2 else 0),'created_at':now()})
        if i in [4,6]:await db.reviews.insert_one({'id':uid(),'transaction_id':tx_id,'submitted_by':maya_id,'submitted_name':'Maya Chen','status':'pending','note':'Sample review: please check the outstanding documents before issuing approval.','created_at':now(),'decided_by':None,'decided_at':None})
    for i,(actor,name,text,kind) in enumerate([(maya_id,'Maya Chen','submitted 1820 Bayview Terrace for review','review'),(owner_id,'Ocean','completed order title','task'),(james_id,'James Wilson','updated the closing date for 710 Harbor Point','transaction'),(maya_id,'Maya Chen','added a note to 95 Coral Way','contact'),(owner_id,'Ocean','opened 460 Ocean Drive','transaction')]):
        tx=txs[4 if i<2 else 6 if i==2 else 5 if i==3 else 2]
        await db.activities.insert_one({'id':uid(),'actor_id':actor,'actor_name':name,'text':text,'transaction_id':tx['id'],'audience_ids':[owner_id],'kind':kind,'internal':True,'created_at':now()})
    for i in [4,6]:
        thread_id=uid();tx=txs[i]
        await db.threads.insert_one({'id':thread_id,'title':tx['address'],'transaction_id':tx['id'],'contact_id':None,'participant_ids':[owner_id,maya_id],'created_by':owner_id,'created_at':now(),'last_message':'The file is ready for your review. I’ve flagged the remaining documents.','last_message_at':now()})
        await db.messages.insert_one({'id':uid(),'thread_id':thread_id,'sender_id':maya_id,'sender_name':'Maya Chen','body':'The file is ready for your review. I’ve flagged the remaining documents.','mention_ids':[owner_id],'read_by':[maya_id],'created_at':now()})
        await db.notifications.insert_one({'id':uid(),'user_id':owner_id,'title':f'Maya Chen mentioned you in {tx["address"]}','link':f'/messages?thread={thread_id}','read':False,'created_at':now()})