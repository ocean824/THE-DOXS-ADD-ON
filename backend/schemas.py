from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import Literal, Optional

Role = Literal['OWNER','TEAM_MEMBER','CLIENT']
class Model(BaseModel):
    model_config = ConfigDict(extra='forbid')
class OK(Model):
    message: str
class UserOut(Model):
    id: str
    name: str
    email: str
    role: Role
    active: bool = True
    notification_preferences: dict = Field(default_factory=lambda:{'messages':True,'tasks':True,'mentions':True})
    created_at: str
class LoginIn(Model):
    email: EmailStr
    password: str = Field(min_length=1,max_length=72)
    client: Literal['web','desktop'] = 'web'
class AuthOut(Model):
    user: UserOut
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_type: str = 'bearer'
    expires_in: int = 900
class RefreshIn(Model):
    refresh_token: Optional[str] = None
class ForgotIn(Model): email: EmailStr
class ResetIn(Model):
    token: str
    password: str = Field(min_length=12,max_length=72)
class PasswordIn(Model):
    current_password: str
    new_password: str = Field(min_length=12,max_length=72)
class UserIn(Model):
    name: str = Field(min_length=2,max_length=80)
    email: EmailStr
    role: Role
    password: str = Field(min_length=12,max_length=72)
class UserPatch(Model):
    role: Optional[Role] = None
    active: Optional[bool] = None
class Preferences(Model):
    messages: bool = True
    tasks: bool = True
    mentions: bool = True
class ContactIn(Model):
    name: str = Field(min_length=2,max_length=100)
    email: EmailStr
    phone: str = Field(default='',max_length=30)
    type: Literal['buyer','seller','partner'] = 'buyer'
    company: str = Field(default='',max_length=100)
    tags: list[str] = Field(default_factory=list,max_length=12)
    notes: str = Field(default='',max_length=5000)
    assigned_ids: list[str] = Field(default_factory=list,max_length=20)
class ContactOut(ContactIn):
    id: str
    created_at: str
    created_by: str
class StageIn(Model):
    name: str = Field(min_length=2,max_length=35)
    color: str = Field(pattern='^#[0-9a-fA-F]{6}$')
class StageOut(StageIn):
    id: str
    position: int
class TransactionIn(Model):
    address: str = Field(min_length=3,max_length=150)
    city: str = Field(min_length=2,max_length=100)
    state: str = Field(default='',max_length=50)
    zip: str = Field(default='',max_length=15)
    value: float = Field(ge=0,le=10000000000)
    property_type: Literal['Single family','Condominium','Townhouse','Commercial','Land'] = 'Single family'
    stage_id: str = 'lead'
    buyer_id: Optional[str] = None
    seller_id: Optional[str] = None
    agent: str = Field(default='',max_length=100)
    contract_date: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
    contingency_date: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
    closing_date: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
    assigned_ids: list[str] = Field(default_factory=list,max_length=20)
    client_ids: list[str] = Field(default_factory=list,max_length=20)
    image_url: str = Field(default='',max_length=1000)
class TransactionOut(TransactionIn):
    id: str
    created_at: str
    created_by: str
    review_status: str = 'not_submitted'
    required_documents: list[str] = []
    sample: bool = False
class TransactionPatch(Model):
    stage_id: Optional[str] = None
    assigned_ids: Optional[list[str]] = None
    client_ids: Optional[list[str]] = None
    closing_date: Optional[str] = Field(default=None,pattern=r'^\d{4}-\d{2}-\d{2}$')
class TaskOut(Model):
    id: str
    transaction_id: str
    title: str
    due_date: str
    assignee_id: str
    completed: bool
    created_at: str
class TaskIn(Model):
    title: str = Field(min_length=2,max_length=150)
    due_date: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
    assignee_id: str
class TaskPatch(Model):
    completed: Optional[bool] = None
    due_date: Optional[str] = Field(default=None,pattern=r'^\d{4}-\d{2}-\d{2}$')
    assignee_id: Optional[str] = None
class DocumentOut(Model):
    id: str
    transaction_id: str
    filename: str
    content_type: str
    size: int
    category: str
    visibility: Literal['internal','client']
    uploaded_by: str
    uploaded_by_name: str = ''
    client_submitted: bool = False
    created_at: str
class ReviewOut(Model):
    id: str
    transaction_id: str
    submitted_by: str
    submitted_name: str
    status: str
    note: str
    created_at: str
    decided_by: Optional[str] = None
    decided_at: Optional[str] = None
class ReviewIn(Model): note: str = Field(default='',max_length=3000)
class DecisionIn(Model):
    decision: Literal['approved','rejected','revision_requested']
    note: str = Field(default='',max_length=3000)
class CommentIn(Model): body: str = Field(min_length=1,max_length=3000)
class ReviewCommentOut(Model):
    id: str
    review_id: str
    transaction_id: str
    author_id: str
    author_name: str
    body: str
    created_at: str
class ThreadIn(Model):
    title: str = Field(min_length=2,max_length=150)
    transaction_id: Optional[str] = None
    contact_id: Optional[str] = None
    participant_ids: list[str] = Field(min_length=1,max_length=30)
class ThreadOut(ThreadIn):
    id: str
    created_by: str
    created_at: str
    last_message: str = ''
    last_message_at: str = ''
    unread: int = 0
class MessageIn(Model):
    body: str = Field(min_length=1,max_length=5000)
    mention_ids: list[str] = Field(default_factory=list,max_length=30)
class MessageOut(MessageIn):
    id: str
    thread_id: str
    sender_id: str
    sender_name: str
    read_by: list[str]
    created_at: str
class AIIn(Model):
    template: Literal['draft_email','summarize','closing_recap','missing_items','knowledge']
    transaction_id: Optional[str] = None
    prompt: str = Field(default='',max_length=2000)
PropertyType = Literal['Single family','Condominium','Townhouse','Commercial','Land']
KnowledgeScope = Literal['project','shared']
class KnowledgeRules(Model):
    enabled: bool = False
    roles: list[Literal['TEAM_MEMBER','CLIENT']] = Field(default_factory=lambda:['TEAM_MEMBER'])
    scopes: list[KnowledgeScope] = Field(default_factory=lambda:['project'])
    project_types: list[PropertyType] = Field(default_factory=lambda:['Single family','Condominium','Townhouse','Commercial','Land'])
    path_prefixes: list[str] = Field(default_factory=list,max_length=30)
class SettingsIn(Model):
    team_daily_limit: int = Field(ge=0,le=10000)
    client_daily_limit: int = Field(ge=0,le=10000)
    autonomous_approvals: bool = False
    autonomous_max_value: float = Field(ge=0,le=1000000000)
    knowledge_rules: KnowledgeRules = Field(default_factory=KnowledgeRules)
class KnowledgeFileIn(Model):
    path: str = Field(min_length=1,max_length=400)
    content: str = Field(max_length=36000000)
    encoding: Literal['text','base64'] = 'text'
class KnowledgeSyncIn(Model):
    items: list[KnowledgeFileIn] = Field(min_length=1,max_length=100)
    scope: KnowledgeScope = 'shared'
    transaction_id: Optional[str] = None
    project_type: Optional[PropertyType] = None
    tags: list[str] = Field(default_factory=list,max_length=12)
    deleted_paths: list[str] = Field(default_factory=list,max_length=500)
class KnowledgeSyncOut(Model):
    created: int
    updated: int
    unchanged: int
    deleted: int
class KnowledgeItemPatch(Model):
    scope: Optional[KnowledgeScope] = None
    transaction_id: Optional[str] = None
    project_type: Optional[PropertyType] = None
    tags: Optional[list[str]] = Field(default=None,max_length=12)
class KnowledgeItemOut(Model):
    id: str
    path: str
    title: str
    scope: KnowledgeScope
    transaction_id: Optional[str] = None
    project_type: Optional[PropertyType] = None
    tags: list[str] = []
    size: int
    format: str = 'md'
    source: str
    content_hash: str
    created_by: str
    created_at: str
    updated_at: str
class KnowledgeItemDetail(KnowledgeItemOut): content: str
class GrantIn(Model):
    user_id: str
    scope: KnowledgeScope
    path_prefix: str = Field(default='',max_length=400)
    project_types: list[PropertyType] = Field(default_factory=list)
    note: str = Field(default='',max_length=1000)
    expires_at: Optional[str] = Field(default=None,pattern=r'^\d{4}-\d{2}-\d{2}$')
class GrantOut(GrantIn):
    id: str
    user_name: str
    granted_by: str
    granted_by_name: str
    authority: str
    active: bool
    created_at: str
    revoked_at: Optional[str] = None
class HermesGrant(GrantIn):
    confirmation_token: Optional[str] = None
    idempotency_key: str = Field(min_length=8,max_length=100)
class GrantConfirmationIn(GrantIn): pass
class KnowledgeAccessOut(Model):
    shared_items: int
    project_items: int
    grants: int
    items: list[KnowledgeItemOut]
MeetingResponse = Literal['pending','accepted','declined']
class MeetingIn(Model):
    transaction_id: str
    title: str = Field(min_length=2,max_length=150)
    starts_at: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$')
    duration_minutes: int = Field(default=30,ge=15,le=480)
    location: str = Field(default='',max_length=200)
    notes: str = Field(default='',max_length=2000)
    participant_ids: list[str] = Field(default_factory=list,max_length=30)
class MeetingPatch(Model):
    title: Optional[str] = Field(default=None,min_length=2,max_length=150)
    starts_at: Optional[str] = Field(default=None,pattern=r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$')
    duration_minutes: Optional[int] = Field(default=None,ge=15,le=480)
    location: Optional[str] = Field(default=None,max_length=200)
    notes: Optional[str] = Field(default=None,max_length=2000)
    status: Optional[Literal['cancelled']] = None
class MeetingOut(MeetingIn):
    id: str
    organizer_id: str
    organizer_name: str
    status: Literal['scheduled','cancelled'] = 'scheduled'
    responses: dict[str,MeetingResponse] = {}
    created_at: str
class RespondIn(Model): response: Literal['accepted','declined']
class SettingsOut(SettingsIn): id: str
class ServiceKeyIn(Model): service: Literal['hermes','dox']
class ServiceKeyOut(Model):
    key: str
    service: str
    scopes: list[str]
class HermesDecision(DecisionIn):
    review_id: str
    confirmation_token: Optional[str] = None
    idempotency_key: str = Field(min_length=8,max_length=100)
class ConfirmationIn(DecisionIn): pass
class ConfirmationOut(Model):
    confirmation_token: str
    expires_in: int
class ActivityOut(Model):
    id: str
    actor_id: str
    actor_name: str
    text: str
    transaction_id: Optional[str]
    audience_ids: list[str]
    kind: str
    internal: bool
    created_at: str
class NotificationOut(Model):
    id: str
    user_id: str
    title: str
    link: str
    read: bool
    created_at: str
class AILogOut(Model):
    id: str
    user_id: str
    user_name: str
    template: str
    transaction_id: Optional[str] = None
    prompt: str
    response: str
    status: str
    knowledge_ids: list[str] = []
    created_at: str