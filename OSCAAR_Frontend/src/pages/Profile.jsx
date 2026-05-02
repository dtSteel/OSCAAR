import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { authApi } from '../api/client'
import { useAuth } from '../context/AuthContext'

const LANGUAGES = [
  { code: 'en', label: '🇬🇧 English' },
  { code: 'fr', label: '🇫🇷 Français' },
  { code: 'de', label: '🇩🇪 Deutsch' },
  { code: 'es', label: '🇪🇸 Español' },
  { code: 'ja', label: '🇯🇵 日本語' },
  { code: 'zh', label: '🇨🇳 中文' },
  { code: 'pt', label: '🇧🇷 Português' },
]

export default function Profile() {
  const { t, i18n } = useTranslation()
  const { user, refreshUser } = useAuth()

  const [current,  setCurrent]  = useState('')
  const [newPwd,   setNewPwd]   = useState('')
  const [confirm,  setConfirm]  = useState('')
  const [lang,     setLang]     = useState(user?.language || 'en')
  const [loading,  setLoading]  = useState(false)
  const [pwdMsg,   setPwdMsg]   = useState(null)
  const [langMsg,  setLangMsg]  = useState(null)
  const [error,    setError]    = useState(null)

  const handlePasswordChange = async e => {
    e.preventDefault()
    if (newPwd !== confirm) { setError('Passwords do not match'); return }
    setLoading(true); setError(null); setPwdMsg(null)
    try {
      await authApi.changePassword({ current_password: current, new_password: newPwd })
      setPwdMsg('✓ Password changed successfully')
      setCurrent(''); setNewPwd(''); setConfirm('')
    } catch (ex) {
      setError(ex.response?.data?.detail || 'Password change failed')
    } finally { setLoading(false) }
  }

  const handleLanguageChange = async () => {
    setLoading(true); setLangMsg(null); setError(null)
    try {
      await authApi.updateLanguage({ language: lang })
      await refreshUser()
      i18n.changeLanguage(lang)
      setLangMsg('✓ Language updated')
    } catch {
      setError('Failed to update language')
    } finally { setLoading(false) }
  }

  const initials = user?.full_name?.split(' ').map(n=>n[0]).join('').slice(0,2).toUpperCase() || 'U'

  return (
    <div style={{ maxWidth: 600 }}>
      <h2 style={{ fontFamily: "'DM Serif Display',serif", fontSize: 26, color: '#1A2733', marginBottom: 28 }}>
        {t('profile')}
      </h2>

      {/* User info card */}
      <div className="card" style={{ padding: 24, marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 20 }}>
          <div style={{ width: 56, height: 56, borderRadius: '50%', background: '#0A8C7C', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, fontWeight: 700, color: '#fff' }}>
            {initials}
          </div>
          <div>
            <div style={{ fontSize: 18, fontWeight: 600, color: '#1A2733' }}>{user?.full_name}</div>
            <div style={{ fontSize: 14, color: '#6B8099' }}>{user?.email}</div>
            <span className={`badge ${user?.role === 'admin' ? 'badge-gold' : 'badge-teal'}`} style={{ marginTop: 6 }}>
              {user?.role}
            </span>
          </div>
        </div>
        <div style={{ borderTop: '1px solid #F0F3F5', paddingTop: 16 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, fontSize: 13 }}>
            <div><span style={{ color: '#6B8099' }}>Account created</span><br/><span style={{ color: '#1A2733', fontWeight: 500 }}>{user?.created_at ? new Date(user.created_at).toLocaleDateString() : '—'}</span></div>
            <div><span style={{ color: '#6B8099' }}>Last login</span><br/><span style={{ color: '#1A2733', fontWeight: 500 }}>{user?.last_login_at ? new Date(user.last_login_at).toLocaleDateString() : 'First login'}</span></div>
          </div>
        </div>
      </div>

      {/* Language */}
      <div className="card" style={{ padding: 24, marginBottom: 24 }}>
        <h3 style={{ fontSize: 16, fontWeight: 600, color: '#1A2733', marginBottom: 16 }}>Language preference</h3>
        {langMsg && <div className="alert-success">{langMsg}</div>}
        <div className="form-group">
          <label>{t('language')}</label>
          <select value={lang} onChange={e => setLang(e.target.value)}>
            {LANGUAGES.map(l => <option key={l.code} value={l.code}>{l.label}</option>)}
          </select>
        </div>
        <button className="btn-primary" onClick={handleLanguageChange} disabled={loading}>
          {t('saveChanges')}
        </button>
      </div>

      {/* Change password */}
      <div className="card" style={{ padding: 24 }}>
        <h3 style={{ fontSize: 16, fontWeight: 600, color: '#1A2733', marginBottom: 16 }}>{t('changePassword')}</h3>
        {pwdMsg && <div className="alert-success">{pwdMsg}</div>}
        {error  && <div className="alert-error">{error}</div>}
        <form onSubmit={handlePasswordChange}>
          <div className="form-group">
            <label>{t('currentPassword')}</label>
            <input type="password" value={current} onChange={e=>setCurrent(e.target.value)} required/>
          </div>
          <div className="form-group">
            <label>{t('newPassword')}</label>
            <input type="password" value={newPwd} onChange={e=>setNewPwd(e.target.value)} placeholder="Min. 12 characters" required/>
          </div>
          <div className="form-group">
            <label>{t('confirmPassword')}</label>
            <input type="password" value={confirm} onChange={e=>setConfirm(e.target.value)} required/>
          </div>
          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? 'Saving…' : t('saveChanges')}
          </button>
        </form>
      </div>
    </div>
  )
}
