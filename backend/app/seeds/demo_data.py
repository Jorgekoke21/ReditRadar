"""Seeds the demo account: communities, one watch profile, ten topics and
twenty fictional conversations (spec sections 6, 7 and 21).

Idempotent: running it repeatedly refreshes only demo-owned rows, including
relative published/detected timestamps, without touching manual/user rows or
duplicating seeds. Safe to run on every container start, which is how
docker-compose invokes it.

Run directly with: python -m app.seeds.demo_data
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.config import get_settings
from app.db import AsyncSessionLocal, Base, engine
from app.models.account import Account
from app.models.alerts import AlertSettings
from app.models.community import Community, WatchProfile, WatchProfileCommunity
from app.models.enums import SourceMode
from app.models.topic import Topic, TopicExclusion, TopicKeyword
from app.services import jobs as jobs_service
from app.services.dedupe import compute_dedupe_hash, normalize_url

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("radarin.seeds")

DEMO_EMAIL = "demo@radarin.local"

COMMON_EXCLUSIONS = [
    "hiring", "oferta de empleo", "work for free", "trabajar gratis", "crypto",
    "bitcoin", "apuestas", "betting", "my course", "mi curso", "dropshipping", "meme",
]

COMMUNITIES = [
    ("agency", "leads", "high"),
    ("localseo", "leads", "high"),
    ("web_design", "leads", "high"),
    ("freelance", "leads", "medium"),
    ("sales", "leads", "medium"),
    ("marketing", "leads", "medium"),
    ("smallbusiness", "leads", "medium"),
    ("SaaS", "learning", "medium"),
    ("SaaSDevelopers", "learning", "low"),
    ("SideProject", "learning", "low"),
    ("startups", "learning", "medium"),
    ("Entrepreneur", "learning", "medium"),
    ("EntrepreneurRideAlong", "learning", "low"),
    ("thesidehustle", "learning", "low"),
]

TOPICS = [
    {
        "name": "Conseguir clientes para agencias",
        "description": "Agencias de marketing o servicios digitales que buscan cómo conseguir más clientes.",
        "keywords": ["conseguir clientes", "find clients", "get more clients", "landing clients", "closing clients", "cliente potencial", "primeros clientes", "clientes locales", "conseguimos clientes"],
        "positive": ["¿Cómo consigo mis primeros clientes para mi agencia?"],
        "negative": ["Vendo curso de marketing digital"],
        "priority": "high",
    },
    {
        "name": "Captación para diseñadores web",
        "description": "Diseñadores o desarrolladores web freelance que no encuentran empresas a las que ofrecer sus servicios.",
        "keywords": ["diseñador web sin clientes", "web designer no clients", "freelance web design clients", "find web design clients", "no encuentro clientes", "need a site", "find businesses that"],
        "positive": ["Soy diseñador web y no encuentro clientes, ¿qué hago?"],
        "negative": ["Aprende diseño web gratis"],
        "priority": "high",
    },
    {
        "name": "Prospección mediante Google Maps",
        "description": "Uso de Google Maps / Google Business Profile para encontrar negocios locales a contactar.",
        "keywords": ["google maps scraping", "prospectar en google maps", "google maps leads", "scrape google maps", "google my business leads", "google maps", "prospecting on google"],
        "positive": ["¿Alguna herramienta para sacar leads de Google Maps?"],
        "negative": ["Cómo llegar en coche usando Google Maps"],
        "priority": "medium",
    },
    {
        "name": "Negocios que necesitan una página web",
        "description": "Negocios locales sin web o con una web anticuada, oportunidad para agencias/freelancers.",
        "keywords": ["negocio sin pagina web", "business without a website", "local business no website", "outdated website", "outdated site", "sin pagina web", "no tienen web", "ni web", "tienen web"],
        "positive": ["Muchos negocios de mi ciudad no tienen ni web"],
        "negative": ["Cómo hacer mi propia web con Wordpress"],
        "priority": "medium",
    },
    {
        "name": "SEO local",
        "description": "Profesionales de SEO local buscando clientes o consejo sobre posicionamiento local.",
        "keywords": ["seo local", "local seo", "posicionamiento local", "google business profile", "local search ranking"],
        "positive": ["¿Cómo consigo clientes de SEO local?"],
        "negative": ["Curso de SEO técnico avanzado"],
        "priority": "high",
    },
    {
        "name": "Generación de leads",
        "description": "Estrategias y herramientas para generar leads B2B o locales.",
        "keywords": ["generar leads", "lead generation", "generación de leads", "cold outreach", "lead gen agency"],
        "positive": ["¿Qué estrategias usáis para generar leads?"],
        "negative": ["Compra leads calientes aquí"],
        "priority": "medium",
    },
    {
        "name": "Priorización de oportunidades",
        "description": "Cómo decidir a qué negocio contactar primero cuando hay muchas oportunidades.",
        "keywords": ["priorizar leads", "prioritize leads", "which leads to contact first", "priorizar oportunidades", "lead scoring", "prioritize", "priorizar", "lead prioritization"],
        "positive": ["Tengo 200 leads y no sé por cuál empezar"],
        "negative": ["Prioriza tu salud mental"],
        "priority": "high",
    },
    {
        "name": "Seguimiento comercial",
        "description": "Seguimiento y follow-up de prospectos y clientes potenciales.",
        "keywords": ["seguimiento de clientes", "follow up with prospects", "sales follow up", "seguimiento comercial"],
        "positive": ["¿Cada cuánto hacéis seguimiento a un prospecto?"],
        "negative": ["Seguimiento médico postoperatorio"],
        "priority": "medium",
    },
    {
        "name": "CRM para agencias pequeñas",
        "description": "Recomendaciones de CRM sencillo y asequible para agencias pequeñas o freelancers.",
        "keywords": ["crm para agencias", "crm for small agency", "simple crm recommendation", "crm barato", "best crm for freelancers"],
        "positive": ["¿Qué CRM sencillo recomendáis para una agencia de 3 personas?"],
        "negative": ["CRM enterprise para 5000 empleados"],
        "priority": "high",
    },
    {
        "name": "Automatización de prospección",
        "description": "Automatizar tareas repetitivas del proceso de prospección comercial.",
        "keywords": ["automatizar prospección", "automate outreach", "prospecting automation", "outreach automation tool"],
        "positive": ["¿Cómo automatizáis la prospección sin sonar a spam?"],
        "negative": ["Automatiza tu casa con Home Assistant"],
        "priority": "medium",
    },
]

# (subreddit, language, title, body, num_comments, hours_ago)
CONVERSATIONS = [
    ("agency", "es", "Agencia de 2 personas, ¿cómo conseguimos los primeros clientes locales?",
     "Montamos hace 3 meses una pequeña agencia de marketing digital y nos cuesta encontrar clientes locales. "
     "¿Cómo priorizáis a qué negocios contactar primero? Sentimos que perdemos mucho tiempo investigando negocios "
     "que luego no encajan.", 6, 5),
    ("web_design", "en", "Freelance web designer, can't find businesses that actually need a site",
     "I'm a freelance web designer and I know there must be small businesses out there with outdated sites, but "
     "I don't know how to find them efficiently. Any tool or method that works for you?", 9, 20),
    ("sales", "en", "What's your process for prospecting on Google Maps?",
     "I keep hearing people say Google Maps is a goldmine for finding local business leads but manually going "
     "business by business is painfully slow. Is there any tool you use to speed this up and still stay compliant?", 4, 10),
    ("agency", "en", "We have 300+ leads and no idea who to contact first",
     "Our agency has been collecting leads for months and now we're drowning in a spreadsheet with 300+ rows. "
     "How do you all prioritize which ones to reach out to first? We're wasting time on ones that go nowhere.", 3, 8),
    ("localseo", "es", "Freelance de SEO local buscando clientes recurrentes",
     "Llevo un año haciendo SEO local para un par de clientes pero necesito escalar. ¿Cómo encontráis negocios "
     "que realmente necesiten mejorar su posicionamiento local?", 2, 30),
    ("SaaS", "en", "Any tool you'd recommend to prioritize which local businesses to contact first?",
     "Building an agency on the side and looking for a tool that helps score/prioritize leads based on real need "
     "signals instead of just a flat list. Any recommendations?", 5, 3),
    ("smallbusiness", "en", "Best pizza place in my neighborhood just closed, so sad",
     "Anyone else devastated when their favorite local spot shuts down? RIP Tony's Pizza, you will be missed.", 12, 40),
    ("freelance", "en", "Hiring a junior developer, unpaid trial period first",
     "We are hiring a junior developer for a 2-week unpaid trial before we consider a paid contract. Send your CV "
     "if interested.", 1, 15),
    ("Entrepreneur", "en", "Check out my course on how I made $10k in a month",
     "I just launched my course teaching you exactly how I made $10k in 30 days. Link in bio, limited spots!", 20, 12),
    ("startups", "en", "when the investor asks about your moat", "", 45, 6),
    ("marketing", "en", "I built a lead scoring tool, thoughts?",
     "I built my own tool for scoring inbound leads and I think it's amazing, way better than anything else out "
     "there. Everyone should be using it honestly.", 3, 18),
    ("agency", "es", "¿Alguna herramienta para priorizar leads antes de contactarlos?",
     "Estoy montando el proceso de prospección de mi agencia y busco algo que me ayude a priorizar leads según "
     "señales reales (web anticuada, sin reseñas, etc.) en vez de ir a ciegas. ¿Qué usáis vosotros?", 7, 4),
    ("EntrepreneurRideAlong", "es", "Documentando cómo construyo mi primera agencia desde cero",
     "Voy a ir compartiendo el proceso de montar mi agencia de servicios digitales. Ahora mismo el mayor reto es "
     "encontrar y priorizar negocios locales a los que ofrecer mis servicios. ¿Consejos?", 8, 26),
    ("SaaSDevelopers", "en", "Built a CRM feature for lead prioritization, feedback welcome",
     "Working on a side project that scores leads by need signals for small agencies. Would love feedback from "
     "anyone who's dealt with lead prioritization pain before.", 6, 14),
    ("web_design", "es", "Negocios sin página web en mi ciudad, ¿oportunidad real?",
     "He notado que muchos negocios locales ni siquiera tienen web. ¿Merece la pena especializarse en contactar "
     "este tipo de negocios como freelance?", 5, 22),
    ("thesidehustle", "en", "Side hustle idea: helping local businesses get found online",
     "Thinking about starting a side hustle helping small local businesses improve their online presence (SEO, "
     "website, Google profile). Anyone doing something similar? How do you find your first clients?", 10, 33),
    ("sales", "es", "¿Cada cuánto hacéis seguimiento comercial a un lead que no responde?",
     "Tengo varios prospectos que no han respondido tras el primer contacto. ¿Cuál es vuestro proceso de "
     "seguimiento antes de darlos por perdidos?", 3, 9),
    ("SideProject", "en", "Launched a tiny tool to track which reddit threads are worth replying to",
     "Built this for myself: it scores reddit conversations based on relevance and promotional risk so I know "
     "which ones are worth a real reply. Curious if this resonates with anyone else doing organic outreach.", 4, 2),
    ("smallbusiness", "en", "Crypto payments for my local bakery, good idea?",
     "Thinking about accepting bitcoin at my bakery, anyone doing this already?", 7, 28),
    ("marketing", "es", "¿Qué CRM sencillo recomendáis para una agencia pequeña?",
     "Somos 3 personas y el Excel ya se nos queda corto. Buscamos un CRM barato y simple, sin mil funciones que no "
     "vamos a usar. ¿Qué usáis?", 11, 7),
]


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    settings = get_settings()
    async with AsyncSessionLocal() as session:
        from app.core.security import issue_dev_login
        from app.models.conversation import Conversation, ConversationAction

        profile = await issue_dev_login(session, settings, DEMO_EMAIL)
        account = (await session.execute(select(Account).where(Account.id == profile.account_id))).scalars().first()

        alert_settings = (
            await session.execute(select(AlertSettings).where(AlertSettings.account_id == account.id))
        ).scalars().first()
        if not alert_settings:
            session.add(AlertSettings(account_id=account.id, email_recipient=""))

        community_rows = {
            c.name: c
            for c in (
                await session.execute(select(Community).where(Community.account_id == account.id))
            ).scalars().all()
        }
        for name, group, priority in COMMUNITIES:
            if name not in community_rows:
                community_rows[name] = Community(
                    account_id=account.id, name=name, group=group, priority=priority, primary_language="en"
                )
                session.add(community_rows[name])
        await session.flush()

        watch_profile = (
            await session.execute(
                select(WatchProfile).where(
                    WatchProfile.account_id == account.id,
                    WatchProfile.name.in_(["Captación de usuarios para Radarin", "Captacion de usuarios para Radarin"]),
                )
            )
        ).scalars().first()
        if not watch_profile:
            watch_profile = WatchProfile(
                account_id=account.id,
                name="Captacion de usuarios para Radarin",
                languages="es,en",
                max_age_hours=72,
            )
            session.add(watch_profile)
            await session.flush()
        existing_links = {
            link.community_id
            for link in (
                await session.execute(
                    select(WatchProfileCommunity).where(WatchProfileCommunity.watch_profile_id == watch_profile.id)
                )
            ).scalars().all()
        }
        for community in community_rows.values():
            if community.id not in existing_links:
                session.add(WatchProfileCommunity(watch_profile_id=watch_profile.id, community_id=community.id))

        topic_rows = {
            topic.name: topic
            for topic in (
                await session.execute(select(Topic).where(Topic.account_id == account.id))
            ).scalars().all()
        }
        for t in TOPICS:
            if t["name"] in topic_rows:
                continue
            topic = Topic(
                account_id=account.id,
                name=t["name"],
                description=t["description"],
                priority=t["priority"],
                positive_examples=t["positive"],
                negative_examples=t["negative"],
            )
            topic.keywords = [TopicKeyword(phrase=p) for p in t["keywords"]]
            topic.exclusions = [TopicExclusion(phrase=p) for p in COMMON_EXCLUSIONS]
            session.add(topic)
            topic_rows[topic.name] = topic
        await session.commit()

        now = datetime.now(timezone.utc)
        created = 0
        refreshed = 0
        for index, (subreddit, language, title, body, num_comments, hours_ago) in enumerate(CONVERSATIONS, start=1):
            published_at = now - timedelta(hours=hours_ago)
            stable_url = f"https://reddit.com/r/{subreddit}/comments/demo{index:02d}/"
            existing = (
                await session.execute(
                    select(Conversation).where(
                        Conversation.account_id == account.id,
                        Conversation.is_demo.is_(True),
                        Conversation.raw_title.in_([f"[DEMO] {title}", title]),
                    )
                )
            ).scalars().first()
            if existing:
                # Only demo rows are touched. Manual/user rows are never
                # relativized, and stable identity makes reruns idempotent.
                existing.published_at = published_at
                existing.detected_at = now - timedelta(hours=max(hours_ago - 1, 0))
                existing.num_comments = num_comments
                if existing.raw_title is not None:
                    existing.raw_title = f"[DEMO] {title}"
                    existing.raw_body = body
                refreshed += 1
                continue

            convo = Conversation(
                account_id=account.id,
                source_mode=SourceMode.demo,
                reddit_post_id=f"demo{index:02d}",
                url=stable_url,
                url_normalized=normalize_url(stable_url),
                dedupe_hash=compute_dedupe_hash(subreddit, title, published_at),
                subreddit=subreddit,
                language=language,
                raw_title=f"[DEMO] {title}",
                raw_body=body,
                raw_author=None,
                expires_at=None,
                published_at=published_at,
                detected_at=now - timedelta(hours=max(hours_ago - 1, 0)),
                num_comments=num_comments,
                is_demo=True,
            )
            session.add(convo)
            await session.flush()
            session.add(
                ConversationAction(
                    conversation_id=convo.id,
                    account_id=account.id,
                    action_type="imported",
                    payload={"source_mode": "demo"},
                )
            )
            await jobs_service._analyze_one(session, convo, settings)
            created += 1

        await session.commit()
        logger.info("Demo data synchronized account_id=%s created=%s refreshed=%s", account.id, created, refreshed)


if __name__ == "__main__":
    asyncio.run(main())
