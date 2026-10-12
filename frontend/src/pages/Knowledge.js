import {useState} from 'react';
import {useNavigate} from 'react-router-dom';
import {BookOpen,Upload,FolderSync,Sparkles,FileText,ShieldCheck,KeyRound} from 'lucide-react';
import {toast} from 'sonner';
import {useAuth} from '../lib/auth';
import {useData} from '../lib/useData';
import {api,errorText,dateLabel} from '../lib/api';
import {PageHeader,Btn,Badge,Empty,Loading,ErrorState,Modal} from '../components/Common';
import {VaultUpload,VaultItems,VaultGrants,VaultSyncTools} from '../components/KnowledgePanels';
export const scopeColor=s=>s==='shared'?'blue':'gold';
export default function Knowledge(){
 const {user}=useAuth(),owner=user.role==='OWNER',navigate=useNavigate();
 const {data:access,loading,error,reload}=useData('/knowledge/access'),{data:txs=[]}=useData('/transactions',[]);
 const [tab,setTab]=useState('items'),[upload,setUpload]=useState(false),[preview,setPreview]=useState(null);
 const openItem=async item=>{try{const r=await api.get(`/knowledge/items/${item.id}`);setPreview(r.data);}catch(e){toast.error(errorText(e));}};
 const items=access?.items||[];
 return <><PageHeader eyebrow="WHAT YOUR TEAM KNOWS. WHO IS ALLOWED TO ASK." title="Knowledge vault" subtitle={owner?'Obsidian notes, Office documents and playbooks the assistant may draw on — scoped per person.':'Approved knowledge you can ask the assistant about.'}>{owner&&<Btn id="vault-upload-button" onClick={()=>setUpload(true)}><Upload/>Add files</Btn>}<Btn secondary id="vault-ask-button" onClick={()=>navigate('/assistant?template=knowledge')}><Sparkles/>Ask the vault</Btn></PageHeader>
 {loading?<Loading/>:error?<ErrorState error={error} retry={reload}/>:<>
 <div className="vault-stats">{[['Shared library',access.shared_items,'Approved for everyone with a library grant'],['Project knowledge',access.project_items,owner?'Linked to a transaction and its project type':'Only for projects you are actively on'],[owner?'Vault items':'Your access grants',owner?items.length:access.grants,owner?'Everything in the vault':'Approved by the owner or relayed through Hermes']].map(([label,value,sub],i)=><div className="vault-stat" key={label} data-testid={`vault-stat-${i}`}><span>{label}</span><strong>{value}</strong><small>{sub}</small></div>)}</div>
 {owner?<><div className="tabs">{[['items','Vault items'],['grants','Access grants'],['sync','Sync tools']].map(([id,label])=><button key={id} data-testid={`vault-tab-${id}`} className={tab===id?'active':''} onClick={()=>setTab(id)}>{label}</button>)}</div>
 {tab==='items'&&<VaultItems items={items} txs={txs} onOpen={openItem}/>}{tab==='grants'&&<VaultGrants/>}{tab==='sync'&&<VaultSyncTools/>}</>
 :<><div className="notice-strip" style={{marginBottom:22}}><ShieldCheck size={16}/><span>The assistant only answers from items listed here. Project notes appear while you are actively assigned to that transaction.</span></div>
 {items.length?<div className="vault-list">{items.map(i=><button key={i.id} data-testid={`vault-item-${i.id}`} className="vault-row" onClick={()=>openItem(i)}><FileText size={15}/><div className="vault-row-main"><strong>{i.title}</strong><small>{i.path}</small></div><Badge color={scopeColor(i.scope)}>{i.scope}</Badge>{i.transaction_id&&<small className="vault-tx">{txs.find(t=>t.id===i.transaction_id)?.address||'Linked project'}</small>}<small>{dateLabel(i.updated_at)}</small></button>)}</div>
 :<Empty title="No knowledge approved for you yet" text="Ask the owner to grant you library or project access."><KeyRound size={14}/></Empty>}</>}</>}
 <VaultUpload open={upload} onClose={()=>setUpload(false)} txs={txs}/>
 <Modal open={!!preview} onClose={()=>setPreview(null)} title={preview?.title||''} description={preview?.path} id="vault-preview-modal"><div style={{display:'flex',gap:8,marginBottom:12}}><Badge color={scopeColor(preview?.scope)}>{preview?.scope}</Badge><Badge color="neutral">{preview?.format}</Badge></div><pre className="code-block" data-testid="vault-preview-content" style={{maxHeight:420,whiteSpace:'pre-wrap'}}>{preview?.content}</pre></Modal></>;
}
