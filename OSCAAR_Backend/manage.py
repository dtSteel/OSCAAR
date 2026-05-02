#!/usr/bin/env python3
"""
OSCAAR Management CLI
Usage: python manage.py <command> [options]
"""
import asyncio
import argparse
import sys


async def cmd_create_admin(args):
    from app.db.session import AsyncSessionLocal, create_tables
    from app.models.user import User
    from app.services.auth_service import hash_password, get_user_by_email

    await create_tables()
    async with AsyncSessionLocal() as db:
        existing = await get_user_by_email(db, args.email)
        if existing:
            print(f"User {args.email} already exists.")
            return

        user = User(
            email=args.email,
            full_name=args.name,
            hashed_password=hash_password(args.password),
            role="admin",
            language="en",
        )
        db.add(user)
        await db.commit()
        print(f"Admin user created: {args.email}")


async def cmd_create_user(args):
    from app.db.session import AsyncSessionLocal, create_tables
    from app.models.user import User
    from app.services.auth_service import hash_password, get_user_by_email
    from app.services.email_service import send_welcome_email
    import secrets

    await create_tables()
    async with AsyncSessionLocal() as db:
        existing = await get_user_by_email(db, args.email)
        if existing:
            print(f"User {args.email} already exists.")
            return

        temp_password = secrets.token_urlsafe(12)
        user = User(
            email=args.email,
            full_name=args.name,
            hashed_password=hash_password(temp_password),
            role=args.role,
            language="en",
        )
        db.add(user)
        await db.commit()
        print(f"User created: {args.email} (role: {args.role})")
        print(f"Temporary password: {temp_password}")

        try:
            await send_welcome_email(args.name, args.email, "en")
            print("Welcome email sent.")
        except Exception as e:
            print(f"Warning: Could not send welcome email: {e}")


async def cmd_set_role(args):
    from app.db.session import AsyncSessionLocal
    from app.services.auth_service import get_user_by_email

    async with AsyncSessionLocal() as db:
        user = await get_user_by_email(db, args.email)
        if not user:
            print(f"User not found: {args.email}")
            return
        user.role = args.role
        await db.commit()
        print(f"Role updated: {args.email} → {args.role}")


async def cmd_set_language(args):
    from app.db.session import AsyncSessionLocal
    from app.services.auth_service import get_user_by_email

    async with AsyncSessionLocal() as db:
        user = await get_user_by_email(db, args.email)
        if not user:
            print(f"User not found: {args.email}")
            return
        user.language = args.lang
        await db.commit()
        print(f"Language updated: {args.email} → {args.lang}")


async def cmd_force_password_reset(args):
    from app.db.session import AsyncSessionLocal
    from app.services.auth_service import (
        get_user_by_email, create_password_reset_token
    )
    from app.services.email_service import send_password_reset_email

    async with AsyncSessionLocal() as db:
        user = await get_user_by_email(db, args.email)
        if not user:
            print(f"User not found: {args.email}")
            return
        token = await create_password_reset_token(db, user.id)
        await db.commit()
        await send_password_reset_email(user.full_name, user.email, token, user.language)
        print(f"Password reset email sent to: {args.email}")


async def cmd_batch_ingest(args):
    from app.tasks.celery_app import batch_ingest_task
    result = batch_ingest_task.delay(args.directory if hasattr(args, 'directory') else "./batch_inbox")
    print(f"Batch ingestion queued. Job ID: {result.id}")


async def cmd_ingest_status(args):
    from app.db.session import AsyncSessionLocal
    from app.models.user import Document
    from sqlalchemy import select, func

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Document.status, func.count(Document.id))
            .where(Document.deleted_at.is_(None))
            .group_by(Document.status)
        )
        rows = result.all()
        print("\nDocument ingestion status:")
        print("-" * 30)
        for status, count in rows:
            print(f"  {status:<12} {count}")
        print()


async def cmd_test_email(args):
    from app.services.email_service import send_email
    await send_email(
        to_address=args.to,
        template="welcome",
        language="en",
        context={"full_name": "Test User", "login_url": "https://www.oscaar.org"},
    )
    print(f"Test email sent to: {args.to}")


async def cmd_migrate(args):
    from app.db.session import create_tables
    await create_tables()
    print("Database tables created/verified.")


async def cmd_reindex_all(args):
    from app.db.session import AsyncSessionLocal
    from app.models.user import Document
    from app.tasks.celery_app import ingest_document_task
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Document).where(
                Document.deleted_at.is_(None),
                Document.status == "indexed"
            )
        )
        docs = result.scalars().all()
        count = 0
        for doc in docs:
            doc.status = "pending"
            ingest_document_task.delay(doc.id, doc.filename, doc.filename, doc.source_type)
            count += 1
        await db.commit()
        print(f"Re-queued {count} documents for re-indexing.")


def main():
    parser = argparse.ArgumentParser(description="OSCAAR Management CLI")
    subparsers = parser.add_subparsers(dest="command")

    # create_admin
    p = subparsers.add_parser("create_admin")
    p.add_argument("--email", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--password", required=True)

    # create_user
    p = subparsers.add_parser("create_user")
    p.add_argument("--email", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--role", default="researcher", choices=["researcher", "admin"])

    # set_role
    p = subparsers.add_parser("set_role")
    p.add_argument("--email", required=True)
    p.add_argument("--role", required=True, choices=["researcher", "admin"])

    # set_language
    p = subparsers.add_parser("set_language")
    p.add_argument("--email", required=True)
    p.add_argument("--lang", required=True)

    # force_password_reset
    p = subparsers.add_parser("force_password_reset")
    p.add_argument("--email", required=True)

    # batch_ingest
    p = subparsers.add_parser("batch_ingest")
    p.add_argument("--directory", default="./batch_inbox")

    # ingest_status
    subparsers.add_parser("ingest_status")

    # test_email
    p = subparsers.add_parser("test_email")
    p.add_argument("--to", required=True)

    # migrate
    subparsers.add_parser("migrate")

    # reindex_all
    subparsers.add_parser("reindex_all")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "create_admin":        cmd_create_admin,
        "create_user":         cmd_create_user,
        "set_role":            cmd_set_role,
        "set_language":        cmd_set_language,
        "force_password_reset":cmd_force_password_reset,
        "batch_ingest":        cmd_batch_ingest,
        "ingest_status":       cmd_ingest_status,
        "test_email":          cmd_test_email,
        "migrate":             cmd_migrate,
        "reindex_all":         cmd_reindex_all,
    }

    asyncio.run(commands[args.command](args))


if __name__ == "__main__":
    main()
