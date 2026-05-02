import { useNavigate, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../context/AuthContext'
import Logo from './Logo'

const NAV = [
  { key: 'search',   path: '/search',   labelKey: 'search' },
  { key: 'email',    path: '/email',     labelKey: 'welcomeEmail' },
  { key: 'documents',path: '/documents', labelKey: 'documents' },
  { key: 'admin',    path: '/admin',     labelKey: 'admin', adminOnly: true },
]

export default function Layout({ children }) {
  const { t }    = useTranslation()
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  const initials = user?.full_name
    ?.split(' ').map(n => n[0]).join('').slice(0,2).toUpperCase() || 'U'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      {/* Topbar */}
      <div style={{
        height: 58, background: '#fff', borderBottom: '1px solid #DDE3E8',
        display: 'flex', alignItems: 'center', padding: '0 28px', gap: 20,
        position: 'sticky', top: 0, zIndex: 100,
        boxShadow: '0 1px 4px rgba(0,0,0,.06)',
      }}>
        <div style={{ cursor: 'pointer', marginRight: 8 }} onClick={() => navigate('/search')}>
          <Logo size={34} textSize={17} />
        </div>

        {/* Nav buttons */}
        <div style={{ display: 'flex', gap: 2, flex: 1 }}>
          {NAV.filter(n => !n.adminOnly || user?.role === 'admin').map(nav => {
            const active = location.pathname.startsWith(nav.path)
            return (
              <button
                key={nav.key}
                onClick={() => navigate(nav.path)}
                style={{
                  padding: '6px 16px', borderRadius: 6, border: 'none',
                  background: active ? '#E6F5F3' : 'none',
                  color: active ? '#076B5E' : '#6B8099',
                  fontSize: 13, fontWeight: active ? 600 : 500,
                  cursor: 'pointer', transition: 'all .15s',
                }}
              >
                {t(nav.labelKey)}
              </button>
            )
          })}
        </div>

        {/* User chip */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          background: '#F0F5F8', border: '1px solid #DDE3E8',
          borderRadius: 20, padding: '4px 12px 4px 4px',
        }}>
          <div style={{
            width: 28, height: 28, borderRadius: '50%', background: '#0A8C7C',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 11, fontWeight: 700, color: '#fff',
          }}>
            {initials}
          </div>
          <span style={{ fontSize: 13, color: '#3D5166', fontWeight: 500 }}>
            {user?.full_name}
          </span>
        </div>

        <button
          onClick={handleLogout}
          style={{
            padding: '6px 14px', borderRadius: 6,
            border: '1px solid #DDE3E8', background: 'none',
            color: '#6B8099', fontSize: 12, cursor: 'pointer',
            transition: 'all .15s',
          }}
          onMouseEnter={e => { e.target.style.color='#B03030'; e.target.style.borderColor='#B03030' }}
          onMouseLeave={e => { e.target.style.color='#6B8099'; e.target.style.borderColor='#DDE3E8' }}
        >
          {t('signOut')}
        </button>
      </div>

      {/* Page content */}
      <main style={{ flex: 1, padding: '32px 32px 48px', maxWidth: 1100, width: '100%', margin: '0 auto' }}>
        {children}
      </main>
    </div>
  )
}
