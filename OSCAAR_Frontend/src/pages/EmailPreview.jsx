import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../context/AuthContext'

const LANGS = [
  { code: 'en', label: '🇬🇧 English' },
  { code: 'fr', label: '🇫🇷 Français' },
  { code: 'de', label: '🇩🇪 Deutsch' },
  { code: 'es', label: '🇪🇸 Español' },
  { code: 'ja', label: '🇯🇵 日本語' },
]

const CONTENT = {
  en: { subject: 'Welcome to OSCAAR — Your research access is ready', greeting: 'Welcome to OSCAAR, Dr. Smith.', p1: 'Your research account has been successfully created. You now have secure access to the OSCAAR cancer research intelligence platform.', p2: "OSCAAR allows you to query your institution's private corpus of research documents using natural language — receiving structured answers grounded in your literature, with full source citations.", cta: 'Access OSCAAR', p3: 'If you did not create this account, please contact your system administrator immediately at admin@oscaar.org.', p4: 'You can change your language preference at any time from your account settings.', footer: 'This email was sent by OSCAAR · Open Source Cancer Analysis & Research · www.oscaar.org' },
  fr: { subject: 'Bienvenue sur OSCAAR — Votre accès recherche est prêt', greeting: 'Bienvenue sur OSCAAR, Dr. Smith.', p1: "Votre compte de recherche a été créé avec succès. Vous avez maintenant un accès sécurisé à la plateforme OSCAAR.", p2: "OSCAAR vous permet d'interroger le corpus privé de votre institution en langage naturel, avec des réponses structurées et des citations complètes.", cta: 'Accéder à OSCAAR', p3: "Si vous n'avez pas créé ce compte, contactez immédiatement admin@oscaar.org.", p4: "Vous pouvez modifier vos préférences linguistiques depuis les paramètres de votre compte.", footer: 'Cet e-mail a été envoyé par OSCAAR · www.oscaar.org' },
  de: { subject: 'Willkommen bei OSCAAR — Ihr Forschungszugang ist bereit', greeting: 'Willkommen bei OSCAAR, Dr. Smith.', p1: 'Ihr Forschungskonto wurde erfolgreich erstellt. Sie haben jetzt sicheren Zugang zur OSCAAR-Plattform.', p2: 'OSCAAR ermöglicht es Ihnen, das private Korpus Ihrer Institution in natürlicher Sprache abzufragen.', cta: 'Zu OSCAAR', p3: 'Wenn Sie dieses Konto nicht erstellt haben, kontaktieren Sie sofort admin@oscaar.org.', p4: 'Sie können Ihre Spracheinstellung in den Kontoeinstellungen ändern.', footer: 'Diese E-Mail wurde von OSCAAR gesendet · www.oscaar.org' },
  es: { subject: 'Bienvenido a OSCAAR — Su acceso de investigación está listo', greeting: 'Bienvenido a OSCAAR, Dr. Smith.', p1: 'Su cuenta de investigación ha sido creada exitosamente. Ahora tiene acceso seguro a la plataforma OSCAAR.', p2: 'OSCAAR le permite consultar el corpus privado en lenguaje natural, recibiendo respuestas estructuradas con citas completas.', cta: 'Acceder a OSCAAR', p3: 'Si usted no creó esta cuenta, comuníquese con admin@oscaar.org de inmediato.', p4: 'Puede cambiar su preferencia de idioma desde la configuración de su cuenta.', footer: 'Este correo fue enviado por OSCAAR · www.oscaar.org' },
  ja: { subject: 'OSCAARへようこそ — 研究アクセスの準備ができました', greeting: 'OSCAARへようこそ、Smith博士。', p1: '研究アカウントが正常に作成されました。OSCAARプラットフォームへの安全なアクセスが可能になりました。', p2: '自然言語で研究文書コーパスを照会し、引用付きの構造化された回答を受け取ることができます。', cta: 'OSCAARにアクセス', p3: 'このアカウントを作成していない場合は、admin@oscaar.orgにお問い合わせください。', p4: '言語設定はアカウント設定からいつでも変更できます。', footer: 'このメールはOSCAAR · www.oscaar.orgより送信されました' },
}

export default function EmailPreview() {
  const { t }  = useTranslation()
  const { user } = useAuth()
  const [lang, setLang] = useState(user?.language || 'en')
  const c = CONTENT[lang] || CONTENT.en

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2 style={{ fontFamily: "'DM Serif Display',serif", fontSize: 26, color: '#1A2733' }}>{t('welcomeEmail')}</h2>
        <span style={{ fontSize: 13, color: '#6B8099' }}>Sent on account creation in detected language</span>
      </div>

      {/* Language selector */}
      <div className="card" style={{ padding: '14px 20px', marginBottom: 20, display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '.08em', textTransform: 'uppercase', color: '#6B8099' }}>Preview language:</span>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {LANGS.map(l => (
            <button key={l.code} onClick={() => setLang(l.code)}
              style={{
                padding: '4px 12px', borderRadius: 10, fontSize: 12, cursor: 'pointer',
                border: lang===l.code ? '1px solid #0A8C7C' : '1px solid #DDE3E8',
                background: lang===l.code ? '#0A8C7C' : '#fff',
                color: lang===l.code ? '#fff' : '#3D5166',
                fontWeight: 500, transition: 'all .15s',
              }}
            >{l.label}</button>
          ))}
        </div>
      </div>

      {/* Email preview */}
      <div style={{ background: '#fff', borderRadius: 12, overflow: 'hidden', border: '1px solid #DDE3E8', maxWidth: 560, boxShadow: '0 4px 20px rgba(0,0,0,.08)' }}>
        <div style={{ background: '#0A8C7C', padding: '18px 24px' }}>
          <div style={{ fontFamily: "'DM Serif Display',serif", fontSize: 20, color: '#fff', letterSpacing: '.06em' }}>OSCAAR</div>
          <div style={{ fontSize: 10, color: 'rgba(255,255,255,.75)', letterSpacing: '.15em', textTransform: 'uppercase' }}>Open Source Cancer Analysis & Research</div>
        </div>
        <div style={{ padding: '28px 32px', fontFamily: 'Georgia, serif', color: '#333' }}>
          <p style={{ fontSize: 12, color: '#888', marginBottom: 16, fontFamily: 'sans-serif', borderBottom: '1px solid #eee', paddingBottom: 12, lineHeight: 1.7 }}>
            <strong>To:</strong> Dr. Jane Smith &lt;jsmith@institution.edu&gt;<br/>
            <strong>From:</strong> oscaar@oscaar.org<br/>
            <strong>Subject:</strong> {c.subject}
          </p>
          <h2 style={{ fontSize: 20, color: '#1A2733', marginBottom: 14 }}>{c.greeting}</h2>
          <p style={{ fontSize: 14, lineHeight: 1.7, marginBottom: 12 }}>{c.p1}</p>
          <p style={{ fontSize: 14, lineHeight: 1.7, marginBottom: 16 }}>{c.p2}</p>
          <a href="#" onClick={e=>e.preventDefault()} style={{ display: 'inline-block', background: '#0A8C7C', color: '#fff', padding: '11px 24px', borderRadius: 8, textDecoration: 'none', fontFamily: 'sans-serif', fontWeight: 700, fontSize: 14, marginBottom: 18 }}>
            {c.cta}
          </a>
          <p style={{ fontSize: 12, color: '#888', marginBottom: 8 }}>{c.p3}</p>
          <p style={{ fontSize: 12, color: '#888' }}>{c.p4}</p>
        </div>
        <div style={{ background: '#F4F6F8', padding: '12px 24px', fontSize: 11, color: '#888', fontFamily: 'sans-serif', borderTop: '1px solid #DDE3E8' }}>
          {c.footer}
        </div>
      </div>
    </div>
  )
}
