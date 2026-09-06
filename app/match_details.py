from typing import Any

def _pick(obj: dict | None,*names:str):
    if not isinstance(obj,dict):return None
    for name in names:
        if name in obj:return obj[name]
    return None

def _player(player:dict|None)->dict|None:
    if not isinstance(player,dict):return None
    return {'id':_pick(player,'id','Id','playerId','PlayerId'),'name':_pick(player,'name','Name','playerName','PlayerName')}
def _person_name(value:Any)->str|None:
    if isinstance(value,str):return value.strip() or None
    if isinstance(value,dict):
        person=_player(value);return person.get('name') if person else None
    return None
def _event(row:dict)->dict:return {'id':_pick(row,'id','Id'),'team_id':_pick(row,'teamId','TeamId'),'elapsed':_pick(row,'elapsed','Elapsed'),'extra':_pick(row,'extra','Extra','extraMinutes','ExtraMinutes'),'type':_pick(row,'type','Type'),'name':_pick(row,'name','Name'),'player':_player(_pick(row,'player','Player')),'assist_player':_player(_pick(row,'assistPlayer','AssistPlayer'))}
def _lineup_player(row:dict)->dict:return {'team_id':_pick(row,'teamId','TeamId'),'player_id':_pick(row,'playerId','PlayerId'),'name':_pick(row,'playerName','PlayerName'),'number':_pick(row,'number','Number'),'position':_pick(row,'position','Position'),'grid':_pick(row,'grid','Grid'),'start_xi':bool(_pick(row,'startXI','StartXI'))}
def _stat_value(row:dict,*names:str):
    value=_pick(row,*names)
    if isinstance(value,dict):return _pick(value,'total','Total','value','Value')
    return value
def _player_stat(row:dict)->dict:
    player=_player(_pick(row,'player','Player')) or {};v=lambda *n:_stat_value(row,*n)
    shots_on=v('shotsOn','ShotsOn','shotsOnGoal','ShotsOnGoal');pass_accuracy=v('passesAccuracy','PassesAccuracy','passesAccurate','PassesAccurate');interceptions=v('tacklesInterceptions','TacklesInterceptions','interceptions','Interceptions');saves=v('goalsSaves','GoalsSaves','saves','Saves','goalkeeperSaves','GoalkeeperSaves');yellow=v('cardsYellow','CardsYellow','yellowCards','YellowCards');red=v('cardsRed','CardsRed','redCards','RedCards')
    return {'player_id':_pick(row,'playerId','PlayerId') or player.get('id'),'player_name':_pick(row,'playerName','PlayerName') or player.get('name'),'team_id':_pick(row,'teamId','TeamId'),'minutes':v('minutes','Minutes'),'captain':v('capitan','Capitan','captain','Captain'),'substitute':v('substitute','Substitute'),'rating':v('rating','Rating'),'goals':v('goalsTotal','GoalsTotal','goals','Goals'),'goals_conceded':v('goalsConceded','GoalsConceded'),'assists':v('goalsAssists','GoalsAssists','assists','Assists'),'saves':saves,'offsides':v('offsides','Offsides'),'shots':v('shotsTotal','ShotsTotal','shots','Shots'),'shots_on':shots_on,'shots_on_goal':shots_on,'passes':v('passesTotal','PassesTotal','passes','Passes'),'key_passes':v('passesKey','PassesKey'),'pass_accuracy':pass_accuracy,'passes_accurate':pass_accuracy,'tackles':v('tacklesTotal','TacklesTotal','tackles','Tackles'),'blocks':v('tacklesBlocks','TacklesBlocks'),'interceptions':interceptions,'duels':v('duelsTotal','DuelsTotal'),'duels_won':v('duelsWon','DuelsWon'),'dribbles':v('dribblesAttempts','DribblesAttempts'),'dribbles_success':v('dribblesSuccess','DribblesSuccess'),'dribbles_past':v('dribblesPast','DribblesPast'),'fouls_drawn':v('foulsDrawn','FoulsDrawn'),'fouls_committed':v('foulsCommitted','FoulsCommitted'),'yellow':yellow,'yellow_cards':yellow,'red':red,'red_cards':red,'penalty_won':v('penaltyWon','PenaltyWon'),'penalty_committed':v('penaltyCommited','PenaltyCommited','penaltyCommitted','PenaltyCommitted'),'penalty_scored':v('penaltyScored','PenaltyScored'),'penalty_missed':v('penaltyMissed','PenaltyMissed'),'penalty_saved':v('penaltySaved','PenaltySaved')}
MATCH_STAT_FIELDS=(("ShotsOnGoal","shotsOnGoalHome","shotsOnGoalAway"),("ShotsOffGoal","shotsOffGoalHome","shotsOffGoalAway"),("TotalShots","totalShotsHome","totalShotsAway"),("BlockedShots","blockedShotsHome","blockedShotsAway"),("ShotsInsideBox","shotsInsideBoxHome","shotsInsideBoxAway"),("ShotsOutsideBox","shotsOutsideBoxHome","shotsOutsideBoxAway"),("Fouls","foulsHome","foulsAway"),("CornerKicks","cornerKicksHome","cornerKicksAway"),("BallPossession","ballPossessionHome","ballPossessionAway"),("YellowCards","yellowCardsHome","yellowCardsAway"),("RedCards","redCardsHome","redCardsAway"),("GoalkeeperSaves","goalkeeperSavesHome","goalkeeperSavesAway"),("TotalPasses","totalPassesHome","totalPassesAway"),("PassesAccurate","passesAccurateHome","passesAccurateAway"),("Offsides","offsidesHome","offsidesAway"),("ExpectedGoals","expectedGoalsHome","expectedGoalsAway"),("ExpectedAssists","expectedAssistsHome","expectedAssistsAway"),("BigChances","bigChancesHome","bigChancesAway"),("XgOnTarget","xgOnTargetHome","xgOnTargetAway"),("HitTheWoodwork","hitTheWoodworkHome","hitTheWoodworkAway"),("GoalsPrevented","goalsPreventedHome","goalsPreventedAway"))
def _match_statistics(full:dict)->dict:
    raw=_pick(full,'statistics','Statistics') or {}
    if not isinstance(raw,dict):return {}
    result={}
    for key,home_key,away_key in MATCH_STAT_FIELDS:
        home=_pick(raw,home_key,home_key[:1].upper()+home_key[1:]);away=_pick(raw,away_key,away_key[:1].upper()+away_key[1:])
        if home is not None or away is not None:result[key]={'home':home,'away':away}
    return result
def _live_snapshot(full:dict)->dict:
    game=_pick(full,'game','Game');game=game if isinstance(game,dict) else full
    return {'status':_pick(game,'status','Status'),'status_name':_pick(game,'statusName','StatusName','statusText','StatusText'),'elapsed':_pick(game,'elapsed','Elapsed','minute','Minute'),'extra_minutes':_pick(game,'extraMinutes','ExtraMinutes','extra','Extra'),'home_goals':_pick(game,'scoreHome','ScoreHome','homeResult','HomeResult'),'away_goals':_pick(game,'scoreAway','ScoreAway','awayResult','AwayResult')}
def normalize_full_match(full:dict|None,home_team_id:int|None,away_team_id:int|None)->dict[str,Any]:
    full=full if isinstance(full,dict) else {};lineup=_pick(full,'lineups','Lineups') or {};events=[_event(x) for x in (_pick(full,'events','Events') or []) if isinstance(x,dict)];events.sort(key=lambda x:(int(x['elapsed'] or 0),int(x['extra'] or 0),int(x['id'] or 0)));players=[_lineup_player(x) for x in (_pick(full,'lineupPlayers','LineupPlayers') or []) if isinstance(x,dict)];stats=[_player_stat(x) for x in (_pick(full,'playerStats','PlayerStats') or []) if isinstance(x,dict)];stats_by_id={str(x['player_id']):x for x in stats if x.get('player_id') is not None}
    def side(team_id:int|None,formation:Any,coach:Any):
        side_players=[x for x in players if str(x.get('team_id'))==str(team_id)]
        for p in side_players:p['stats']=stats_by_id.get(str(p.get('player_id')))
        return {'formation':formation,'coach':_person_name(coach),'starting':[x for x in side_players if x['start_xi']],'bench':[x for x in side_players if not x['start_xi']]}
    venue=_pick(full,'venue','Venue') or {}
    return {'live_raw':_live_snapshot(full),'statistics':_match_statistics(full),'referee':_pick(full,'refereeName','RefereeName'),'venue_full':{'id':_pick(venue,'id','Id'),'name':_pick(venue,'name','Name'),'city':_pick(venue,'city','City'),'address':_pick(venue,'address','Address')} if venue else None,'events':events,'player_stats':stats,'lineups':{'home':side(home_team_id,_pick(lineup,'homeFormation','HomeFormation'),_pick(lineup,'homeCoach','HomeCoach')),'away':side(away_team_id,_pick(lineup,'awayFormation','AwayFormation'),_pick(lineup,'awayCoach','AwayCoach'))}}
