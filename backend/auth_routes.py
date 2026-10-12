import bcrypt, secrets, time, asyncio
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Request, Response, HTTPException
from pymongo import ReturnDocument
import jwt
from core import db, SECRET, ORIGIN, uid, digest, now, require
from schemas import AuthOut, UserOut, LoginIn, RefreshIn, ForgotIn, ResetIn, PasswordIn, OK
from email_service import send_reset

router=APIRouter(prefix='/api/auth',tags=['Authentication'])
async def hash_password(password):
    if len(password.encode())>72: raise HTTPException(422,'Password must be at most 72 UTF-8 bytes')
    return (await asyncio.to_thread(bcrypt.hashpw,password.encode(),bcrypt.gensalt())).decode()
async def valid_password(password, hashed):
    if len(password.encode())>72: return False
    return await asyncio.to_thread(bcrypt.checkpw,password.encode(),hashed.encode())
async def throttle(key, maximum, seconds):
    slot=int(time.time())//seconds
    record=await db.rate_limits.find_one_and_update({'id':f'{key}:{slot}'},{'$inc':{'count':1},'$setOnInsert':{'expires':datetime.now(timezone.utc)+timedelta(seconds=seconds*2)}},upsert=True,return_document=ReturnDocument.AFTER)
    if record['count']>maximum: raise HTTPException(429,'Too many attempts. Please try again later')
def access_token(user_id, session_id):
    return jwt.encode({'sub':user_id,'sid':session_id,'type':'access','iat':int(time.time()),'exp':int(time.time())+900,'iss':'dox-workspace','aud':'dox-api'},SECRET,algorithm='HS256')
def set_cookies(response, access, refresh):
    response.set_cookie('dox_access',access,httponly=True,secure=True,samesite='lax',max_age=900,path='/api')
    response.set_cookie('dox_refresh',refresh,httponly=True,secure=True,samesite='lax',max_age=604800,path='/api/auth')
def clear_cookies(response):
    response.delete_cookie('dox_access',path='/api',secure=True,samesite='lax')
    response.delete_cookie('dox_refresh',path='/api/auth',secure=True,samesite='lax')
@router.post('/login',response_model=AuthOut)
async def login(data: LoginIn,request:Request,response:Response):
    await throttle('login:'+data.email.lower(),10,900)
    user=await db.users.find_one({'email':data.email.lower(),'active':True},{'_id':0})
    if not user or not await valid_password(data.password,user['password_hash']): raise HTTPException(401,'Email or password is incorrect')
    sid=uid(); refresh=secrets.token_urlsafe(48)
    await db.sessions.insert_one({'id':sid,'user_id':user['id'],'refresh_hash':digest(refresh),'client':data.client,'revoked':False,'expires':datetime.now(timezone.utc)+timedelta(days=7),'created_at':now()})
    access=access_token(user['id'],sid)
    if data.client=='web': set_cookies(response,access,refresh)
    return AuthOut(user=UserOut(**{k:v for k,v in user.items() if k!='password_hash'}),access_token=access if data.client=='desktop' else None,refresh_token=refresh if data.client=='desktop' else None)
@router.post('/refresh',response_model=AuthOut)
async def refresh(data:RefreshIn,request:Request,response:Response):
    token=data.refresh_token or request.cookies.get('dox_refresh')
    if not data.refresh_token and request.headers.get('origin') != ORIGIN: raise HTTPException(403,'Invalid request origin')
    if not token: raise HTTPException(401,'Please sign in')
    new=secrets.token_urlsafe(48)
    session=await db.sessions.find_one_and_update({'refresh_hash':digest(token),'revoked':False,'expires':{'$gt':datetime.now(timezone.utc)}},{'$set':{'refresh_hash':digest(new)}},projection={'_id':0})
    if not session: raise HTTPException(401,'Session expired')
    user=await db.users.find_one({'id':session['user_id'],'active':True},{'_id':0,'password_hash':0})
    if not user: raise HTTPException(401,'Account unavailable')
    access=access_token(user['id'],session['id'])
    if session['client']=='web': set_cookies(response,access,new)
    return AuthOut(user=UserOut(**user),access_token=access if session['client']=='desktop' else None,refresh_token=new if session['client']=='desktop' else None)
@router.get('/me',response_model=UserOut)
async def me(user=Depends(require('read'))): return {k:v for k,v in user.items() if not k.startswith('_')}
@router.post('/logout',response_model=OK)
async def logout(response:Response,user=Depends(require('read'))):
    await db.sessions.update_one({'id':user['_session_id']},{'$set':{'revoked':True}})
    clear_cookies(response)
    return {'message':'Signed out'}
@router.post('/forgot-password',response_model=OK)
async def forgot(data:ForgotIn):
    await throttle('reset:'+data.email.lower(),3,1800)
    user=await db.users.find_one({'email':data.email.lower(),'active':True},{'_id':0})
    if user:
        token=secrets.token_urlsafe(40)
        await db.password_resets.insert_one({'token_hash':digest(token),'user_id':user['id'],'used':False,'expires':datetime.now(timezone.utc)+timedelta(minutes=30)})
        await send_reset(user,token)
    return {'message':'If that email belongs to an account, a reset link has been sent.'}
@router.post('/reset-password',response_model=OK)
async def reset(data:ResetIn):
    record=await db.password_resets.find_one_and_update({'token_hash':digest(data.token),'used':False,'expires':{'$gt':datetime.now(timezone.utc)}},{'$set':{'used':True}},projection={'_id':0})
    if not record: raise HTTPException(400,'Reset link is invalid or expired')
    await db.users.update_one({'id':record['user_id']},{'$set':{'password_hash':await hash_password(data.password)}})
    await db.sessions.update_many({'user_id':record['user_id']},{'$set':{'revoked':True}})
    return {'message':'Password updated. Please sign in.'}
@router.post('/change-password',response_model=OK)
async def change_password(data:PasswordIn,response:Response,user=Depends(require('read'))):
    record=await db.users.find_one({'id':user['id']},{'_id':0})
    if not await valid_password(data.current_password,record['password_hash']): raise HTTPException(400,'Current password is incorrect')
    await db.users.update_one({'id':user['id']},{'$set':{'password_hash':await hash_password(data.new_password)}})
    await db.sessions.update_many({'user_id':user['id']},{'$set':{'revoked':True}})
    clear_cookies(response)
    return {'message':'Password changed. Sign in with your new password.'}