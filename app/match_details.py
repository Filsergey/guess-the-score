from typing import Any


def _pick(obj: dict | None,*names:str):
    if not isinstance(obj,dict):return None
    for name in names:
        if name in obj:return obj[name]
    folded={str(k).casefold():v for k,v in obj.items()}
    for name in names:
        if str(name).casefold() in folded:return folded[str(name).casefold()]
    return None


def _deep_pick(obj:Any,*names:str):
    wanted={str(n).casefold() for n in names}
    if isinstance(obj,dict):
        for key,value in obj.items():
            if str(key).casefold() in wanted and value not in (None,""):
                return value
        for value in obj.values():
            found=_deep_pick(value,*names)
            if found not in (None,""):
                return found
    elif isinstance(obj,list):
        for value in obj:
            found=_deep_pick(value,*names)
            if found not in (None,""):
                return found
    return None


def _as_list(value:Any)->list:
    if isinstance(value,list):return value
    if isinstance(value,dict):
        for key in ('items','Items','data','Data','rows','Rows','players','Players','events','Events'):
            nested=value.get(key)
            if isinstance(nested,list):return nested
    return []


def _player(player:dict|None)->dict|None:
    if not isinstance(player,dict):return None
    return {'id':_pick(player,'id','Id','playerId','PlayerId','participantId','ParticipantId'),'name':_pick(player,'name','Name','playerName','PlayerName','participantName','ParticipantName')}


def _person_name(value:Any)->str|None:
    if isinstance(value,str):return value.strip() or None
    if isinstance(value,dict):
        person=_player(value);return person.get('name') if person else None
    return None


def _event(row:dict)->dict:
    player=_pick(row,'player','Player','participant','Participant')
    return {
        'id':_pick(row,'id','Id','eventId','EventId'),
        'team_id':_pick(row,'teamId','TeamId','participantTeamId','ParticipantTeamId'),
        'elapsed':_pick(row,'elapsed','Elapsed','minute','Minute','time','Time'),
        'extra':_pick(row,'extra','Extra','extraMinutes','ExtraMinutes','injuryTime','InjuryTime'),
        'type':_pick(row,'type','Type','eventType','EventType'),
        'name':_pick(row,'name','Name','eventName','EventName','typeName','TypeName'),
        'player':_player(player if isinstance(player,dict) else {'name':player} if isinstance(player,str) else None),
        'assist_player':_player(_pick(row,'assistPlayer','AssistPlayer','assist','Assist')),
    }


def _lineup_player(row:dict,team_id=None,start_default=None)->dict:
    start=_pick(row,'startXI','StartXI','starting','Starting','isStarting','IsStarting')
    if start is None:
        substitute=_pick(row,'substitute','Substitute','isSubstitute','IsSubstitute','bench','Bench')
        if substitute is not None:start=not bool(substitute)
    if start is None:start=bool(start_default)
    player=_pick(row,'player','Player')
    return {
        'team_id':_pick(row,'teamId','TeamId') or team_id,
        'player_id':_pick(row,'playerId','PlayerId') or (_pick(player,'id','Id') if isinstance(player,dict) else None),
        'name':_pick(row,'playerName','PlayerName','name','Name') or (_pick(player,'name','Name') if isinstance(player,dict) else None),
        'number':_pick(row,'number','Number','shirtNumber','ShirtNumber','jerseyNumber','JerseyNumber'),
        'position':_pick(row,'position','Position','positionName','PositionName'),
        'grid':_pick(row,'grid','Grid'),
        'start_xi':bool(start),
    }


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
    raw=_deep_pick(full,'statistics','Statistics','matchStatistics','MatchStatistics') or {}
    result={}
    if isinstance(raw,dict):
        for key,home_key,away_key in MATCH_STAT_FIELDS:
            home=_pick(raw,home_key,home_key[:1].upper()+home_key[1:]);away=_pick(raw,away_key,away_key[:1].upper()+away_key[1:])
            if home is not None or away is not None:result[key]={'home':home,'away':away}
    # Some SStats/Flashscore responses expose the same values directly on a nested game object.
    for key,home_key,away_key in MATCH_STAT_FIELDS:
        if key in result:continue
        home=_deep_pick(full,home_key,home_key[:1].upper()+home_key[1:]);away=_deep_pick(full,away_key,away_key[:1].upper()+away_key[1:])
        if home is not None or away is not None:result[key]={'home':home,'away':away}
    return result


def _live_snapshot(full:dict)->dict:
    game=_deep_pick(full,'game','Game','match','Match');game=game if isinstance(game,dict) else full
    return {'status':_pick(game,'status','Status'),'status_name':_pick(game,'statusName','StatusName','statusText','StatusText'),'elapsed':_pick(game,'elapsed','Elapsed','minute','Minute'),'extra_minutes':_pick(game,'extraMinutes','ExtraMinutes','extra','Extra'),'home_goals':_pick(game,'scoreHome','ScoreHome','homeResult','HomeResult'),'away_goals':_pick(game,'scoreAway','ScoreAway','awayResult','AwayResult')}


def _collect_lineup_players(full:dict,home_team_id,away_team_id)->list[dict]:
    direct=_deep_pick(full,'lineupPlayers','LineupPlayers')
    rows=[_lineup_player(x) for x in _as_list(direct) if isinstance(x,dict)]
    if rows:return rows
    lineup=_deep_pick(full,'lineups','Lineups','lineup','Lineup') or {}
    if not isinstance(lineup,dict):return []
    result=[]
    for side,team_id in (('home',home_team_id),('away',away_team_id)):
        container=_pick(lineup,side,side.capitalize(),side+'Team',side.capitalize()+'Team')
        if not isinstance(container,(dict,list)):continue
        starters=_deep_pick(container,'starting','Starting','startXI','StartXI','players','Players')
        bench=_deep_pick(container,'bench','Bench','substitutes','Substitutes')
        for row in _as_list(starters):
            if isinstance(row,dict):result.append(_lineup_player(row,team_id,True))
        for row in _as_list(bench):
            if isinstance(row,dict):result.append(_lineup_player(row,team_id,False))
    return result


def normalize_full_match(full:dict|None,home_team_id:int|None,away_team_id:int|None)->dict[str,Any]:
    full=full if isinstance(full,dict) else {}
    lineup=_deep_pick(full,'lineups','Lineups','lineup','Lineup') or {}
    event_rows=_deep_pick(full,'events','Events','incidents','Incidents','timeline','Timeline') or []
    events=[_event(x) for x in _as_list(event_rows) if isinstance(x,dict)]
    def _event_order(x):
        try:m=int(str(x.get('elapsed') or 0).split(':')[0])
        except (TypeError,ValueError):m=0
        try:e=int(x.get('extra') or 0)
        except (TypeError,ValueError):e=0
        try:i=int(x.get('id') or 0)
        except (TypeError,ValueError):i=0
        return m,e,i
    events.sort(key=_event_order)
    players=_collect_lineup_players(full,home_team_id,away_team_id)
    stat_rows=_deep_pick(full,'playerStats','PlayerStats','playerStatistics','PlayerStatistics') or []
    stats=[_player_stat(x) for x in _as_list(stat_rows) if isinstance(x,dict)]
    stats_by_id={str(x['player_id']):x for x in stats if x.get('player_id') is not None}
    def side(team_id:int|None,formation:Any,coach:Any):
        side_players=[x for x in players if str(x.get('team_id'))==str(team_id)]
        for p in side_players:p['stats']=stats_by_id.get(str(p.get('player_id')))
        return {'formation':formation,'coach':_person_name(coach),'starting':[x for x in side_players if x['start_xi']],'bench':[x for x in side_players if not x['start_xi']]}
    venue=_deep_pick(full,'venue','Venue','stadium','Stadium') or {}
    home_formation=_deep_pick(lineup,'homeFormation','HomeFormation') if isinstance(lineup,dict) else None
    away_formation=_deep_pick(lineup,'awayFormation','AwayFormation') if isinstance(lineup,dict) else None
    home_coach=_deep_pick(lineup,'homeCoach','HomeCoach') if isinstance(lineup,dict) else None
    away_coach=_deep_pick(lineup,'awayCoach','AwayCoach') if isinstance(lineup,dict) else None
    return {
        'live_raw':_live_snapshot(full),
        'statistics':_match_statistics(full),
        'referee':_deep_pick(full,'refereeName','RefereeName','referee','Referee'),
        'venue_full':{'id':_pick(venue,'id','Id'),'name':_pick(venue,'name','Name'),'city':_pick(venue,'city','City'),'address':_pick(venue,'address','Address')} if isinstance(venue,dict) and venue else None,
        'events':events,
        'player_stats':stats,
        'lineups':{'home':side(home_team_id,home_formation,home_coach),'away':side(away_team_id,away_formation,away_coach)},
    }
