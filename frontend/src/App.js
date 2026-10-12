import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './lib/auth';
import { Toaster } from './components/ui/sonner';
import { Shell } from './components/Shell';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Transactions from './pages/Transactions';
import TransactionDetail from './pages/TransactionDetail';
import Contacts from './pages/Contacts';
import Tasks from './pages/Tasks';
import Reviews from './pages/Reviews';
import Messages from './pages/Messages';
import Assistant from './pages/Assistant';
import Settings from './pages/Settings';
import Integrations from './pages/Integrations';
import Knowledge from './pages/Knowledge';
import Calendar from './pages/Calendar';
import './App.css';
function Protected(){const {user,loading}=useAuth(); if(loading)return <div className="boot" data-testid="app-loading"><span className="brand-serif">D.O.X</span><span className="loading-line"/></div>;return user?<Shell/>:<Navigate to="/login" replace/>;}
function Staff({children}){const {user}=useAuth();return user.role==='CLIENT'?<Navigate to="/" replace/>:children;}
function Owner({children}){const {user}=useAuth();return user.role==='OWNER'?children:<Navigate to="/" replace/>;}
export default function App(){return <BrowserRouter><AuthProvider><Routes><Route path="/login" element={<Login/>}/><Route path="/reset-password" element={<Login reset/>}/><Route element={<Protected/>}><Route index element={<Dashboard/>}/><Route path="/transactions" element={<Transactions/>}/><Route path="/transactions/:id" element={<TransactionDetail/>}/><Route path="/contacts" element={<Staff><Contacts/></Staff>}/><Route path="/tasks" element={<Staff><Tasks/></Staff>}/><Route path="/reviews" element={<Staff><Reviews/></Staff>}/><Route path="/messages" element={<Messages/>}/><Route path="/assistant" element={<Assistant/>}/><Route path="/knowledge" element={<Knowledge/>}/><Route path="/calendar" element={<Calendar/>}/><Route path="/settings" element={<Settings/>}/><Route path="/integrations" element={<Owner><Integrations/></Owner>}/></Route><Route path="*" element={<Navigate to="/" replace/>}/></Routes><Toaster theme="dark" position="bottom-right" richColors/></AuthProvider></BrowserRouter>;}