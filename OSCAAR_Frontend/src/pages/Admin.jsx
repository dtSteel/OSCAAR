import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { adminApi } from '../api/client'
import { format } from 'date-fns'

function StatCard({ label, value, sub }) {
  return (
    <div className="card" style={{ padding: 20 }}>
      <div style={{ fontSize: 11, letterSpacing: '.08em', textTransform: 'uppercase', color: '#6B8099', marginBottom: 8, fontWeight: 700 }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 700, color: '#1A2733' }}>{value}</div>
      {sub && <div style={{ fontSize: 12, color: '#0A8C7C', marginTop: 4, fontWeight: 500 }}>{sub}</div>}
    </div>
  )
}

function RoleBadge({ role }) {
  return <span className={`badge ${role === 'admin' ? 'badge-gold' : 'badge-teal'}`}>{role}</span>
}

export default function Admin() {
  const { t } = useTranslation()

  const [users,   setUsers]   = useState([])
  const [report,  setReport]  = useState(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)
  const [success, setSuccess] = useState(null)

  const load = async () => {
    try {
      const [usersRes, reportRes] = await Promise.all([adminApi.users(), adminApi.usageReport()])
      setUsers(usersRes.data.items || [])
      setReport(reportRes.data)
    } catch { setError('Failed to load admin data') }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const action = async (fn, successMsg) => {
    setError(null); setSuccess(null)
    try { await fn(); setSuccess(successMsg); load() }
    catch (ex) { setError(ex.response?.data?.detail || 'Action failed') }
  }

  const handleDisable = id => action(() => adminApi.disableUser(id), '✓ User disabled')
  const handleEnable  = id => action(() => adminApi.enableUser(id),  '✓ User enabled')
  const handleDelete  = id => {
    if (!window.confirm('Permanently delete this user? This cannot be undone.')) return
    action(() => adminApi.deleteUser(id), '✓ User deleted')
  }
  const handleRole = (id, role) => action(() => adminApi.setRole(id, { role }), `✓ Role updated to ${role}`)
  const handleTestEmail = () => action(() => adminApi.testEmail(), '✓ Test email sent — check your inbox or Mailpit')
  const handleExport = async () => {
    try {
      const { data } = await adminApi.usageReport()
      const csv = ['Metric,Value', ...Object.entries(data).map(([k,v]) => `${k},${v}`)].join('\n')
      const blob = new Blob([csv], { type: 'text/csv' })
      const url  = URL.createObjectURL(blob)
      const a    = document.createElement('a')
      a.href = url; a.download = 'oscaar_report.csv'; a.click()
    } catch { setError('Export failed') }
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <h2 style={{ fontFamily: "'DM Serif Display',serif", fontSize: 26, color: '#1A2733' }}>
          {t('admin')}
        </h2>
        <button className="btn-outline" onClick={handleExport}>{t('exportReport')}</button>
      </div>

      {error   && <div className="alert-error">{error}</div>}
      {success && <div className="alert-success">{success}</div>}

      {/* Stats grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 14, marginBottom: 28 }}>
        <StatCard label={t('totalUsers')}  value={report?.total_users    || 0} sub="Active researchers"/>
        <StatCard label={t('totalDocs')}   value={report?.total_documents || 0} sub="In corpus"/>
        <StatCard label={t('queries30d')}  value={report?.total_queries   || 0} sub="Total queries"/>
        <StatCard label="System"           value="OK" sub="All services healthy"/>
      </div>

      {/* User management */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
        <div className="section-label" style={{ marginBottom: 0 }}>{t('userMgmt')}</div>
        <div style={{ display: 'flex', gap: 10 }}>
          <button className="btn-outline" onClick={handleTestEmail}>{t('emailSettings')}</button>
        </div>
      </div>

      <div className="card" style={{ overflow: 'hidden', marginBottom: 20 }}>
        {loading ? (
          <div style={{ padding: 40, textAlign: 'center' }}><div className="spinner" style={{ margin: '0 auto' }}/></div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>{t('name')}</th>
                <th>Email</th>
                <th>{t('role')}</th>
                <th>{t('status')}</th>
                <th>{t('lastLogin')}</th>
                <th>{t('actions')}</th>
              </tr>
            </thead>
            <tbody>
              {users.map(u => (
                <tr key={u.id}>
                  <td style={{ color: '#1A2733', fontWeight: 600 }}>{u.full_name}</td>
                  <td style={{ color: '#6B8099' }}>{u.email}</td>
                  <td><RoleBadge role={u.role}/></td>
                  <td>
                    <span style={{ display: 'inline-flex', alignItems: 'center', fontSize: 12, fontWeight: 500 }}>
                      <span className={`dot ${u.is_active ? 'dot-active' : 'dot-disabled'}`}/>
                      {u.is_active ? t('active') : t('disabled')}
                    </span>
                  </td>
                  <td style={{ color: '#6B8099' }}>
                    {u.last_login_at ? format(new Date(u.last_login_at), 'MMM d') : 'Never'}
                  </td>
                  <td>
                    <div style={{ display: 'flex', gap: 5 }}>
                      {u.is_active
                        ? <button className="btn-ghost danger" onClick={() => handleDisable(u.id)}>{t('disable')}</button>
                        : <button className="btn-ghost" onClick={() => handleEnable(u.id)}>{t('enable')}</button>
                      }
                      {u.role === 'researcher'
                        ? <button className="btn-ghost" onClick={() => handleRole(u.id, 'admin')}>→ Admin</button>
                        : <button className="btn-ghost" onClick={() => handleRole(u.id, 'researcher')}>→ Researcher</button>
                      }
                      <button className="btn-ghost danger" onClick={() => handleDelete(u.id)}>{t('delete')}</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
