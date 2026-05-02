# OSCAAR

**Open Source Cancer Analysis & Research**

A multi-language, multi-modal Retrieval-Augmented Generation (RAG) platform for cancer research institutions. Researchers query a private corpus of scientific documents using natural language and receive structured responses grounded in the uploaded literature.

---

## Quick Start (Demo)

```bash
# 1. Clone the repository
git clone https://github.com/dtSteel/OSCAAR.git
cd OSCAAR

# 2. Generate JWT signing keys
python scripts/generate_keys.py

# 3. Copy and configure environment
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY and OPENAI_API_KEY

# 4. Start all services
docker compose up -d

# 5. Create the first admin account
docker compose exec api python manage.py create_admin \
  --email admin@yourdomain.com \
  --name "Your Name" \
  --password "YourSecurePassword123!"

# 6. Open in browser
open http://localhost:8000
# Mailpit email UI: http://localhost:8025
```

---

## Project Structure

```
oscaar/
├── app/
│   ├── main.py              # FastAPI app entry point
│   ├── api/routes/          # All API endpoints
│   │   ├── auth.py          # Authentication routes
│   │   ├── query.py         # RAG query routes
│   │   ├── documents.py     # Document management routes
│   │   ├── admin.py         # Admin routes
│   │   └── health.py        # Health check
│   ├── core/
│   │   ├── config.py        # Settings from .env
│   │   ├── dependencies.py  # JWT auth dependencies
│   │   └── logging.py       # Structured logging
│   ├── db/
│   │   └── session.py       # SQLAlchemy async session
│   ├── models/
│   │   └── user.py          # All database models
│   ├── schemas/
│   │   └── schemas.py       # Pydantic request/response schemas
│   ├── services/
│   │   ├── auth_service.py      # JWT, hashing, tokens
│   │   ├── rag_service.py       # Full RAG pipeline
│   │   ├── vector_store.py      # ChromaDB / Qdrant abstraction
│   │   ├── ingestion_service.py # Document parsing and chunking
│   │   ├── injection_filter.py  # Prompt injection defence
│   │   ├── email_service.py     # Mailpit / Postal email
│   │   └── geoip_service.py     # IP to language detection
│   └── tasks/
│       └── celery_app.py    # Background ingestion workers
├── templates/email/         # Multilingual email templates
├── scripts/
│   ├── generate_keys.py     # JWT key generation
│   └── backup_db.sh         # Database backup script
├── tests/                   # Test suite
├── manage.py                # CLI management commands
├── docker-compose.yml       # Demo environment
├── Dockerfile
├── requirements.txt
└── .env.example
```

---

## Management Commands

```bash
python manage.py migrate                          # Create/update database tables
python manage.py create_admin --email x --name y --password z
python manage.py create_user  --email x --name y --role researcher
python manage.py set_role     --email x --role admin
python manage.py set_language --email x --lang fr
python manage.py force_password_reset --email x
python manage.py batch_ingest --directory ./batch_inbox
python manage.py ingest_status
python manage.py test_email   --to you@domain.com
python manage.py reindex_all
```

---

## API Documentation

Available at `http://localhost:8000/api/docs` in demo mode.

Full API reference: see `OSCAAR_Backend_API_Schema.docx` in the `docs/` folder.

---

## Full Documentation

All documentation is in the `docs/` folder:

- `OSCAAR_System_Administrator_Guide.docx` — Installation, configuration, security, backups
- `OSCAAR_Backend_API_Schema.docx` — Complete API reference and database schema
- `OSCAAR_1_System_Overview.pdf` — Architecture overview diagram
- `OSCAAR_2_RAG_Query_Pipeline.pdf` — Query pipeline diagram
- `OSCAAR_3_Document_Ingestion.pdf` — Document ingestion diagram

---

## License

Private — OSCAAR Research Project
