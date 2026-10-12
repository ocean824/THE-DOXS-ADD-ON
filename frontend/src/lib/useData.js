import {useState,useEffect,useCallback} from 'react';
import {api,errorText} from './api';
export function useData(path,initial=null){
 const [data,setData]=useState(initial),[loading,setLoading]=useState(true),[error,setError]=useState('');
 const reload=useCallback(async()=>{if(!path){setLoading(false);return;}try{const r=await api.get(path);setData(r.data);setError('');}catch(e){setError(errorText(e));}finally{setLoading(false);}},[path]);
 useEffect(()=>{reload();window.addEventListener('crm-refresh',reload);return()=>window.removeEventListener('crm-refresh',reload);},[reload]);
 return {data,loading,error,reload,setData};
}