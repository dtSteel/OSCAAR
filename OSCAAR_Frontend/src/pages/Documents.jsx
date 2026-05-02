import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useDropzone } from 'react-dropzone'
import { docApi } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { format } from 'date-fns'

function StatusBadge({ status }) {
  const styles = {
    indexed:    'badge-teal',
    processing: 'badge-gold',
    pending:    'badge-gold',
    error:      'badge-danger',
  }
  const labels = { indexed: '● Indexed', processing: '⟳ Processing', pending: '● Pending', error: '✕ Error' }
  return <span className={`badge ${styles[status] || 'badge-gray'}`}>{labels[status] || status}</span>
}

export default function Documents() {
  const { t }    = useTranslation()
  const { user } = useAuth()

  const [docs,    setDocs]    = useState([])
  const [stats,   setStats]   = useState(null)
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [urlInput, setUrlInput] = useState('')
  const [error,   setError]   = useState(null)
  const [success, setSuccess] = useState(null)

  const loadDocs = async () => {
    try {
      const [docsRes, statsRes] = await Promise.all([docApi.list(), docApi.stats()])
      setDocs(docsRes.data.items || [])
      setStats(statsRes.data)
    } catch { setError('Failed to load documents') }
    finally { setLoading(false) }
  }

  useEffect(() => { loadDocs() }, [])

  const onDrop = useCallback(async acceptedFiles => {
    setUploading(true); setError(null); setSuccess(null)
    let uploaded = 0
    for (const file of acceptedFiles) {
      try {
        await docApi.upload(file)
        uploaded++
      } catch (ex) {
        setError(`Failed to upload ${file.name}: ${ex.response?.data?.detail || 'Unknown error'}`)
      }
    }
    if (uploaded > 0) {
      setSuccess(`✓ ${uploaded} file${uploaded>1?'s':''} uploaded and queued for indexing`)
      loadDocs()
    }
    setUploading(false)
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'], 'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'], 'text/plain': ['.txt'], 'text/markdown': ['.md'] },
    maxSize: 50 * 1024 * 1024,
  })

  const handleUrlIngest = async () => {
    if (!urlInput.trim()) return
    setUploading(true); setError(null)
    try {
      await docApi.uploadUrl({ url: urlInput.trim() })
      setSuccess('✓ URL queued for ingestion')
      setUrlInput('')
      loadDocs()
    } catch (ex) {
      setError(ex.response?.data?.detail || 'URL ingestion failed')
    } finally { setUploading(false) }
  }

  const handleDelete = async id => {
    if (!window.confirm('Delete this document? This cannot be undone.')) return
    try {
      await docApi.delete(id)
      setDocs(d => d.filter(doc => doc.id !== id))
      setSuccess('✓ Document deleted')
    } catch { setError('Failed to delete document') }
  }

  const typeExt = filename => {
    const ext = filename?.split('.').pop()?.toUpperCase()
    return ext && ext.length <= 4 ? ext : 'URL'
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <h2 style={{ fontFamily: "'DM Serif Display',serif", fontSize: 26, color: '#1A2733' }}>
          {t('documents')}
        </h2>
        {stats && (
          <div style={{ fontSize: 13, color: '#6B8099' }}>
            {stats.indexed_documents} indexed · {stats.total_documents} total · {Math.round(stats.total_storage_bytes / 1024 / 1024)} MB
          </div>
        )}
      </div>

      {error   && <div className="alert-error">{error}</div>}
      {success && <div className="alert-success">{success}</div>}

      {/* Upload zone */}
      <div {...getRootProps()} style={{
        border: `2px dashed ${isDragActive ? '#0A8C7C' : '#C5CDD6'}`,
        borderRadius: 12, padding: 32, textAlign: 'center', marginBottom: 16,
        background: isDragActive ? '#E6F5F3' : '#fff', cursor: 'pointer', transition: 'all .2s',
      }}>
        <input {...getInputProps()}/>
        <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#0A8C7C" strokeWidth="1.5" strokeLinecap="round" style={{ marginBottom: 10 }}>
          <polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/>
          <path d="M20.39 18.39A5 5 0 0018 9h-1.26A8 8 0 103 16.3"/>
        </svg>
        <p style={{ color: '#6B8099', fontSize: 14, marginBottom: 10 }}>
          {uploading ? 'Uploading…' : isDragActive ? 'Drop files here' : t('uploadZone')}
        </p>
        <div style={{ display: 'flex', gap: 6, justifyContent: 'center', flexWrap: 'wrap' }}>
          {['PDF','DOCX','TXT','MD'].map(ext => (
            <span key={ext} className="badge badge-gold">{ext}</span>
          ))}
        </div>
      </div>

      {/* URL input */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 24 }}>
        <input
          value={urlInput}
          onChange={e => setUrlInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleUrlIngest()}
          placeholder="https://pubmed.ncbi.nlm.nih.gov/..."
          style={{ flex: 1, padding: '10px 14px', background: '#F8FAFB', border: '1px solid #DDE3E8', borderRadius: 8, fontSize: 13, outline: 'none', fontFamily: 'inherit' }}
        />
        <button className="btn-outline" onClick={handleUrlIngest} disabled={uploading}>
          Ingest URL
        </button>
        {user?.role === 'admin' && (
          <button className="btn-ghost" onClick={() => docApi.batch().then(() => { setSuccess('Batch ingestion started'); loadDocs() })}>
            Batch Folder
          </button>
        )}
      </div>

      {/* Documents table */}
      <div className="section-label">{t('indexedDocs')} ({docs.length})</div>
      <div className="card" style={{ overflow: 'hidden' }}>
        {loading ? (
          <div style={{ padding: 40, textAlign: 'center' }}><div className="spinner" style={{ margin: '0 auto' }}/></div>
        ) : docs.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#6B8099', fontSize: 14 }}>
            No documents yet. Upload your first file above.
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Document</th>
                <th>{t('type')}</th>
                <th>{t('added')}</th>
                <th>{t('status')}</th>
                {user?.role === 'admin' && <th></th>}
              </tr>
            </thead>
            <tbody>
              {docs.map(doc => (
                <tr key={doc.id}>
                  <td style={{ color: '#1A2733', fontWeight: 500, maxWidth: 320, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {doc.filename}
                  </td>
                  <td><span className="badge badge-gold">{typeExt(doc.filename)}</span></td>
                  <td>{doc.created_at ? format(new Date(doc.created_at), 'MMM d, yyyy') : '—'}</td>
                  <td><StatusBadge status={doc.status}/></td>
                  {user?.role === 'admin' && (
                    <td>
                      <button onClick={() => handleDelete(doc.id)}
                        style={{ background: 'none', border: 'none', color: '#6B8099', cursor: 'pointer', fontSize: 14, padding: '3px 8px', borderRadius: 4 }}
                        onMouseEnter={e=>{e.target.style.background='#FFF0F0';e.target.style.color='#B03030'}}
                        onMouseLeave={e=>{e.target.style.background='none';e.target.style.color='#6B8099'}}
                      >✕</button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
