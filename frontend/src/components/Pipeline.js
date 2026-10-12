import {Plus} from 'lucide-react';
import {toast} from 'sonner';
import {useAuth} from '../lib/auth';
import {TransactionCard} from './TransactionCard';
import {api,errorText,money,refreshData} from '../lib/api';
export const Pipeline=({transactions,stages,tasks,onAdd,limit})=>{
 const {user}=useAuth();const move=async(e,stage)=>{e.preventDefault();const id=e.dataTransfer.getData('transaction');if(!id||user.role==='CLIENT')return;try{await api.patch(`/transactions/${id}`,{stage_id:stage});refreshData();toast.success('Pipeline stage updated');}catch(e){toast.error(errorText(e));}};
 return <div className={`pipeline-board ${stages.length>4?'custom-stages':''}`} data-testid="pipeline-board">{stages.map(s=>{const items=transactions.filter(t=>t.stage_id===s.id);return <section key={s.id} className="pipeline-stage" data-testid={`pipeline-stage-${s.id}`} onDragOver={e=>e.preventDefault()} onDrop={e=>move(e,s.id)} style={{'--stage-color':s.color}}><div className="stage-heading"><i className="stage-dot"/><strong>{s.name}</strong><span className="stage-count">{items.length.toString().padStart(2,'0')}</span><span className="stage-total">{money(items.reduce((n,t)=>n+t.value,0),true)}</span></div>{items.slice(0,limit||items.length).map(t=><TransactionCard key={t.id} transaction={t} tasks={tasks}/>)}{user.role!=='CLIENT'&&<button className="add-stage-item" data-testid={`add-transaction-${s.id}`} onClick={()=>onAdd(s.id)}><Plus size={12}/>Add transaction</button>}{items.length===0&&user.role==='CLIENT'&&<p className="sample-label">No transactions</p>}</section>;})}</div>;
};