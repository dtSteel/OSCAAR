import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './context/AuthContext'
import Layout from './components/Layout'
import Login       from './pages/Login'
import Search      from './pages/Search'
import Documents   from './pages/Documents'
import Admin       from './pages/Admin'
import Profile     from './pages/Profile'
import EmailPreview from './pages/EmailPreview'

function Protected({ children, adminOnly = false }) {
  const { user, loading } = useAuth()
  if (loading) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh' }}>
      <div className="spinner" style={{ width: 32, height: 32 }}/>
    </div>
  )
  if (!user) return <Navigate to="/login" replace/>
  if (adminOnly && user.role !== 'admin') return <Navigate to="/search" replace/>
  return <Layout>{children}</Layout>
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login/>}/>
        <Route path="/search"   element={<Protected><Search/></Protected>}/>
        <Route path="/documents" element={<Protected><Documents/></Protected>}/>
        <Route path="/email"    element={<Protected><EmailPreview/></Protected>}/>
        <Route path="/admin"    element={<Protected adminOnly><Admin/></Protected>}/>
        <Route path="/profile"  element={<Protected><Profile/></Protected>}/>
        <Route path="*"         element={<Navigate to="/search" replace/>}/>
      </Routes>
    </BrowserRouter>
  )
}
