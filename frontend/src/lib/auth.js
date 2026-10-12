import { createContext,useContext,useState,useEffect } from 'react';
import { api } from './api';
const AuthContext=createContext(null);
export function AuthProvider({children}){
 const [user,setUser]=useState(null),[loading,setLoading]=useState(true);
 useEffect(()=>{let alive=true;(async()=>{try{const r=await api.get('/auth/me');if(alive)setUser(r.data);}catch(e){try{const r=await api.post('/auth/refresh',{});if(alive)setUser(r.data.user);}catch(ignore){}}finally{if(alive)setLoading(false);}})();const expired=()=>setUser(null);window.addEventListener('session-expired',expired);return()=>{alive=false;window.removeEventListener('session-expired',expired);};},[]);
 const login=async(email,password)=>{const r=await api.post('/auth/login',{email,password});setUser(r.data.user);};
 const logout=async()=>{try{await api.post('/auth/logout');}finally{setUser(null);}};
 return <AuthContext.Provider value={{user,setUser,loading,login,logout}}>{children}</AuthContext.Provider>;
}
export const useAuth=()=>useContext(AuthContext);