from collections import defaultdict
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
def _round_key(m):return (m.round_name or '').strip() or 'Без тура'
def _is_completed(m):return m.status_short in FINAL_MATCH_STATUSES and m.home_goals is not None and m.away_goals is not None
@router.get('/{league_id}/achievements')
async def achievements(league_id:int,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
 league=await db.get(UserLeague,league_id)
 if league is None:raise HTTPException(404,'League not found')
 await _membership(league_id,user,db);members=(await db.execute(select(LeagueMember,User).join(User,User.id==LeagueMember.user_id).where(LeagueMember.league_id==league_id))).all()
 all_matches=(await db.execute(select(Match).where(Match.provider==league.tournament_provider,Match.season==league.tournament_season).order_by(Match.kickoff_at))).scalars().all();matches=[m for m in all_matches if _is_completed(m)];ids=[m.id for m in matches]
 all_preds=(await db.execute(select(Prediction).where(Prediction.match_id.in_(ids)))).scalars().all() if ids else [];preds={(p.user_id,p.match_id):p for p in all_preds};oracle_rows=(await db.execute(select(OraclePrediction).where(OraclePrediction.match_id.in_(ids)))).scalars().all() if ids and league.include_oracle else [];oracle={p.match_id:p for p in oracle_rows}
 rounds_all=defaultdict(list)
 for m in all_matches:rounds_all[_round_key(m)].append(m)
 rows=[]
 for _,u in members:
  eligible=[m for m in matches if m.kickoff_at>=u.registered_at];points=[];exacts=outcomes=oracle_wins=unique_exacts=0
  for m in eligible:
   p=preds.get((u.id,m.id));pts=prediction_points(p,m) if p else None
   if pts is None:continue
   points.append(pts);exacts+=pts==3;outcomes+=pts==1;os=_oracle_score(oracle.get(m.id),m) if league.include_oracle else None
   if os is not None and pts>os[2]:oracle_wins+=1
   if pts==3:
    exact_count=sum(bool((op:=preds.get((other.id,m.id))) and m.kickoff_at>=other.registered_at and prediction_points(op,m)==3) for _,other in members);osc=_oracle_score(oracle.get(m.id),m) if league.include_oracle else None
    if osc and osc[2]==3:exact_count+=1
    if exact_count==1:unique_exacts+=1
  badges=[]
  def add(code,title,icon,value,level=1,subtitle=None):badges.append({'code':code,'title':title,'icon':icon,'value':value,'level':level,'subtitle':subtitle})
  exact_streak=_streak(points,3);cur=best_hit=0
  for x in points:cur=cur+1 if x>0 else 0;best_hit=max(best_hit,cur)
  if exacts:add('sniper','Снайпер','🎯',exacts,3 if exacts>=10 else 2 if exacts>=5 else 1)
  if exact_streak>=2:add('exact_streak','Серия точных','🔥',exact_streak,3 if exact_streak>=4 else 2 if exact_streak>=3 else 1)
  if best_hit>=3:add('hit_streak','На серии','⚡',best_hit,3 if best_hit>=10 else 2 if best_hit>=6 else 1)
  if oracle_wins:add('oracle_hunter','Охотник на Оракула','✦',oracle_wins,3 if oracle_wins>=10 else 2 if oracle_wins>=5 else 1)
  if unique_exacts:add('only_one','Один такой','💎',unique_exacts,3 if unique_exacts>=5 else 2 if unique_exacts>=3 else 1)
  rows.append({'user_id':u.id,'display_name':u.display_name,'avatar_url':u.avatar_url,'is_me':u.id==user.id,'exacts':exacts,'outcomes':outcomes,'predictions':len(points),'best_exact_streak':exact_streak,'best_hit_streak':best_hit,'oracle_wins':oracle_wins,'unique_exacts':unique_exacts,'achievements':badges,'round_awards':[]})
 by_user={r['user_id']:r for r in rows};round_awards=[]
 for round_name,all_round_matches in rounds_all.items():
  if not all_round_matches or not all(_is_completed(m) for m in all_round_matches):continue
  rmatches=[m for m in all_round_matches if _is_completed(m)];scores=[]
  for _,u in members:
   eligible=[m for m in rmatches if m.kickoff_at>=u.registered_at];vals=[]
   for m in eligible:
    p=preds.get((u.id,m.id));pts=prediction_points(p,m) if p else None
    if pts is not None:vals.append(pts)
   if vals:scores.append({'user_id':u.id,'display_name':u.display_name,'points':sum(vals),'exacts':sum(x==3 for x in vals),'hits':sum(x>0 for x in vals),'predictions':len(vals),'eligible':len(eligible)})
  if not scores:continue
  best=max(x['points'] for x in scores);winners=[x for x in scores if x['points']==best];awards=[]
  for x in winners:
   awards.append({'code':'round_winner','title':'Лучший прогнозист тура','icon':'🏆','user_id':x['user_id'],'display_name':x['display_name'],'value':x['points']});by_user[x['user_id']]['round_awards'].append({'code':'round_winner','title':'Лучший прогнозист тура','icon':'🏆','round':round_name,'value':x['points']})
  for x in scores:
   if x['eligible']>0 and x['predictions']==x['eligible'] and x['exacts']==x['eligible']:
    awards.append({'code':'perfect_round','title':'Идеальный тур','icon':'👑','user_id':x['user_id'],'display_name':x['display_name'],'value':x['exacts']});by_user[x['user_id']]['round_awards'].append({'code':'perfect_round','title':'Идеальный тур','icon':'👑','round':round_name,'value':x['exacts']})
  round_awards.append({'round':round_name,'complete':True,'match_count':len(rmatches),'awards':awards,'ranking':sorted(scores,key=lambda x:(-x['points'],-x['exacts'],-x['hits'],x['display_name'].casefold()))})
 for r in rows:
  wins=sum(a['code']=='round_winner' for a in r['round_awards']);perfect=sum(a['code']=='perfect_round' for a in r['round_awards'])
  if wins:r['achievements'].append({'code':'round_champion','title':'Король тура','icon':'🏆','value':wins,'level':3 if wins>=5 else 2 if wins>=3 else 1,'subtitle':'побед в турах'})
  if perfect:r['achievements'].append({'code':'perfect_round','title':'Идеальный тур','icon':'👑','value':perfect,'level':3 if perfect>=3 else 2 if perfect>=2 else 1,'subtitle':'идеальных туров'})
 rows.sort(key=lambda x:(-len(x['achievements']),-x['exacts'],-x['oracle_wins'],x['display_name'].casefold()));mine=next((x for x in rows if x['is_me']),None)
 return {'league_id':league_id,'count':len(rows),'mine':mine,'round_awards':round_awards,'response':rows}
