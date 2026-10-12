import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI,Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse,HTMLResponse
from fastapi.openapi.docs import get_swagger_ui_html
from core import client,ORIGIN,require
from seed import seed
from document_routes import init_storage
from auth_routes import router as auth
from crm_routes import router as crm
from document_routes import router as documents
from review_routes import router as reviews
from message_routes import router as messages
from ai_routes import router as ai
from integration_routes import router as integrations
from knowledge_routes import router as knowledge
from calendar_routes import router as calendar

logging.basicConfig(level=logging.INFO)
@asynccontextmanager
async def lifespan(app):
    await seed()
    try:await init_storage()
    except Exception:logging.warning('Object storage unavailable at startup; upload will retry initialization')
    yield
    client.close()
app=FastAPI(title='D.O.X Workspace API',version='1.0.0',description='Single source of truth for D.O.X Workspace, Hermes and Traycer. Web clients use Secure HttpOnly cookies; desktop clients request bearer tokens with client=desktop. Every domain endpoint enforces current database roles and relationship visibility. Clients have view-only transaction/document/thread access. Invalid authentication: 401; forbidden role: 403; invisible object: 404; validation: 422; conflict: 409; limits: 429. AI and events use SSE.',docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=[ORIGIN],allow_credentials=True,allow_methods=['GET','POST','PUT','PATCH','DELETE','OPTIONS'],allow_headers=['Content-Type','Authorization'])
@app.middleware('http')
async def headers(request,call_next):
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    response.headers['Strict-Transport-Security']='max-age=31536000; includeSubDomains'
    if not request.url.path.endswith('/events'):response.headers['Cache-Control']='no-store'
    return response
for router in (auth,crm,documents,reviews,messages,ai,integrations,knowledge,calendar):app.include_router(router)
@app.get('/api/health',tags=['Service health'])
async def health():return {'status':'ok','service':'dox-workspace'}
@app.get('/api/openapi.json',include_in_schema=False)
async def openapi(user=Depends(require('read'))):return JSONResponse(app.openapi())
@app.get('/api/docs',include_in_schema=False)
async def docs(user=Depends(require('read'))):return get_swagger_ui_html(openapi_url='/api/openapi.json',title='D.O.X Workspace · API reference')