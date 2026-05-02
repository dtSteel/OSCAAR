import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { queryApi } from '../api/client'
import { useAuth } from '../context/AuthContext'

const CHIPS = [
  { label: 'BRCA mutations',         q: 'BRCA mutation mechanisms in breast cancer' },
  { label: 'Checkpoint inhibitors',  q: 'immunotherapy checkpoint inhibitors PD-1 PD-L1' },
  { label: 'Tumor microenvironment', q: 'tumor microenvironment immune evasion mechanisms' },
  { label: 'CRISPR therapy',         q: 'CRISPR cancer therapy clinical trials' },
  { label: 'Liquid biopsy',          q: 'liquid biopsy early cancer detection ctDNA' },
]

const FORMATS = ['text', 'chart', 'slides', 'citations']
const FORMAT_LABELS = { text: 'Summary', chart: 'Chart', slides: 'Slides', citations: 'Citations' }

function ConfidenceBadge({ level }) {
  const styles = {
    high:   { background: '#E6F5F3', color: '#076B5E', border: '1px solid #C2E8E3' },
    medium: { background: '#FFF8E6', color: '#8A6200', border: '1px solid #D4A940' },
    low:    { background: '#FFF0F0', color: '#B03030', border: '1px solid #f5c0c0' },
  }
  return (
    <span style={{ ...styles[level] || styles.low, padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 700 }}>
      {level?.charAt(0).toUpperCase() + level?.slice(1)} confidence
    </span>
  )
}

function ResultCard({ result }) {
  return (
    <div className="card" style={{ padding: '20px 24px', marginBottom: 12, transition: 'box-shadow .15s' }}
      onMouseEnter={e=>e.currentTarget.style.boxShadow='0 3px 12px rgba(0,0,0,.08)'}
      onMouseLeave={e=>e.currentTarget.style.boxShadow=''}
    >
      <h3 style={{ fontSize: 16, color: '#076B5E', marginBottom: 8, fontWeight: 600 }}>
        Query Result
      </h3>
      <p style={{ fontSize: 14, color: '#3D5166', lineHeight: 1.65, marginBottom: 12, whiteSpace: 'pre-wrap' }}>
        {result.answer}
      </p>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 10 }}>
        <ConfidenceBadge level={result.confidence}/>
        <span style={{ fontSize: 12, color: '#6B8099' }}>
          {result.tokens_used} tokens used
        </span>
      </div>
      {result.sources?.length > 0 && (
        <div style={{ borderTop: '1px solid #F0F3F5', paddingTop: 10, marginTop: 4 }}>
          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '.07em', textTransform: 'uppercase', color: '#6B8099', marginBottom: 8 }}>
            Sources
          </div>
          {result.sources.map((src, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 5, fontSize: 12, color: '#3D5166' }}>
              <span style={{ background: '#E6F5F3', color: '#076B5E', border: '1px solid #C2E8E3', padding: '1px 6px', borderRadius: 3, fontSize: 10, fontWeight: 700 }}>
                {Math.round(src.relevance_score * 100)}%
              </span>
              <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {src.filename}
              </span>
              <span style={{ color: '#6B8099' }}>chunk {src.chunk_index}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function Search() {
  const { t }    = useTranslation()
  const { user } = useAuth()

  const [query,   setQuery]   = useState('')
  const [format,  setFormat]  = useState('text')
  const [loading, setLoading] = useState(false)
  const [result,  setResult]  = useState(null)
  const [error,   setError]   = useState(null)

  const doSearch = async (q = query) => {
    if (!q.trim()) return
    setLoading(true); setError(null); setResult(null)
    try {
      const { data } = await queryApi.submit({
        q: q.trim(),
        response_format: format,
        top_k: 5,
        language: user?.language || 'en',
      })
      setResult(data)
    } catch (ex) {
      const code = ex.response?.headers?.['x-error-code']
      if (code === 'QUERY_INJECTION') setError('Your query was flagged as potentially unsafe and was not processed.')
      else if (code === 'VECTOR_STORE_DOWN') setError('The search index is temporarily unavailable. Please try again shortly.')
      else setError(ex.response?.data?.detail || 'Search failed. Please try again.')
    } finally { setLoading(false) }
  }

  const fillSearch = q => { setQuery(q); doSearch(q) }

  return (
    <div>
      <div style={{ textAlign: 'center', padding: '28px 0 36px' }}>
        <h1 style={{ fontFamily: "'DM Serif Display',serif", fontSize: 34, color: '#1A2733', marginBottom: 8 }}>
          {t('searchHero')}
        </h1>
        <p style={{ fontSize: 15, color: '#6B8099' }}>{t('searchSub')}</p>
      </div>

      {/* Search bar */}
      <div style={{
        display: 'flex', alignItems: 'center',
        background: '#fff', border: '1.5px solid #DDE3E8',
        borderRadius: 12, padding: '5px 5px 5px 20px',
        maxWidth: 700, margin: '0 auto 18px',
        boxShadow: '0 2px 12px rgba(0,0,0,.06)',
        transition: 'border-color .2s',
      }}
        onFocus={e => e.currentTarget.style.borderColor='#0A8C7C'}
        onBlur={e => e.currentTarget.style.borderColor='#DDE3E8'}
      >
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && doSearch()}
          placeholder={t('searchPlaceholder')}
          style={{ flex: 1, border: 'none', outline: 'none', fontSize: 15, color: '#1A2733', background: 'none', padding: '9px 0', fontFamily: 'inherit' }}
        />
        <button
          onClick={() => doSearch()}
          disabled={loading}
          className="btn-primary"
          style={{ borderRadius: 8, padding: '10px 22px' }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
            <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>
          </svg>
          {t('search')}
        </button>
      </div>

      {/* Suggestion chips */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'center', marginBottom: 28 }}>
        {CHIPS.map(c => (
          <button key={c.label} onClick={() => fillSearch(c.q)}
            style={{
              padding: '6px 14px', borderRadius: 20, background: '#fff',
              border: '1px solid #DDE3E8', fontSize: 12, color: '#3D5166',
              cursor: 'pointer', fontWeight: 500, transition: 'all .15s',
            }}
            onMouseEnter={e=>{e.target.style.background='#E6F5F3';e.target.style.borderColor='#C2E8E3';e.target.style.color='#076B5E'}}
            onMouseLeave={e=>{e.target.style.background='#fff';e.target.style.borderColor='#DDE3E8';e.target.style.color='#3D5166'}}
          >
            {c.label}
          </button>
        ))}
      </div>

      {/* Loading */}
      {loading && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 16px', background: '#E6F5F3', border: '1px solid #C2E8E3', borderRadius: 8, marginBottom: 16, fontSize: 13, color: '#076B5E' }}>
          <div className="spinner"/>
          {t('analyzing')}
        </div>
      )}

      {/* Error */}
      {error && <div className="alert-error">{error}</div>}

      {/* Results */}
      {result && (
        <div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 16, alignItems: 'center' }}>
            <span style={{ fontSize: 12, color: '#6B8099', fontWeight: 500 }}>{t('viewAs')}:</span>
            {FORMATS.map(f => (
              <button key={f} onClick={() => setFormat(f)}
                style={{
                  padding: '5px 14px', borderRadius: 6,
                  border: format===f ? '1px solid #0A8C7C' : '1px solid #DDE3E8',
                  background: format===f ? '#E6F5F3' : '#fff',
                  color: format===f ? '#076B5E' : '#6B8099',
                  fontSize: 12, cursor: 'pointer', fontWeight: format===f ? 600 : 500,
                }}
              >
                {FORMAT_LABELS[f]}
              </button>
            ))}
          </div>
          <ResultCard result={result}/>
        </div>
      )}
    </div>
  )
}
