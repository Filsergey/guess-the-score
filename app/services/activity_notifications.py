from sqlalchemy import select

from app.database import SessionLocal
from app.models import LeagueMember, Match, Team, Tournament, User, UserLeague
from app.notification_models import LeagueTelegramChat
from app.services.notifications import _send_telegram, deliver_to_user


async def _match_names(db,match:Match)->tuple[str,str]:
    h=await db.get(Team,match.home_team_id);a=await db.get(Team,match.away_team_id)
    return (h.name if h else 'Хозяева',a.name if a else 'Гости')

async def _rows_for_match(db,match:Match):
    stmt=select(UserLeague,User).join(LeagueMember,LeagueMember.league_id==UserLeague.id).join(User,User.id==LeagueMember.user_id).where(UserLeague.tournament_provider==match.provider,UserLeague.tournament_season==match.season)
    rows=(await db.execute(stmt)).all()
    exact=[r for r in rows if r[0].tournament_id==match.tournament_id]
    return exact or rows

async def _chat_id(db,league_id:int)->int|None:
    row=await db.scalar(select(LeagueTelegramChat).where(LeagueTelegramChat.league_id==league_id))
    return row.chat_id if row else None

async def notify_prediction_activity(actor_id:int,match_id:int)->None:
    async with SessionLocal() as db:
        actor=await db.get(User,actor_id);match=await db.get(Match,match_id)
        if not actor or not match:return
        home,away=await _match_names(db,match);rows=await _rows_for_match(db,match);seen_users=set();seen_chats=set()
        for league,user in rows:
            if user.id!=actor.id and user.id not in seen_users:
                seen_users.add(user.id)
                await deliver_to_user(db,user,f'activity:match:{match.id}:actor:{actor.id}:u:{user.id}','participant_activity','Активность участников',f'{actor.display_name} сделал прогноз на {home} — {away}. Счёт откроется после старта.',f'/?match={match.id}')
            cid=await _chat_id(db,league.id)
            if cid and cid not in seen_chats:
                seen_chats.add(cid);await _send_telegram(cid,f'👥 {actor.display_name} сделал прогноз на {home} — {away}. Счёт откроется после стартового свистка.')

async def notify_tournament_activity(actor_id:int,tournament_id:int|None,season:int)->None:
    async with SessionLocal() as db:
        actor=await db.get(User,actor_id)
        if not actor:return
        tournament=await db.get(Tournament,tournament_id) if tournament_id else None;name=tournament.name if tournament else 'турнир'
        stmt=select(UserLeague,User).join(LeagueMember,LeagueMember.league_id==UserLeague.id).join(User,User.id==LeagueMember.user_id).where(UserLeague.tournament_season==season)
        rows=(await db.execute(stmt)).all()
        if tournament_id:
            exact=[r for r in rows if r[0].tournament_id==tournament_id]
            if exact:rows=exact
        seen_users=set();seen_chats=set()
        for league,user in rows:
            if user.id!=actor.id and user.id not in seen_users:
                seen_users.add(user.id)
                await deliver_to_user(db,user,f'activity:tournament:{tournament_id or 0}:{season}:actor:{actor.id}:u:{user.id}','participant_activity','Турнирный прогноз',f'{actor.display_name} заполнил прогноз на {name}.','/')
            cid=await _chat_id(db,league.id)
            if cid and cid not in seen_chats:
                seen_chats.add(cid);await _send_telegram(cid,f'🏆 {actor.display_name} заполнил турнирный прогноз на {name}.')
