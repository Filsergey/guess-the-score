import asyncio
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import get_settings
from app.database import get_db
from app.models import Player, Team, User
from app.providers.sstats import SStatsProvider

router = APIRouter(tags=["players"])
settings = get_settings()
CATALOG_REFRESH_DAYS = 7
POPULAR_TOKENS = ("mbappe","мбаппе","kane","кейн","haaland","холанд","yamal","ямаль","vinicius","винисиус","dembele","дембеле","saka","сака","bellingham","беллингем","pedri","педри","wirtz","вирц","musiala","мусиала","lautaro","лаутаро")


def _pick(data: dict, *names: str, default=None):
    for name in names:
        if name in data:
            return data[name]
    return default


def _items(payload: dict) -> list[dict]:
    rows = payload.get("data") or payload.get("response") or []
    return rows if isinstance(rows, list) else []


def _player_name(row: dict) -> str | None:
    direct = _pick(row, "name", "Name")
    if direct: return str(direct).strip()
    first = str(_pick(row, "firstName", "FirstName", default="") or "").strip()
    last = str(_pick(row, "lastName", "LastName", default="") or "").strip()
    return " ".join(x for x in (first,last) if x) or None


def _nationality(value) -> str | None:
    if isinstance(value, dict):
        value = _pick(value, "name", "Name", "code", "Code")
    return str(value)[:64] if value else None


def _position(row: dict) -> str | None:
    value = _pick(row,"positionName","PositionName","position","Position")
    if isinstance(value,dict): value=_pick(value,"name","Name")
    return str(value)[:80] if value else None


def _is_popular(name: str | None) -> bool:
    low=(name or "").casefold(); return any(token in low for token in POPULAR_TOKENS)


async def _download_photo(client: httpx.AsyncClient, url: str | None):
    if not url or not str(url).startswith("https://"): return None,None
    try:
        r=await client.get(str(url),headers={"User-Agent":"guess-the-score/1.0"})
        ctype=(r.headers.get("content-type") or "").split(";")[0].lower()
        if r.status_code==200 and r.content and ctype.startswith("image/") and len(r.content)<=2*1024*1024:
            return r.content,ctype
    except Exception:
        pass
    return None,None


def _apply_player_row(player: Player, row: dict, team: Team | None, season: int | None) -> None:
    name=_player_name(row)
    if name:
        player.name=name; player.display_name=name
    player.team_provider_id=team.provider_id if team else player.team_provider_id
    player.team_name=team.name if team else player.team_name
    player.position=_position(row) or player.position
    player.shirt_number=_pick(row,"shirtNumber","ShirtNumber","number","Number",default=player.shirt_number)
    player.nationality=_nationality(_pick(row,"nationality","Nationality",default=player.nationality))
    photo=_pick(row,"photoUrl","PhotoUrl")
    if photo: player.photo_source_url=str(photo)
    player.has_photo=bool(player.photo_source_url or player.photo_data)
    player.is_active=True; player.is_popular=_is_popular(player.name); player.season=season; player.updated_at=datetime.now(timezone.utc)


async def sync_sstats_team_players(db: AsyncSession, team: Team, season: int | None = None) -> dict:
    payload=await SStatsProvider().get_players(team_id=team.provider_id,limit=1000)
    rows=_items(payload); ids=[]; saved=0; photo_urls=0
    for row in rows:
        raw_id=_pick(row,"id","Id")
        if raw_id is None: continue
        pid=int(raw_id); ids.append(pid)
        player=await db.scalar(select(Player).where(Player.provider=="sstats",Player.provider_id==pid))
        if player is None:
            name=_player_name(row) or f"Player {pid}"
            player=Player(provider="sstats",provider_id=pid,name=name)
            db.add(player)
        _apply_player_row(player,row,team,season)
        if player.photo_source_url: photo_urls+=1
        saved+=1
    if ids:
        stale=(await db.execute(select(Player).where(Player.provider=="sstats",Player.team_provider_id==team.provider_id,Player.is_active.is_(True),Player.provider_id.not_in(set(ids))))).scalars().all()
        for p in stale: p.is_active=False; p.updated_at=datetime.now(timezone.utc)
    await db.commit()
    return {"provider":"sstats","team_id":team.provider_id,"team":team.name,"received":len(rows),"saved":saved,"photo_urls":photo_urls}


async def _refresh_player_detail(db: AsyncSession, player: Player) -> None:
    if player.provider!="sstats": return
    try:
        payload=await SStatsProvider().get_player(player.provider_id)
        row=payload.get("data") or payload.get("response") or {}
        if isinstance(row,list): row=row[0] if row else {}
        if not isinstance(row,dict): return
        team=None
        if player.team_provider_id:
            team=await db.scalar(select(Team).where(Team.provider=="sstats",Team.provider_id==player.team_provider_id))
        _apply_player_row(player,row,team,player.season)
        await db.commit()
    except Exception:
        await db.rollback()


async def _player_rows(db,q,popular,limit):
    cols=(Player.id,Player.provider,Player.provider_id,Player.name,Player.display_name,Player.team_name,Player.position,Player.shirt_number,Player.nationality,Player.is_popular,Player.photo_source_url,(Player.photo_data.is_not(None)).label("has_photo_blob"))
    base=select(*cols).where(Player.is_active.is_(True),Player.provider=="sstats")
    if q:
        like=f"%{q.strip()}%"; base=base.where(or_(Player.name.ilike(like),Player.display_name.ilike(like),Player.team_name.ilike(like)))
    if popular:
        rows=(await db.execute(base.where(Player.is_popular.is_(True)).order_by(Player.name).limit(limit))).all()
        if rows:return rows
    return (await db.execute(base.order_by(Player.is_popular.desc(),Player.name).limit(limit))).all()


@router.get("/api/players")
async def list_players(q:str|None=Query(default=None,max_length=100),popular:bool=False,limit:int=Query(default=30,ge=1,le=100),user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    del user; rows=await _player_rows(db,q,popular,limit)
    return {"count":len(rows),"response":[{"id":r.id,"provider":r.provider,"provider_id":r.provider_id,"name":r.name,"display_name":r.display_name or r.name,"team":r.team_name,"position":r.position,"number":r.shirt_number,"nationality":r.nationality,"photo":f"/api/players/{r.id}/photo" if (r.has_photo_blob or r.photo_source_url) else None,"has_photo":bool(r.has_photo_blob or r.photo_source_url),"popular":r.is_popular} for r in rows]}


@router.get("/api/players/catalog-status",include_in_schema=False)
async def player_catalog_status(db:AsyncSession=Depends(get_db)):
    total=(await db.execute(select(func.count(Player.id)).where(Player.provider=="sstats"))).scalar_one(); active=(await db.execute(select(func.count(Player.id)).where(Player.provider=="sstats",Player.is_active.is_(True)))).scalar_one(); with_source=(await db.execute(select(func.count(Player.id)).where(Player.provider=="sstats",Player.photo_source_url.is_not(None)))).scalar_one(); with_blob=(await db.execute(select(func.count(Player.id)).where(Player.provider=="sstats",Player.photo_data.is_not(None)))).scalar_one()
    return {"provider":"sstats","total":total,"active":active,"with_photo_source":with_source,"with_photo_blob":with_blob}


@router.get("/api/players/{player_id}/photo",include_in_schema=False)
async def player_photo(player_id:int,db:AsyncSession=Depends(get_db)):
    p=await db.get(Player,player_id)
    if not p or p.provider!="sstats": raise HTTPException(404,"Player not found")
    if p.photo_data: return Response(content=p.photo_data,media_type=p.photo_media_type or "image/jpeg",headers={"Cache-Control":"public, max-age=604800, immutable"})
    if not p.photo_source_url: await _refresh_player_detail(db,p)
    if p.photo_source_url:
        async with httpx.AsyncClient(timeout=8,follow_redirects=True) as client: data,ctype=await _download_photo(client,p.photo_source_url)
        if data:
            p.photo_data=data; p.photo_media_type=ctype; p.has_photo=True; await db.commit()
            return Response(content=data,media_type=ctype or "image/jpeg",headers={"Cache-Control":"public, max-age=604800, immutable"})
    raise HTTPException(404,"Player photo not found")


@router.post("/api/admin/players/sync")
async def sync_catalog(limit_teams:int|None=Query(default=None,ge=1,le=100),x_admin_token:str|None=Header(default=None),db:AsyncSession=Depends(get_db)):
    if not settings.admin_sync_token: raise HTTPException(503,"ADMIN_SYNC_TOKEN is not configured")
    if x_admin_token!=settings.admin_sync_token: raise HTTPException(401,"Invalid admin token")
    q=select(Team).where(Team.provider=="sstats").order_by(Team.id)
    if limit_teams is not None:q=q.limit(limit_teams)
    teams=(await db.execute(q)).scalars().all(); results=[]
    for team in teams:
        try: results.append(await sync_sstats_team_players(db,team))
        except Exception as e:
            await db.rollback(); results.append({"team_id":team.provider_id,"team":team.name,"error":type(e).__name__})
    total=(await db.execute(select(func.count(Player.id)).where(Player.provider=="sstats"))).scalar_one()
    return {"provider":"sstats","teams_processed":len(results),"total_players":total,"results":results}


async def _team_catalog_needs_refresh(db: AsyncSession, team: Team) -> bool:
    rows=(await db.execute(select(Player.updated_at).where(Player.provider=="sstats",Player.team_provider_id==team.provider_id,Player.is_active.is_(True)))).scalars().all()
    if len(rows)<10:return True
    last=max((x for x in rows if x),default=None)
    if not last:return True
    if last.tzinfo is None:last=last.replace(tzinfo=timezone.utc)
    return last<datetime.now(timezone.utc)-timedelta(days=CATALOG_REFRESH_DAYS)


async def bootstrap_popular_players():
    """Best-effort SStats squad cache warmup; never blocks application startup."""
    from app.database import SessionLocal
    try:
        async with SessionLocal() as db:
            teams=(await db.execute(select(Team).where(Team.provider=="sstats").order_by(Team.id))).scalars().all()
            for team in teams:
                try:
                    if await _team_catalog_needs_refresh(db,team):
                        await sync_sstats_team_players(db,team); await asyncio.sleep(.1)
                except Exception:
                    await db.rollback()
    except Exception:
        return
