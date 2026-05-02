export default function Logo({ size = 40, showText = true, textSize = 22 }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <svg width={size} height={size} viewBox="0 0 40 40" fill="none">
        <circle cx="20" cy="20" r="18" stroke="#0A8C7C" strokeWidth="1.5" strokeDasharray="4 2.5"/>
        <circle cx="20" cy="20" r="8" fill="rgba(10,140,124,0.12)" stroke="#0A8C7C" strokeWidth="1"/>
        <path d="M20 12 Q24 16 20 20 Q16 24 20 28" stroke="#0A8C7C" strokeWidth="1.8" fill="none" strokeLinecap="round"/>
        <path d="M20 12 Q16 16 20 20 Q24 24 20 28" stroke="#C8953A" strokeWidth="1.8" fill="none" strokeLinecap="round"/>
        <line x1="17.5" y1="14.5" x2="22.5" y2="14.5" stroke="#0A8C7C" strokeWidth=".9" opacity=".6"/>
        <line x1="17.5" y1="18.5" x2="22.5" y2="18.5" stroke="#0A8C7C" strokeWidth=".9" opacity=".6"/>
        <line x1="17.5" y1="22.5" x2="22.5" y2="22.5" stroke="#0A8C7C" strokeWidth=".9" opacity=".6"/>
        <line x1="17.5" y1="26.5" x2="22.5" y2="26.5" stroke="#0A8C7C" strokeWidth=".9" opacity=".6"/>
        <circle cx="6"  cy="20" r="2.5" fill="#0A8C7C" opacity=".7"/>
        <circle cx="34" cy="20" r="2.5" fill="#0A8C7C" opacity=".7"/>
        <circle cx="20" cy="6"  r="2.5" fill="#C8953A" opacity=".7"/>
        <circle cx="20" cy="34" r="2.5" fill="#C8953A" opacity=".7"/>
        <line x1="6"  y1="20" x2="12" y2="20" stroke="#0A8C7C" strokeWidth=".8" opacity=".4"/>
        <line x1="28" y1="20" x2="34" y2="20" stroke="#0A8C7C" strokeWidth=".8" opacity=".4"/>
        <line x1="20" y1="6"  x2="20" y2="12" stroke="#C8953A" strokeWidth=".8" opacity=".4"/>
        <line x1="20" y1="28" x2="20" y2="34" stroke="#C8953A" strokeWidth=".8" opacity=".4"/>
      </svg>
      {showText && (
        <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1 }}>
          <span style={{ fontFamily: "'DM Serif Display', serif", fontSize: textSize, letterSpacing: '.06em', color: '#0A8C7C' }}>
            OSCAAR
          </span>
          <span style={{ fontSize: 9, letterSpacing: '.18em', textTransform: 'uppercase', color: '#6B8099', marginTop: 2, fontWeight: 400 }}>
            Open Source Cancer Analysis & Research
          </span>
        </div>
      )}
    </div>
  )
}
