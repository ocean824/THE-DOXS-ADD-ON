from fastapi import APIRouter, Depends, HTTPException
from core import db, now, require, Repo, activity, authorize
from schemas import ReviewOut,ReviewIn,DecisionIn,CommentIn,ReviewCommentOut
router=APIRouter(prefix='/api',tags=['Reviews'])
async def compliance(repo,tx):
    tasks=await repo.list('tasks',{'transaction_id':tx['id']})
    documents=await repo.list('documents',{'transaction_id':tx['id'],'is_deleted':False})
    missing=[d for d in tx['required_documents'] if d not in [x['category'] for x in documents]]
    return tasks,documents,missing
@router.get('/reviews',response_model=list[ReviewOut])
async def reviews(user=Depends(require('internal'))):return await Repo(user).list('reviews',sort=('created_at',-1))
@router.post('/transactions/{id}/reviews',response_model=ReviewOut,status_code=201)
async def submit(id:str,data:ReviewIn,user=Depends(require('write'))):
    repo=Repo(user);tx=await repo.get('transactions',id)
    existing=await repo.list('reviews',{'transaction_id':id,'status':'pending'})
    if existing: raise HTTPException(409,'This transaction already has a pending review')
    record=await repo.insert('reviews',{'transaction_id':id,'submitted_by':user['id'],'submitted_name':user['name'],'status':'pending','note':data.note,'decided_by':None,'decided_at':None})
    await repo.update('transactions',id,{'review_status':'pending'})
    await activity(user,f'submitted {tx["address"]} for review',tx,'review')
    return record
@router.get('/reviews/{id}',response_model=ReviewOut)
async def get_review(id:str,user=Depends(require('internal'))):return await Repo(user).get('reviews',id)
async def decide_review(id,data,user,via='workspace'):
    repo=Repo(user);review=await repo.get('reviews',id);tx=await repo.get('transactions',review['transaction_id'])
    await authorize(user,'approvals:decide' if user.get('principal_type')=='service' else 'review',review)
    if review['submitted_by'] in [user['id'],user.get('_confirmed_owner_id')]:raise HTTPException(403,'The submitter cannot approve their own review; use another owner account')
    if review['status']!='pending':raise HTTPException(409,'This review already has a decision')
    if data.decision!='approved' and not data.note.strip():raise HTTPException(422,'A note is required when rejecting or requesting revision')
    values={'status':data.decision,'decided_by':user['id'],'decided_at':now()}
    result=await db.reviews.update_one(await repo.query('reviews',{'id':id,'status':'pending'}),{'$set':values})
    if not result.modified_count:raise HTTPException(409,'This review already has a decision')
    await repo.update('transactions',tx['id'],{'review_status':data.decision})
    await repo.insert('review_comments',{'review_id':id,'transaction_id':tx['id'],'author_id':user['id'],'author_name':user['name'],'body':f'{data.decision.replace("_"," ").capitalize()} via {via}. {data.note}'.strip()})
    await activity(user,f'{data.decision.replace("_"," ")} review for {tx["address"]}',tx,'review')
    return {**review,**values}
@router.post('/reviews/{id}/decision',response_model=ReviewOut)
async def decision(id:str,data:DecisionIn,user=Depends(require('review'))):return await decide_review(id,data,user)
@router.get('/reviews/{id}/comments',response_model=list[ReviewCommentOut])
async def comments(id:str,user=Depends(require('internal'))):
    repo=Repo(user);await repo.get('reviews',id);return await repo.list('review_comments',{'review_id':id},sort=('created_at',1))
@router.post('/reviews/{id}/comments',response_model=ReviewCommentOut,status_code=201)
async def comment(id:str,data:CommentIn,user=Depends(require('write'))):
    repo=Repo(user);review=await repo.get('reviews',id)
    record=await repo.insert('review_comments',{'review_id':id,'transaction_id':review['transaction_id'],'author_id':user['id'],'author_name':user['name'],'body':data.body})
    await activity(user,'commented on a transaction review',await repo.get('transactions',review['transaction_id']),'review');return record