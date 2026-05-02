import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../context/AuthContext'
import { authApi } from '../api/client'
import Logo from '../components/Logo'

const LANGUAGES = [
  { code: 'en', label: '🇬🇧 English' },
  { code: 'fr', label: '🇫🇷 Français' },
  { code: 'de', label: '🇩🇪 Deutsch' },
  { code: 'es', label: '🇪🇸 Español' },
  { code: 'ja', label: '🇯🇵 日本語' },
  { code: 'zh', label: '🇨🇳 中文' },
  { code: 'pt', label: '🇧🇷 Português' },
]

function EyeIcon({ open }) {
  return open
    ? <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
    : <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
}

function PwdField({ id, label, value, onChange }) {
  const [show, setShow] = useState(false)
  return (
    <div className="form-group">
      <label>{label}</label>
      <div style={{ position: 'relative' }}>
        <input type={show ? 'text' : 'password'} value={value} onChange={onChange} placeholder="••••••••••" style={{ paddingRight: 40 }}/>
        <button
          type="button"
          onClick={() => setShow(s => !s)}
          style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: show ? '#0A8C7C' : '#6B8099', display: 'flex' }}
        >
          <EyeIcon open={show}/>
        </button>
      </div>
    </div>
  )
}

export default function Login() {
  const { t, i18n } = useTranslation()
  const { login }   = useAuth()
  const navigate    = useNavigate()

  const [tab,      setTab]      = useState('signin')
  const [loading,  setLoading]  = useState(false)
  const [msg,      setMsg]      = useState(null)
  const [err,      setErr]      = useState(null)

  const [email,     setEmail]    = useState('')
  const [password,  setPassword] = useState('')
  const [confirm,   setConfirm]  = useState('')
  const [fullName,  setFullName] = useState('')
  const [lang,      setLang]     = useState('auto')

  const clear = () => { setMsg(null); setErr(null) }

  const handleSignIn = async e => {
    e.preventDefault(); clear(); setLoading(true)
    try {
      await login(email, password)
      navigate('/search')
    } catch (ex) {
      setErr(ex.response?.data?.detail || 'Sign in failed')
    } finally { setLoading(false) }
  }

  const handleRegister = async e => {
    e.preventDefault(); clear()
    if (password !== confirm) { setErr('Passwords do not match'); return }
    setLoading(true)
    try {
      await authApi.register({ full_name: fullName, email, password, language: lang })
      setMsg('✓ Account created! A welcome email has been sent. Please check your inbox.')
      setTab('signin')
    } catch (ex) {
      setErr(ex.response?.data?.detail || 'Registration failed')
    } finally { setLoading(false) }
  }

  const handleReset = async e => {
    e.preventDefault(); clear(); setLoading(true)
    try {
      await authApi.forgotPassword({ email })
      setMsg('✓ Reset link sent. Please check your email within 5 minutes.')
    } catch {
      setMsg('✓ If that email is registered you will receive a reset link.')
    } finally { setLoading(false) }
  }

  const switchTab = t => { setTab(t); clear() }

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'linear-gradient(135deg,#EDF5F7 0%,#F4F6F8 50%,#EBF3F5 100%)',
      padding: 24, position: 'relative', overflow: 'hidden',
    }}>
      {/* Background pattern */}
      <div style={{
        position: 'absolute', inset: 0, opacity: .035,
        backgroundImage: 'repeating-linear-gradient(60deg,transparent,transparent 40px,rgba(10,140,124,.8) 40px,rgba(10,140,124,.8) 41px),repeating-linear-gradient(-60deg,transparent,transparent 40px,rgba(10,140,124,.8) 40px,rgba(10,140,124,.8) 41px)',
      }}/>

      <div className="card" style={{ width: 460, maxWidth: '100%', padding: 40, position: 'relative', zIndex: 1 }}>
        {/* Header */}
        <div style={{ textAlign: 'center', marginBottom: 28 }}>
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 14 }}>
            <Logo size={44} textSize={22}/>
          </div>
          <div style={{ fontSize: 12, letterSpacing: '.12em', textTransform: 'uppercase', color: '#6B8099', fontWeight: 400 }}>
            {t('securePortal')}
          </div>
        </div>

        {/* Tabs */}
        <div style={{ display: 'flex', gap: 4, background: '#F4F6F8', borderRadius: 8, padding: 4, marginBottom: 22, border: '1px solid #DDE3E8' }}>
          {[['signin','signIn'],['register','createAccount'],['reset','resetPassword']].map(([key,lk]) => (
            <button key={key} onClick={() => switchTab(key)} style={{
              flex: 1, padding: '7px 4px', borderRadius: 6, border: 'none', cursor: 'pointer',
              background: tab===key ? '#0A8C7C' : 'none',
              color: tab===key ? '#fff' : '#6B8099',
              fontSize: 12, fontWeight: 500, transition: 'all .2s',
              boxShadow: tab===key ? '0 2px 6px rgba(10,140,124,.25)' : 'none',
            }}>{t(lk)}</button>
          ))}
        </div>

        {msg && <div className="alert-success">{msg}</div>}
        {err && <div className="alert-error">{err}</div>}

        {/* Sign In */}
        {tab === 'signin' && (
          <form onSubmit={handleSignIn}>
            <div className="form-group"><label>{t('email')}</label><input type="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="researcher@institution.edu" required/></div>
            <PwdField label={t('password')} value={password} onChange={e=>setPassword(e.target.value)}/>
            <div className="form-group">
              <label>{t('language')}</label>
              <select value={lang} onChange={e=>{setLang(e.target.value);if(e.target.value!=='auto')i18n.changeLanguage(e.target.value)}}>
                <option value="auto">🌐 Auto-detect {t('langDetected')}</option>
                {LANGUAGES.map(l=><option key={l.code} value={l.code}>{l.label}</option>)}
              </select>
            </div>
            <button type="submit" className="btn-primary" style={{ width: '100%', justifyContent: 'center', marginTop: 4 }} disabled={loading}>
              {loading ? <><span className="spinner" style={{width:16,height:16}}/> Signing in…</> : t('signInBtn')}
            </button>
            <div style={{ textAlign: 'center', marginTop: 14, fontSize: 13, color: '#6B8099' }}>
              <a onClick={() => switchTab('reset')} style={{ color: '#0A8C7C', cursor: 'pointer', fontWeight: 500 }}>{t('forgotPassword')}</a>
            </div>
          </form>
        )}

        {/* Register */}
        {tab === 'register' && (
          <form onSubmit={handleRegister}>
            <div className="form-group"><label>{t('fullName')}</label><input type="text" value={fullName} onChange={e=>setFullName(e.target.value)} placeholder="Dr. Jane Smith" required/></div>
            <div className="form-group"><label>{t('email')}</label><input type="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="jsmith@cancerresearch.org" required/></div>
            <PwdField label={t('password')} value={password} onChange={e=>setPassword(e.target.value)}/>
            <PwdField label={t('confirmPassword')} value={confirm} onChange={e=>setConfirm(e.target.value)}/>
            <button type="submit" className="btn-primary" style={{ width: '100%', justifyContent: 'center', marginTop: 4 }} disabled={loading}>
              {loading ? <><span className="spinner" style={{width:16,height:16}}/> Creating…</> : t('createBtn')}
            </button>
            <div style={{ textAlign: 'center', marginTop: 14, fontSize: 13, color: '#6B8099' }}>
              {t('alreadyHaveAccount')} <a onClick={() => switchTab('signin')} style={{ color: '#0A8C7C', cursor: 'pointer', fontWeight: 500 }}>{t('signIn')}</a>
            </div>
          </form>
        )}

        {/* Reset */}
        {tab === 'reset' && (
          <form onSubmit={handleReset}>
            <div className="form-group"><label>{t('email')}</label><input type="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="your@email.com" required/></div>
            <button type="submit" className="btn-primary" style={{ width: '100%', justifyContent: 'center', marginTop: 4 }} disabled={loading}>
              {loading ? <><span className="spinner" style={{width:16,height:16}}/> Sending…</> : t('sendResetBtn')}
            </button>
            <div style={{ textAlign: 'center', marginTop: 14, fontSize: 13, color: '#6B8099' }}>
              <a onClick={() => switchTab('signin')} style={{ color: '#0A8C7C', cursor: 'pointer', fontWeight: 500 }}>{t('backToSignIn')}</a>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}
