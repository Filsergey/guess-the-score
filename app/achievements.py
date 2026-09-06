from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth import get_current_user
from app.database import get_db
from app.leagues import _membership, _oracle_score
from app.models import LeagueMember, Match, OraclePrediction, Prediction, User, UserLeague
from app.predictions import prediction_points
from app.match_status import FINAL_MATCH_STATUSES
router=APIRouter(tags=['achievements'])
def _streak(values,needle):
 best=cur=0
 for v in values:cur=cur+1 if v==needle else 0;best=max(best,cur)
 return best
@router.get('/{league_id}/achievements')
async def achievements(league_id:int,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
 league=await db.get(UserLeague,league_id)
 if league is None:raise HTTPException(404,'League not found')
 await _membership(league_id,user,db);members=(await db.execute(select(LeagueMember,User).join(User,User.id==LeagueMember.user_id).where(LeagueMember.league_id==league_id))).all();matches=(await db.execute(select(Match).where(Match.provider==league.tournament_provider,Match.season==league.tournament_season,Match.status_short.in_(tuple(FINAL_MATCH_STATUSES)),Match.home_goals.is_not(None),Match.away_goals.is_not(None)).order_by(Match.kickoff_at))).scalars().all();ids=[m.id for m in matches];all_preds=(await db.execute(select(Prediction).where(Prediction.match_id.in_(ids)))).scalars().all() if ids else [];preds={(p.user_id,p.match_id):p for p in all_preds};oracle_rows=(await db.execute(select(OraclePrediction).where(OraclePrediction.match_id.in_(ids)))).scalars().all() if ids and league.include_oracle else [];oracle={p.match_id:p for p in oracle_rows};rows=[]
 for _,u in members:
  eligible=[m for m in matches if m.kickoff_at>=u.registered_at];points=[];exacts=outcomes=oracle_wins=unique_exacts=0
  for m in eligible:
   p=preds.get((u.id,m.id));pts=prediction_points(p,m) if p else None
   if pts is None:continue
   points.append(pts);exacts+=pts==3;outcomes+=pts==1;os=_oracle_score(oracle.get(m.id),m) if league.include_oracle else None
   if os is not None and pts>os[2]:oracle_wins+=1
   if pts==3:
    exact_count=0
    for _,other in members:
     if m.kickoff_at<other.registered_at:continue
     op=preds.get((other.id,m.id));exact_count+=bool(op and prediction_points(op,m)==3)
    osc=_oracle_score(oracle.get(m.id),m) if league.include_oracle else None
    if osc and osc[2]==3:exact_count+=1
    if exact_count==1:unique_exacts+=1
  badges=[]
  def add(code,title,icon,value,level=1):badges.append({'code':code,'title':title,'icon':icon,'value':value,'level':level})
  exact_streak=_streak(points,3);cur=best_hit=0
  for x in points:cur=cur+1 if x>0 else 0;best_hit=max(best_hit,cur)
  if exacts:add('sniper','Снайпер','🎯',exacts,3 if exacts>=10 else 2 if exacts>=5 else 1)
  if exact_streak>=2:add('exact_streak','Серия точных','🔥',exact_streak,3 if exact_streak>=4 else 2 if exact_streak>=3 else 1)
  if best_hit>=3:add('hit_streak','На серии','⚡',best_hit,3 if best_hit>=10 else 2 if best_hit>=6 else 1)
  if oracle_wins:add('oracle_hunter','Охотник на Оракула','✦',oracle_wins,3 if oracle_wins>=10 else 2 if oracle_wins>=5 else 1)
  if unique_exacts:add('only_one','Один такой','💎',unique_exacts,3 if unique_exacts>=5 else 2 if unique_exacts>=3 else 1)
  rows.append({'user_id':u.id,'display_name':u.display_name,'avatar_url':u.avatar_url,'is_me':u.id==user.id,'exacts':exacts,'outcomes':outcomes,'predictions':len(points),'best_exact_streak':exact_streak,'best_hit_streak':best_hit,'oracle_wins':oracle_wins,'unique_exacts':unique_exacts,'achievements':badges})
 rows.sort(key=lambda x:(-len(x['achievements']),-x['exacts'],-x['oracle_wins'],x['display_name'].casefold()));mine=next((x for x in rows if x['is_me']),None);return {'league_id':league_id,'count':len(rows),'mine':mine,'response':rows}
