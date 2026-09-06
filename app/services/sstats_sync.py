from datetime import datetime, timezone
import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.competitions.champions_league import classify_ucl_round
from app.models import Match, Team, Tournament
from app.providers.sstats import SStatsProvider
from app.providers.uefa import UEFAProvider

SSTATS_PROVIDER="sstats";CHAMPIONS_LEAGUE_ID=2;UEFA_CHAMPIONS_LEAGUE_ID=1
SSTATS_STATUSES={1:("TBD","Date/time to be defined"),2:("NS","Not started"),3:("1H","First half"),4:("HT","Half-time"),5:("2H","Second half"),6:("ET","Extra time"),7:("PEN_LIVE","Penalties in progress"),8:("FT","Full-time"),9:("AET","After extra time"),10:("PEN","Finished after penalties"),11:("ET_BREAK","Extra-time break"),12:("SUSP","Suspended"),13:("ABD","Abandoned"),14:("PST","Postponed"),15:("CANC","Cancelled"),17:("AWD","Technical loss"),18:("WO","Walkover"),19:("LIVE","In progress")}
def _pick(data,*names,default=None):
 for name in names:
  if name in data:return data[name]
 return default
def _parse_datetime(value):
 r=value if isinstance(value,datetime) else datetime.fromisoformat(str(value).strip().replace("Z","+00:00"));return r.replace(tzinfo=timezone.utc) if r.tzinfo is None else r
def _normalize_status(raw_status,raw_status_name=None):
 try:code=int(raw_status) if raw_status is not None else None
 except (TypeError,ValueError):code=None
 mapped=SSTATS_STATUSES.get(code);provider_name=str(raw_status_name).strip() if raw_status_name not in (None,"") else None
 if mapped:return mapped[0],provider_name or mapped[1]
 raw_text=None if raw_status is None else str(raw_status);return "UNKNOWN",provider_name or (f"SStats status {raw_text}" if raw_text is not None else None)
def _integrity_message(exc,game_id):
 orig=getattr(exc,"orig",None);parts=[f"game_id={game_id}"]
 for key in ("sqlstate","constraint_name","detail"):
  value=getattr(orig,key,None)
  if value:parts.append(f"{key}={value}")
 return "; ".join(parts)
def _norm(value):
 if not value:return ""
 text=value.casefold().replace("&"," and ").replace("’","'");text=(text.replace("ø","o").replace("ö","o").replace("ó","o").replace("ò","o").replace("ô","o").replace("ü","u").replace("ú","u").replace("ä","a").replace("á","a").replace("à","a").replace("é","e").replace("è","e").replace("í","i").replace("ñ","n").replace("ç","c"));text=re.sub(r"[^\w\s']+"," ",text,flags=re.UNICODE);tokens=[t for t in text.split() if t not in {"fc","cf","afc","fk","sc","ac","fa"}];normalized=" ".join(tokens);return {"atletico madrid":"atleti","atletico de madrid":"atleti","club atletico de madrid":"atleti","lask linz":"lask","sabah masazir":"sabah"}.get(normalized,normalized)
def _norm_code(value):return {"LAS":"LASK"}.get(re.sub(r"[^A-Z0-9]","",str(value or "").upper()),re.sub(r"[^A-Z0-9]","",str(value or "").upper()))
def _has_cyrillic(value):return bool(re.search(r"[А-Яа-яЁё]",value or ""))
def _items(payload):
 rows=payload.get("data") or payload.get("response") or [];return rows if isinstance(rows,list) else []
async def _get_or_create_tournament(session,item,league_id=None,league_name=None):
 provider_id=int(_pick(item,"leagueId","LeagueId",default=league_id or CHAMPIONS_LEAGUE_ID));t=await session.scalar(select(Tournament).where(Tournament.provider==SSTATS_PROVIDER,Tournament.provider_id==provider_id));name=_pick(item,"leagueName","LeagueName",default=league_name or "SStats")
 if t is None:t=Tournament(provider=SSTATS_PROVIDER,provider_id=provider_id,name=name);session.add(t);await session.flush()
 t.name=name;t.country=_pick(item,"countryName","CountryName");return t
async def _get_or_create_team(session,provider_id,name):
 team=await session.scalar(select(Team).where(Team.provider==SSTATS_PROVIDER,Team.provider_id==provider_id))
 if team is None:team=Team(provider=SSTATS_PROVIDER,provider_id=provider_id,name=name,source_name=name);session.add(team);await session.flush()
 else:
  team.source_name=name
  if not team.uefa_id and not _has_cyrillic(team.name):team.name=name
 return team
async def sync_sstats_competition(session,league_id:int,year:int,league_name:str|None=None):
 provider=SStatsProvider();payload,season_ref=await provider.competition_games(league_id,year);items=_items(payload);created=updated=skipped=classified_rounds=0;skip_reasons={};status_counts={};current_game_id=None;tournament=None
 try:
  for item in items:
   game_id=_pick(item,"id","Id");current_game_id=game_id;home_id=_pick(item,"homeTeamId","HomeTeamId");away_id=_pick(item,"awayTeamId","AwayTeamId");home_name=_pick(item,"homeTeamName","HomeTeamName");away_name=_pick(item,"awayTeamName","AwayTeamName");date_value=_pick(item,"date","Date");required={"game_id":game_id,"home_id":home_id,"away_id":away_id,"home_name":home_name,"away_name":away_name,"date":date_value};missing=[k for k,v in required.items() if v is None]
   if missing:skipped+=1;reason=",".join(missing);skip_reasons[reason]=skip_reasons.get(reason,0)+1;continue
   tournament=await _get_or_create_tournament(session,item,league_id,league_name);home_team=await _get_or_create_team(session,int(home_id),str(home_name));away_team=await _get_or_create_team(session,int(away_id),str(away_name));match=await session.scalar(select(Match).where(Match.provider==SSTATS_PROVIDER,Match.provider_id==int(game_id)));is_new=match is None;kickoff_at=_parse_datetime(date_value);season=int(_pick(item,"year","Year",default=year));home_goals=_pick(item,"scoreHome","ScoreHome","scoreHomeFT","ScoreHomeFT");away_goals=_pick(item,"scoreAway","ScoreAway","scoreAwayFT","ScoreAwayFT");status_short,status_long=_normalize_status(_pick(item,"status","Status"),_pick(item,"statusName","StatusName"));status_counts[status_short]=status_counts.get(status_short,0)+1;provider_round=_pick(item,"round","Round","roundName","RoundName");classified=classify_ucl_round(season,kickoff_at) if league_id==CHAMPIONS_LEAGUE_ID else None;round_name=provider_round or (classified["round_label"] if classified else None);classified_rounds+=int(not provider_round and bool(classified))
   if is_new:match=Match(provider=SSTATS_PROVIDER,provider_id=int(game_id),tournament_id=tournament.id,season=season,kickoff_at=kickoff_at,status_short=status_short,home_team_id=home_team.id,away_team_id=away_team.id);session.add(match)
   match.tournament_id=tournament.id;match.season=season;match.round_name=round_name;match.kickoff_at=kickoff_at;match.status_short=status_short;match.status_long=status_long;match.elapsed=None;match.home_team_id=home_team.id;match.away_team_id=away_team.id;match.home_goals=home_goals;match.away_goals=away_goals;match.updated_at=datetime.now(timezone.utc);await session.flush();created+=int(is_new);updated+=int(not is_new)
  await session.commit()
 except IntegrityError as exc:await session.rollback();raise RuntimeError("SStats database integrity error: "+_integrity_message(exc,current_game_id)) from exc
 return {"provider":SSTATS_PROVIDER,"league_id":league_id,"tournament_id":tournament.id if tournament else None,"year":year,"season_ref":{k:v for k,v in season_ref.items() if k!='raw'},"received":len(items),"created":created,"updated":updated,"classified_rounds":classified_rounds,"skipped":skipped,"skip_reasons":skip_reasons,"status_counts":status_counts}
async def sync_sstats_champions_league(session,year):
 result=await sync_sstats_competition(session,CHAMPIONS_LEAGUE_ID,year,"UEFA Champions League")
 try:result["team_metadata"]=await sync_sstats_team_metadata(session)
 except Exception as exc:await session.rollback();result["team_metadata"]={"error":type(exc).__name__}
 return result
async def sync_sstats_team_metadata(session,limit=None):
 provider=SStatsProvider();sstats_rows=_items(await provider.get_teams(limit=1000));sstats_by_id={int(_pick(r,"id","Id")):r for r in sstats_rows if _pick(r,"id","Id") is not None};query=select(Team).where(Team.provider==SSTATS_PROVIDER).order_by(Team.id)
 if limit is not None:query=query.limit(limit)
 teams=(await session.execute(query)).scalars().all()
 for team in teams:
  src=sstats_by_id.get(team.provider_id)
  if not src:continue
  source_name=str(_pick(src,"name","Name",default=team.source_name or team.name));team.source_name=source_name;country=_pick(src,"country","Country")
  if isinstance(country,dict):team.country_code=str(_pick(country,"code","Code",default="") or "")[:16] or team.country_code
  logo=_pick(src,"logoUrl","LogoUrl")
  if logo and not team.logo_url:team.logo_url=str(logo)
 now=datetime.now(timezone.utc);season=now.year+(1 if now.month>=7 else 0);sstats_season=season-1;matches=(await session.execute(select(Match).where(Match.provider==SSTATS_PROVIDER,Match.season==sstats_season))).scalars().all();main_ids={tid for m in matches if classify_ucl_round(sstats_season,m.kickoff_at) is not None for tid in (m.home_team_id,m.away_team_id) if tid is not None};uefa_teams=await UEFAProvider().competition_teams(UEFA_CHAMPIONS_LEAGUE_ID,season);by_name={};code_candidates={}
 for u in uefa_teams:
  for candidate in [u.international_name,u.name_ru,u.name,*list(getattr(u,"aliases",()) or ())]:
   key=_norm(candidate)
   if key:by_name[key]=u
  code=_norm_code(u.code)
  if code:code_candidates.setdefault(code,[]).append(u)
 by_code={c:r[0] for c,r in code_candidates.items() if len(r)==1};updated=0;unmatched_names=[];matched=set();main_unmatched=[];current={u.id for u in uefa_teams}
 for team in teams:
  if team.id not in main_ids:
   if team.uefa_id in current:team.uefa_id=None
   if len(unmatched_names)<40:unmatched_names.append(team.source_name or team.name)
   continue
  u=None
  for candidate in (team.source_name,team.name):
   key=_norm(candidate)
   if key and key in by_name:u=by_name[key];break
  if not u:
   code=_norm_code(team.code)
   if code:u=by_code.get(code)
  if not u:main_unmatched.append(team.source_name or team.name);continue
  matched.add(u.id);team.uefa_id=u.id
  if u.name_ru:team.name=u.name_ru
  if u.code:team.code=str(u.code)[:20]
  if u.country_code:team.country_code=str(u.country_code)[:16]
  logo=u.logo_medium_url or u.logo_url or u.logo_big_url or u.logo_small_url
  if logo:team.logo_url=logo
  updated+=1
 await session.commit();non_main=sum(1 for t in teams if t.id not in main_ids);return {"provider":"sstats","catalog_source":"sstats:/Teams/list","metadata_source":"uefa-standings","season_year":season,"teams_in_db":len(teams),"sstats_catalog":len(sstats_rows),"uefa_catalog":len(uefa_teams),"main_stage_teams":sum(1 for t in teams if t.id in main_ids),"updated":updated,"uefa_matched":len(matched),"uefa_unmatched":len(uefa_teams)-len(matched),"main_stage_unmatched":main_unmatched,"unmatched_non_uefa":non_main,"unmatched_names":unmatched_names}