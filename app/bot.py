from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.config import Settings, get_settings
from app.db.session import get_sessionmaker
from app.domain.errors import DomainError
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.lesson_note_repository import LessonNoteRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.skill_repository import SkillRepository
from app.services.agent import AgentService
from app.services.knowledge import KnowledgeBase
from app.services.router import LlmClient, RouterService
from app.services.tools import Tool, ToolContext, phase2_tools
from app.services.web_search import WebSearcher

log = structlog.get_logger()

START_TEXT = (
    "Hi Daria! I'm your driving-exam copilot.\n\n"
    "I can:\n"
    '- look up your upcoming and past lessons ("when is my next lesson?", '
    '"what did we do last time?")\n'
    '- look up your notes ("what did I write about highways?")\n'
    '- analyse your progress ("what are my weak areas?", "am I on track?")\n'
    '- answer CBR exam questions ("what do they check on bijzondere verrichtingen?")\n'
    '- log what you practiced ("today we did parking, went ok")\n\n'
    "Just write to me in Russian or English."
)


@dataclass
class Copilot:
    """Wires the router + agent + tool registry around shared services."""

    router: RouterService
    agent: AgentService
    tools: list[Tool]
    settings: Settings

    @classmethod
    def build(cls, client: LlmClient, settings: Settings) -> Copilot:
        return cls(
            router=RouterService(client, settings),
            agent=AgentService(client, settings),
            tools=phase2_tools(),
            settings=settings,
        )

    async def respond(self, message: str) -> str:
        label = await self.router.classify(message)
        async with get_sessionmaker()() as session:
            ctx = _tool_context(session, self.settings)
            try:
                reply = await self.agent.handle(message, label, self.tools, ctx)
                await session.commit()
                log.info("bot.respond", label=label, chars=len(reply))
                return reply
            except DomainError:
                await session.rollback()
                raise


def _tool_context(session: AsyncSession, settings: Settings) -> ToolContext:
    return ToolContext(
        sessions=SessionRepository(session),
        skills=SkillRepository(session),
        notes=LessonNoteRepository(session),
        audit=AuditLogRepository(session),
        timezone=ZoneInfo(settings.timezone),
        knowledge=KnowledgeBase(settings.knowledge_dir),
        web=WebSearcher(settings.tavily_api_key),
        exam_date=_parse_exam_date(settings.exam_date),
    )


def _parse_exam_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        log.warning("bot.bad_exam_date", value=value)
        return None


def build_application(
    copilot: Copilot, settings: Settings
) -> Application[Any, Any, Any, Any, Any, Any]:
    application = ApplicationBuilder().token(settings.telegram_bot_token).build()
    application.bot_data["copilot"] = copilot
    application.bot_data["settings"] = settings
    application.add_handler(CommandHandler("start", _start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _on_message))
    return application


async def _start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data["settings"]
    chat_id = update.effective_chat.id if update.effective_chat else None
    if not is_allowed_chat(chat_id, settings):
        return
    if update.effective_chat is not None:
        await update.effective_chat.send_message(START_TEXT)


async def _on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data["settings"]
    chat_id = update.effective_chat.id if update.effective_chat else None
    if not is_allowed_chat(chat_id, settings):
        return
    message = update.message
    if message is None or message.text is None:
        return
    copilot: Copilot = context.bot_data["copilot"]
    try:
        reply = await copilot.respond(message.text)
    except DomainError as exc:
        log.error("bot.error", error=str(exc))
        reply = "Sorry, I couldn't process that right now. Please try again in a moment."
    log.info("bot.reply", text=reply)
    if update.effective_chat is not None:
        await update.effective_chat.send_message(reply)


def is_allowed_chat(chat_id: int | None, settings: Settings) -> bool:
    """Identity check: only the configured chat may talk to the bot."""
    if settings.allowed_chat_id is None:
        if chat_id is not None:
            log.warning("bot.ignored_no_allowed_chat_id", chat_id=chat_id)
        return False
    if chat_id is None or chat_id != settings.allowed_chat_id:
        log.warning("bot.ignored_foreign_chat", chat_id=chat_id)
        return False
    return True


def run(copilot: Copilot, settings: Settings) -> None:
    application = build_application(copilot, settings)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


__all__ = ["START_TEXT", "Copilot", "build_application", "get_settings", "is_allowed_chat", "run"]
