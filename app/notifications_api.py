import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import LeagueMember, User, UserLeague
from app.notification_models import LeagueTelegramChat
from app.profile_models import UserProfile
from app.services.notifications import DEFAULT_NOTIFICATION_PREFERENCES, _send_telegram, normalize_preferences

router=APIRouter(prefix='/notifications',tags=['notifications'])

class PreferencesBody(BaseModel):
    prediction_reminders:bool|None=None
    participant_activity:bool|None=None
    match_start:bool|None=None
    match_results:bool|None=None
    daily_digest:bool|None=None
    match_videos:bool|None=None
    timezone:str|None=Field(default=None,max_length=80)

class LeagueChatBody(BaseModel):
    chat_id:int

async def _profile(db:AsyncSession,user_id:int,create:bool=False)->UserProfile|None:
    p=await db.scalar(select(UserProfile).where(UserProfile.user_id==user_id))
    if p is None and create:
        p=UserProfile(user_id=user_id);db.add(p);await db.flush()
    return p

def _raw(profile:UserProfile|None)->dict:
    try:return json.loads(profile.notification_preferences or '{}') if profile else {}
    except Exception:return {}

@router.get('/preferences')
async def get_preferences(user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db))->dict:
    p=await _profile(db,user.id);raw=_raw(p);prefs=normalize_preferences(raw)
    return {'preferences':prefs,'timezone':raw.get('_timezone') or 'Europe/Moscow'}

@router.put('/preferences')
async def put_preferences(body:PreferencesBody,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db))->dict:
    p=await _profile(db,user.id,True);raw=_raw(p);prefs=normalize_preferences(raw)
    supplied=body.model_dump(exclude_none=True)
    tz=supplied.pop('timezone',None)
    for key,value in supplied.items():
        if key in DEFAULT_NOTIFICATION_PREFERENCES:prefs[key]=bool(value)
    if tz:raw['_timezone']=tz.strip() or 'Europe/Moscow'
    raw.update(prefs);p.notification_preferences=json.dumps(raw,ensure_ascii=False);p.updated_at=datetime.now(timezone.utc)
    await db.commit();await db.refresh(p)
    return {'preferences':prefs,'timezone':raw.get('_timezone') or 'Europe/Moscow'}

async def _owner_league(db:AsyncSession,league_id:int,user:User)->UserLeague:
    league=await db.get(UserLeague,league_id)
    if league is None:raise HTTPException(404,'Лига не найдена')
    if league.owner_user_id!=user.id and user.role!='superadmin':raise HTTPException(403,'Привязать чат может только владелец лиги')
    return league

@router.get('/leagues/{league_id}/telegram-chat')
async def get_league_chat(league_id:int,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db))->dict:
    membership=await db.scalar(select(LeagueMember.id).where(LeagueMember.league_id==league_id,LeagueMember.user_id==user.id))
    if not membership and user.role!='superadmin':raise HTTPException(403,'Нет доступа к лиге')
    binding=await db.scalar(select(LeagueTelegramChat).where(LeagueTelegramChat.league_id==league_id))
    return {'linked':binding is not None,'chat_id':binding.chat_id if binding else None}

@router.put('/leagues/{league_id}/telegram-chat')
async def put_league_chat(league_id:int,body:LeagueChatBody,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db))->dict:
    league=await _owner_league(db,league_id,user)
    if not await _send_telegram(body.chat_id,f'⚽ Чат привязан к лиге «{league.name}». Уведомления об активности участников будут приходить сюда.'):
        raise HTTPException(422,'Не удалось отправить сообщение в этот чат. Добавь бота в чат и выдай ему право отправлять сообщения.')
    binding=await db.scalar(select(LeagueTelegramChat).where(LeagueTelegramChat.league_id==league_id))
    if binding is None:binding=LeagueTelegramChat(league_id=league_id,chat_id=body.chat_id,bound_by_user_id=user.id);db.add(binding)
    else:binding.chat_id=body.chat_id;binding.bound_by_user_id=user.id;binding.updated_at=datetime.now(timezone.utc)
    await db.commit()
    return {'linked':True,'chat_id':body.chat_id}

@router.delete('/leagues/{league_id}/telegram-chat')
async def delete_league_chat(league_id:int,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db))->dict:
    await _owner_league(db,league_id,user);binding=await db.scalar(select(LeagueTelegramChat).where(LeagueTelegramChat.league_id==league_id))
    if binding:await db.delete(binding);await db.commit()
    return {'linked':False,'chat_id':None}
