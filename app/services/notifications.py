import asyncio
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
from pywebpush import WebPushException, webpush
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import SessionLocal
from app.match_status import is_final_status
from app.models import LeagueMember, Match, Prediction, Team, Tournament, User, UserLeague
from app.notification_models import NotificationDelivery
from app.profile_models import UserProfile
from app.push_models import PushSubscription

settings=get_settings()
DEFAULT_NOTIFICATION_PREFERENCES={
    'prediction_reminders':False,
    'participant_activity':False,
    'match_start':False,
    'match_results':False,
    'daily_digest':False,
    'match_videos':False,
}
SERVICE_STARTED_AT=datetime.now(timezone.utc)
ADMIN_PWA_TEST_EVENT='manual:pwa-test:2026-09-08-v1'
FACTS=[
    'Первый чемпионат мира прошёл в 1930 году в Уругвае.',
    'Размер футбольных ворот — 7,32 × 2,44 метра.',
    'Жёлтые и красные карточки впервые использовали на чемпионате мира 1970 года.',
    'Правило офсайда существовало уже в первых официальных футбольных правилах XIX века.',
    'Пенальти исполняется с расстояния 11 метров от линии ворот.',
    'Финал чемпионата мира 1950 года на «Маракане» собрал одну из крупнейших аудиторий в истории футбола.',
    'Традиционный футбольный матч длится 90 минут: два тайма по 45.',
]


def normalize_preferences(value:str|dict|None)->dict:
    if isinstance(value,dict):raw=value
    else:
        try:raw=json.loads(value or '{}')
        except Exception:raw={}
    return {k:(bool(raw[k]) if k in raw else v) for k,v in DEFAULT_NOTIFICATION_PREFERENCES.items()}

async def user_preferences(db:AsyncSession,user_id:int)->dict:
    profile=await db.scalar(select(UserProfile).where(UserProfile.user_id==user_id))
    return normalize_preferences(profile.notification_preferences if profile else None)

async def _already_sent(db:AsyncSession,user_id:int,event_key:str,channel:str)->bool:
    return await db.scalar(select(NotificationDelivery.id).where(NotificationDelivery.user_id==user_id,NotificationDelivery.event_key==event_key,NotificationDelivery.channel==channel)) is not None

async def _mark_sent(db:AsyncSession,user_id:int,event_key:str,channel:str)->None:
    if not await _already_sent(db,user_id,event_key,channel):
        db.add(NotificationDelivery(user_id=user_id,event_key=event_key,channel=channel))
        await db.commit()

async def _send_webpush(subscription:PushSubscription,payload:dict)->None:
    private_key=(settings.webpush_vapid_private_key or '').strip();subject=(settings.webpush_subject or '').strip() or 'mailto:admin@example.com'
    if not private_key:return
    info={'endpoint':subscription.endpoint,'keys':{'p256dh':subscription.p256dh,'auth':subscription.auth}}
    await asyncio.to_thread(webpush,subscription_info=info,data=json.dumps(payload,ensure_ascii=False),vapid_private_key=private_key,vapid_claims={'sub':subject},ttl=3600,timeout=8)

async def _send_telegram(chat_id:int|str,text:str)->bool:
    token=(settings.telegram_bot_token or '').strip()
    if not token:return False
    try:
        async with httpx.AsyncClient(timeout=7.0) as client:
            r=await client.post(f'https://api.telegram.org/bot{token}/sendMessage',json={'chat_id':chat_id,'text':text,'disable_web_page_preview':True})
            return r.is_success and bool((r.json() or {}).get('ok'))
    except Exception:return False

async def deliver_to_user(db:AsyncSession,user:User,event_key:str,pref_key:str,title:str,body:str,url:str='/',telegram_text:str|None=None)->dict:
    prefs=await user_preferences(db,user.id)
    if not prefs.get(pref_key,False):return {'push':0,'telegram':0,'skipped':'preference'}
    sent_push=0;sent_tg=0
    if not await _already_sent(db,user.id,event_key,'push'):
        subs=(await db.execute(select(PushSubscription).where(PushSubscription.user_id==user.id))).scalars().all()
        stale=[]
        for sub in subs:
            try:
                await _send_webpush(sub,{'title':title,'body':body,'url':url,'tag':event_key})
                sent_push+=1
            except WebPushException as exc:
                status=getattr(exc,'status_code',None) or getattr(getattr(exc,'response',None),'status_code',None)
                if status in {404,410}:stale.append(sub)
            except Exception:pass
        for sub in stale:await db.delete(sub)
        if sent_push or stale:await db.commit()
        if sent_push:await _mark_sent(db,user.id,event_key,'push')
    if user.telegram_id and not await _already_sent(db,user.id,event_key,'telegram'):
        ok=await _send_telegram(user.telegram_id,telegram_text or f'{title}\n{body}')
        if ok:
            sent_tg=1;await _mark_sent(db,user.id,event_key,'telegram')
    return {'push':sent_push,'telegram':sent_tg}

async def _send_superadmin_pwa_test_once(db:AsyncSession)->int:
    admins=(await db.execute(select(User).where(User.role=='superadmin'))).scalars().all();sent_total=0
    for user in admins:
        if await _already_sent(db,user.id,ADMIN_PWA_TEST_EVENT,'push'):continue
        subs=(await db.execute(select(PushSubscription).where(PushSubscription.user_id==user.id))).scalars().all();sent=0;stale=[]
        for sub in subs:
            try:
                await _send_webpush(sub,{
                    'title':'Тестовое уведомление ⚽',
                    'body':'PWA-уведомления «Угадай счёт» работают. Это тестовая отправка.',
                    'url':'/',
                    'tag':'gts-admin-pwa-test-v1',
                });sent+=1
            except WebPushException as exc:
                status=getattr(exc,'status_code',None) or getattr(getattr(exc,'response',None),'status_code',None)
                if status in {404,410}:stale.append(sub)
            except Exception:pass
        for sub in stale:await db.delete(sub)
        if stale:await db.commit()
        if sent:
            await _mark_sent(db,user.id,ADMIN_PWA_TEST_EVENT,'push');sent_total+=sent
            print(f'PWA admin test sent: user_id={user.id}, subscriptions={sent}',flush=True)
        elif subs:
            print(f'PWA admin test failed: user_id={user.id}, subscriptions={len(subs)}',flush=True)
    return sent_total

async def _league_members_for_match(db:AsyncSession,match:Match)->list[tuple[UserLeague,User]]:
    rows=(await db.execute(select(UserLeague,User).join(LeagueMember,LeagueMember.league_id==UserLeague.id).join(User,User.id==LeagueMember.user_id).where(UserLeague.tournament_provider==match.provider,UserLeague.tournament_season==match.season,UserLeague.tournament_id==match.tournament_id))).all()
    if rows:return rows
    return (await db.execute(select(UserLeague,User).join(LeagueMember,LeagueMember.league_id==UserLeague.id).join(User,User.id==LeagueMember.user_id).where(UserLeague.tournament_provider==match.provider,UserLeague.tournament_season==match.season))).all()

async def _match_names(db:AsyncSession,match:Match)->tuple[str,str]:
    h=await db.get(Team,match.home_team_id);a=await db.get(Team,match.away_team_id)
    return (h.name if h else 'Хозяева',a.name if a else 'Гости')

async def notify_prediction_activity(actor_id:int,match_id:int)->None:
    async with SessionLocal() as db:
        actor=await db.get(User,actor_id);match=await db.get(Match,match_id)
        if not actor or not match:return
        home,away=await _match_names(db,match);rows=await _league_members_for_match(db,match);seen=set();chats=set()
        for league,user in rows:
            if user.id!=actor.id and user.id not in seen:
                seen.add(user.id)
                await deliver_to_user(db,user,f'activity:match:{match.id}:actor:{actor.id}:u:{user.id}','participant_activity','Активность участников',f'{actor.display_name} сделал прогноз на {home} — {away}. Счёт откроется после старта.',f'/?match={match.id}')
            chat_id=getattr(league,'telegram_chat_id',None)
            if chat_id and chat_id not in chats:
                chats.add(chat_id);await _send_telegram(chat_id,f'👥 {actor.display_name} сделал прогноз на {home} — {away}. Счёт откроется после стартового свистка.')

async def notify_tournament_activity(actor_id:int,tournament_id:int|None,season:int)->None:
    async with SessionLocal() as db:
        actor=await db.get(User,actor_id)
        if not actor:return
        tournament=await db.get(Tournament,tournament_id) if tournament_id else None;name=tournament.name if tournament else 'турнир'
        stmt=select(UserLeague,User).join(LeagueMember,LeagueMember.league_id==UserLeague.id).join(User,User.id==LeagueMember.user_id).where(UserLeague.tournament_season==season)
        if tournament_id:stmt=stmt.where(UserLeague.tournament_id==tournament_id)
        rows=(await db.execute(stmt)).all();seen=set();chats=set()
        for league,user in rows:
            if user.id!=actor.id and user.id not in seen:
                seen.add(user.id);await deliver_to_user(db,user,f'activity:tournament:{tournament_id or 0}:{season}:actor:{actor.id}:u:{user.id}','participant_activity','Турнирный прогноз',f'{actor.display_name} заполнил прогноз на {name}.','/')
            chat_id=getattr(league,'telegram_chat_id',None)
            if chat_id and chat_id not in chats:
                chats.add(chat_id);await _send_telegram(chat_id,f'🏆 {actor.display_name} заполнил турнирный прогноз на {name}.')

async def _process_reminders(db:AsyncSession,now:datetime)->None:
    matches=(await db.execute(select(Match).where(Match.kickoff_at>=now+timedelta(minutes=50),Match.kickoff_at<=now+timedelta(minutes=70)))).scalars().all()
    for match in matches:
        home,away=await _match_names(db,match)
        for _,user in await _league_members_for_match(db,match):
            pred=await db.scalar(select(Prediction).where(Prediction.user_id==user.id,Prediction.match_id==match.id))
            body=(f'Матч {home} — {away} начнётся примерно через час. Твой прогноз {pred.home_score}:{pred.away_score} сохранён.' if pred else f'Матч {home} — {away} начнётся примерно через час. У тебя ещё нет прогноза.')
            await deliver_to_user(db,user,f'reminder:{match.id}','prediction_reminders','Матч через час',body,f'/?match={match.id}')

async def _process_starts(db:AsyncSession,now:datetime)->None:
    matches=(await db.execute(select(Match).where(Match.kickoff_at>=now-timedelta(minutes=8),Match.kickoff_at<=now+timedelta(minutes=1)))).scalars().all()
    for match in matches:
        home,away=await _match_names(db,match)
        for _,user in await _league_members_for_match(db,match):
            await deliver_to_user(db,user,f'start:{match.id}','match_start','Матч начался',f'{home} — {away}. Прогнозы участников теперь открыты.',f'/?match={match.id}')

async def _process_results(db:AsyncSession,now:datetime)->None:
    matches=(await db.execute(select(Match).where(Match.updated_at>=max(SERVICE_STARTED_AT-timedelta(minutes=2),now-timedelta(minutes=12))))).scalars().all()
    for match in matches:
        if not is_final_status(match.status_short):continue
        home,away=await _match_names(db,match);score=f'{match.home_goals}:{match.away_goals}'
        for _,user in await _league_members_for_match(db,match):
            pred=await db.scalar(select(Prediction).where(Prediction.user_id==user.id,Prediction.match_id==match.id));points=0
            if pred and match.home_goals is not None and match.away_goals is not None:
                if pred.home_score==match.home_goals and pred.away_score==match.away_goals:points=3
                elif (pred.home_score>pred.away_score)==(match.home_goals>match.away_goals) and (pred.home_score==pred.away_score)==(match.home_goals==match.away_goals):points=1
            suffix=f' Твой прогноз принёс {points} очк.' if pred else ' Прогноза на этот матч не было.'
            await deliver_to_user(db,user,f'result:{match.id}','match_results','Матч завершён',f'{home} — {away} {score}.{suffix}',f'/?match={match.id}')

async def _daily_for_user(db:AsyncSession,user:User,now:datetime)->None:
    profile=await db.scalar(select(UserProfile).where(UserProfile.user_id==user.id));raw={}
    if profile:
        try:raw=json.loads(profile.notification_preferences or '{}')
        except Exception:raw={}
    tzname=raw.get('_timezone') or 'Europe/Moscow'
    try:tz=ZoneInfo(tzname)
    except Exception:tz=ZoneInfo('Europe/Moscow')
    local=now.astimezone(tz)
    if not (local.hour==8 and local.minute<15):return
    day_key=local.date().isoformat();prefs=normalize_preferences(raw)
    if not prefs.get('daily_digest',False):return
    leagues=(await db.execute(select(UserLeague).join(LeagueMember,LeagueMember.league_id==UserLeague.id).where(LeagueMember.user_id==user.id))).scalars().all()
    tournament_ids={x.tournament_id for x in leagues if x.tournament_id};providers={(x.tournament_provider,x.tournament_season) for x in leagues}
    start=datetime.combine(local.date(),datetime.min.time(),tzinfo=tz).astimezone(timezone.utc);end=start+timedelta(days=1)
    stmt=select(Match).where(Match.kickoff_at>=start,Match.kickoff_at<end)
    matches=(await db.execute(stmt.order_by(Match.kickoff_at))).scalars().all();matches=[m for m in matches if (m.tournament_id in tournament_ids) or ((m.provider,m.season) in providers)]
    if matches:
        lines=[]
        for m in matches[:5]:
            h,a=await _match_names(db,m);lines.append(f'{m.kickoff_at.astimezone(tz).strftime("%H:%M")} — {h} — {a}')
        body='Сегодня: '+('; '.join(lines))
        if len(matches)>5:body+=f'. И ещё {len(matches)-5} матч(а).'
        title='Утренняя сводка Оракула'
    else:
        fact=FACTS[local.toordinal()%len(FACTS)];style=(profile.oracle_style if profile else 'irony')
        prefix={'merciless':'Оракул без пощады: ','irony':'Оракул напоминает: ','calm':'Факт дня: ','numbers':'Факт: '}.get(style,'Оракул: ')
        title='Футбольный факт дня';body=prefix+fact
    await deliver_to_user(db,user,f'daily:{day_key}','daily_digest',title,body,'/')

async def run_notification_cycle()->None:
    now=datetime.now(timezone.utc)
    async with SessionLocal() as db:
        await _send_superadmin_pwa_test_once(db)
        await _process_reminders(db,now);await _process_starts(db,now);await _process_results(db,now)
        users=(await db.execute(select(User))).scalars().all()
        for user in users:await _daily_for_user(db,user,now)

async def notification_scheduler_loop()->None:
    await asyncio.sleep(20)
    while True:
        try:await run_notification_cycle()
        except Exception:pass
        await asyncio.sleep(60)
