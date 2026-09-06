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


def _walk_dicts(obj:Any):
    if isinstance(obj,dict):
        yield obj
        for value in obj.values():
            yield from _walk_dicts(value)
    elif isinstance(obj,list):
        for value in obj:
            yield from _walk_dicts(value)


def _as_list(value:Any)->list:
    if isinstance(value,list):return value
    if isinstance(value,dict):
        for key in ('items','Items','data','Data','rows','Rows','players','Players','events','Events','incidents','Incidents','statistics','Statistics','stats','Stats','groups','Groups','statisticsItems','StatisticsItems'):
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
    event_name=_pick(row,'name','Name','eventName','EventName','typeName','TypeName','incidentType','IncidentType','incidentClass','IncidentClass')
    return {
        'id':_pick(row,'id','Id','eventId','EventId','incidentId','IncidentId'),
        'team_id':_pick(row,'teamId','TeamId','participantTeamId','ParticipantTeamId'),
        'elapsed':_pick(row,'elapsed','Elapsed','minute','Minute','time','Time','incidentTime','IncidentTime'),
        'extra':_pick(row,'extra','Extra','extraMinutes','ExtraMinutes','injuryTime','InjuryTime'),
        'type':_pick(row,'type','Type','eventType','EventType','incidentType','IncidentType'),
        'name':event_name,
        'player':_player(player if isinstance(player,dict) else {'name':player} if isinstance(player,str) else {'name':_pick(row,'playerName','PlayerName')} if _pick(row,'playerName','PlayerName') else None),
        'assist_player':_player(_pick(row,'assistPlayer','AssistPlayer','assist','Assist')),
    }


def _lineup_player(row:dict,team_id=None,start_default=None)->dict:
    start=_pick(row,'startXI','StartXI','starting','Starting','isStarting','IsStarting','firstTeam','FirstTeam')
    if start is None:
        substitute=_pick(row,'substitute','Substitute','isSubstitute','IsSubstitute','bench','Bench')
        if substitute is not None:start=not bool(substitute)
    if start is None:start=bool(start_default)
    player=_pick(row,'player','Player','participant','Participant')
    return {
        'team_id':_pick(row,'teamId','TeamId','team','Team') if not isinstance(_pick(row,'team','Team'),dict) else (_pick(_pick(row,'team','Team'),'id','Id') or team_id),
        'player_id':_pick(row,'playerId','PlayerId','participantId','ParticipantId') or (_pick(player,'id','Id') if isinstance(player,dict) else None),
        'name':_pick(row,'playerName','PlayerName','name','Name','participantName','ParticipantName') or (_pick(player,'name','Name') if isinstance(player,dict) else None),
        'number':_pick(row,'number','Number','shirtNumber','ShirtNumber','jerseyNumber','JerseyNumber'),
        'position':_pick(row,'position','Position','positionName','PositionName','role','Role'),
        'grid':_pick(row,'grid','Grid'),
        'start_xi':bool(start),
    }


def _stat_value(row:dict,*names:str):
    value=_pick(row,*names)
    if isinstance(value,dict):return _pick(value,'total','Total','value','Value','displayValue','DisplayValue')
    return value


def _player_stat(row:dict)->dict:
    player=_player(_pick(row,'player','Player')) or {};v=lambda *n:_stat_value(row,*n)
    shots_on=v('shotsOn','ShotsOn','shotsOnGoal','ShotsOnGoal');pass_accuracy=v('passesAccuracy','PassesAccuracy','passesAccurate','PassesAccurate');interceptions=v('tacklesInterceptions','TacklesInterceptions','interceptions','Interceptions');saves=v('goalsSaves','GoalsSaves','saves','Saves','goalkeeperSaves','GoalkeeperSaves');yellow=v('cardsYellow','CardsYellow','yellowCards','YellowCards');red=v('cardsRed','CardsRed','redCards','RedCards')
    return {'player_id':_pick(row,'playerId','PlayerId') or player.get('id'),'player_name':_pick(row,'playerName','PlayerName') or player.get('name'),'team_id':_pick(row,'teamId','TeamId'),'minutes':v('minutes','Minutes'),'captain':v('capitan','Capitan','captain','Captain'),'substitute':v('substitute','Substitute'),'rating':v('rating','Rating'),'goals':v('goalsTotal','GoalsTotal','goals','Goals'),'goals_conceded':v('goalsConceded','GoalsConceded'),'assists':v('goalsAssists','GoalsAssists','assists','Assists'),'saves':saves,'offsides':v('offsides','Offsides'),'shots':v('shotsTotal','ShotsTotal','shots','Shots'),'shots_on':shots_on,'shots_on_goal':shots_on,'passes':v('passesTotal','PassesTotal','passes','Passes'),'key_passes':v('passesKey','PassesKey'),'pass_accuracy':pass_accuracy,'passes_accurate':pass_accuracy,'tackles':v('tacklesTotal','TacklesTotal','tackles','Tackles'),'blocks':v('tacklesBlocks','TacklesBlocks'),'interceptions':interceptions,'duels':v('duelsTotal','DuelsTotal'),'duels_won':v('duelsWon','DuelsWon'),'dribbles':v('dribblesAttempts','DribblesAttempts'),'dribbles_success':v('dribblesSuccess','DribblesSuccess'),'dribbles_past':v('dribblesPast','DribblesPast'),'fouls_drawn':v('foulsDrawn','FoulsDrawn'),'fouls_committed':v('foulsCommitted','FoulsCommitted'),'yellow':yellow,'yellow_cards':yellow,'red':red,'red_cards':red,'penalty_won':v('penaltyWon','PenaltyWon'),'penalty_committed':v('penaltyCommited','PenaltyCommited','penaltyCommitted','PenaltyCommitted'),'penalty_scored':v('penaltyScored','PenaltyScored'),'penalty_missed':v('penaltyMissed','PenaltyMissed'),'penalty_saved':v('penaltySaved','PenaltySaved')}


MATCH_STAT_FIELDS=(("ShotsOnGoal","shotsOnGoalHome","shotsOnGoalAway"),("ShotsOffGoal","shotsOffGoalHome","shotsOffGoalAway"),("TotalShots","totalShotsHome","totalShotsAway"),("BlockedShots","blockedShotsHome","blockedShotsAway"),("ShotsInsideBox","shotsInsideBoxHome","shotsInsideBoxAway"),("ShotsOutsideBox","shotsOutsideBoxHome","shotsOutsideBoxAway"),("Fouls","foulsHome","foulsAway"),("CornerKicks","cornerKicksHome","cornerKicksAway"),("BallPossession","ballPossessionHome","ballPossessionAway"),("YellowCards","yellowCardsHome","yellowCardsAway"),("RedCards","redCardsHome","redCardsAway"),("GoalkeeperSaves","goalkeeperSavesHome","goalkeeperSavesAway"),("TotalPasses","totalPassesHome","totalPassesAway"),("PassesAccurate","passesAccurateHome","passesAccurateAway"),("Offsides","offsidesHome","offsidesAway"),("ExpectedGoals","expectedGoalsHome","expectedGoalsAway"),("ExpectedAssists","expectedAssistsHome","expectedAssistsAway"),("BigChances","bigChancesHome","bigChancesAway"),("XgOnTarget","xgOnTargetHome","xgOnTargetAway"),("HitTheWoodwork","hitTheWoodworkHome","hitTheWoodworkAway"),("GoalsPrevented","goalsPreventedHome","goalsPreventedAway"))

STAT_NAME_MAP={
    'shots on goal':'ShotsOnGoal','shots on target':'ShotsOnGoal','shotsongoal':'ShotsOnGoal','shotsontarget':'ShotsOnGoal','удары в створ':'ShotsOnGoal',
    'shots off goal':'ShotsOffGoal','shots off target':'ShotsOffGoal','shotsoffgoal':'ShotsOffGoal','shotsofftarget':'ShotsOffGoal','мимо':'ShotsOffGoal',
    'total shots':'TotalShots','totalshots':'TotalShots','shots total':'TotalShots','удары':'TotalShots',
    'blocked shots':'BlockedShots','blockedshots':'BlockedShots','заблокировано':'BlockedShots',
    'shots inside box':'ShotsInsideBox','shotsinsidebox':'ShotsInsideBox','shots in box':'ShotsInsideBox','из штрафной':'ShotsInsideBox',
    'shots outside box':'ShotsOutsideBox','shotsoutsidebox':'ShotsOutsideBox','shots out of box':'ShotsOutsideBox','из-за штрафной':'ShotsOutsideBox',
    'fouls':'Fouls','fouls committed':'Fouls','фолы':'Fouls',
    'corner kicks':'CornerKicks','corners':'CornerKicks','cornerkicks':'CornerKicks','угловые':'CornerKicks',
    'ball possession':'BallPossession','possession':'BallPossession','ballpossession':'BallPossession','владение':'BallPossession',
    'yellow cards':'YellowCards','yellowcards':'YellowCards','жёлтые карточки':'YellowCards','желтые карточки':'YellowCards',
    'red cards':'RedCards','redcards':'RedCards','красные карточки':'RedCards',
    'goalkeeper saves':'GoalkeeperSaves','saves':'GoalkeeperSaves','goalkeepersaves':'GoalkeeperSaves','сейвы':'GoalkeeperSaves',
    'total passes':'TotalPasses','passes':'TotalPasses','totalpasses':'TotalPasses','пасы':'TotalPasses',
    'accurate passes':'PassesAccurate','passes accurate':'PassesAccurate','passesaccurate':'PassesAccurate','точные пасы':'PassesAccurate',
    'offsides':'Offsides','офсайды':'Offsides',
    'expected goals':'ExpectedGoals','expected goals (xg)':'ExpectedGoals','xg':'ExpectedGoals','expectedgoals':'ExpectedGoals',
    'expected assists':'ExpectedAssists','xa':'ExpectedAssists','expectedassists':'ExpectedAssists',
    'big chances':'BigChances','bigchances':'BigChances',
    'xg on target':'XgOnTarget','xgot':'XgOnTarget','xgontarget':'XgOnTarget',
    'hit the woodwork':'HitTheWoodwork','woodwork':'HitTheWoodwork','hitthewoodwork':'HitTheWoodwork',
    'goals prevented':'GoalsPrevented','goalsprevented':'GoalsPrevented',
}


def _stat_key(name:Any)->str|None:
    if name is None:return None
    text=' '.join(str(name).strip().casefold().replace('_',' ').replace('-',' ').split())
    compact=text.replace(' ','')
    return STAT_NAME_MAP.get(text) or STAT_NAME_MAP.get(compact)


def _side_value(value:Any):
    if isinstance(value,dict):return _pick(value,'value','Value','total','Total','displayValue','DisplayValue','text','Text')
    return value


def _pair_from_stat_row(row:dict):
    name=_pick(row,'name','Name','title','Title','label','Label','statName','StatName','key','Key')
    key=_stat_key(name)
    if not key:return None
    home=_pick(row,'home','Home','homeValue','HomeValue','valueHome','ValueHome','homeStat','HomeStat','homeTeam','HomeTeam')
    away=_pick(row,'away','Away','awayValue','AwayValue','valueAway','ValueAway','awayStat','AwayStat','awayTeam','AwayTeam')
    values=_pick(row,'values','Values')
    if (home is None or away is None) and isinstance(values,list) and len(values)>=2:
        home=values[0] if home is None else home;away=values[1] if away is None else away
    home=_side_value(home);away=_side_value(away)
    if home is None and away is None:return None
    return key,{'home':home,'away':away}


def _match_statistics(full:dict)->dict:
    raw=_deep_pick(full,'statistics','Statistics','matchStatistics','MatchStatistics','stats','Stats') or {}
    result={}
    if isinstance(raw,dict):
        for key,home_key,away_key in MATCH_STAT_FIELDS:
            home=_pick(raw,home_key,home_key[:1].upper()+home_key[1:]);away=_pick(raw,away_key,away_key[:1].upper()+away_key[1:])
            if home is not None or away is not None:result[key]={'home':home,'away':away}
        for raw_name,value in raw.items():
            mapped=_stat_key(raw_name)
            if not mapped or mapped in result:continue
            if isinstance(value,dict):
                home=_side_value(_pick(value,'home','Home','homeValue','HomeValue'));away=_side_value(_pick(value,'away','Away','awayValue','AwayValue'))
                if home is not None or away is not None:result[mapped]={'home':home,'away':away}
    for key,home_key,away_key in MATCH_STAT_FIELDS:
        if key in result:continue
        home=_deep_pick(full,home_key,home_key[:1].upper()+home_key[1:]);away=_deep_pick(full,away_key,away_key[:1].upper()+away_key[1:])
        if home is not None or away is not None:result[key]={'home':home,'away':away}
    # Flashscore GameInfo frequently represents statistics as nested groups/items.
    for row in _walk_dicts(raw if raw else full):
        pair=_pair_from_stat_row(row)
        if pair and pair[0] not in result:result[pair[0]]=pair[1]
    return result


def _live_snapshot(full:dict)->dict:
    game=_deep_pick(full,'game','Game','match','Match');game=game if isinstance(game,dict) else full
    return {'status':_pick(game,'status','Status'),'status_name':_pick(game,'statusName','StatusName','statusText','StatusText'),'elapsed':_pick(game,'elapsed','Elapsed','minute','Minute'),'extra_minutes':_pick(game,'extraMinutes','ExtraMinutes','extra','Extra'),'home_goals':_pick(game,'scoreHome','ScoreHome','homeResult','HomeResult'),'away_goals':_pick(game,'scoreAway','ScoreAway','awayResult','AwayResult')}


def _collect_lineup_players(full:dict,home_team_id,away_team_id)->list[dict]:
    direct=_deep_pick(full,'lineupPlayers','LineupPlayers')
    rows=[_lineup_player(x) for x in _as_list(direct) if isinstance(x,dict)]
    if rows:return rows
    lineup=_deep_pick(full,'lineups','Lineups','lineup','Lineup','formations','Formations') or {}
    if not isinstance(lineup,dict):return []
    result=[]
    for side,team_id in (('home',home_team_id),('away',away_team_id)):
        container=_pick(lineup,side,side.capitalize(),side+'Team',side.capitalize()+'Team')
        if isinstance(container,list):
            for row in container:
                if isinstance(row,dict):result.append(_lineup_player(row,team_id,None))
            continue
        if not isinstance(container,dict):continue
        starters=_deep_pick(container,'starting','Starting','startXI','StartXI','starters','Starters')
        bench=_deep_pick(container,'bench','Bench','substitutes','Substitutes')
        all_players=_deep_pick(container,'players','Players')
        if not _as_list(starters) and not _as_list(bench) and _as_list(all_players):
            for row in _as_list(all_players):
                if isinstance(row,dict):result.append(_lineup_player(row,team_id,None))
            continue
        for row in _as_list(starters):
            if isinstance(row,dict):result.append(_lineup_player(row,team_id,True))
        for row in _as_list(bench):
            if isinstance(row,dict):result.append(_lineup_player(row,team_id,False))
    return result


def normalize_full_match(full:dict|None,home_team_id:int|None,away_team_id:int|None)->dict[str,Any]:
    full=full if isinstance(full,dict) else {}
    lineup=_deep_pick(full,'lineups','Lineups','lineup','Lineup','formations','Formations') or {}
    event_rows=_deep_pick(full,'events','Events','incidents','Incidents','timeline','Timeline','matchEvents','MatchEvents') or []
    events=[_event(x) for x in _as_list(event_rows) if isinstance(x,dict)]
    if not events:
        candidates=[]
        for row in _walk_dicts(full):
            if _pick(row,'incidentType','IncidentType','eventType','EventType') is not None and _pick(row,'minute','Minute','elapsed','Elapsed','time','Time') is not None:candidates.append(row)
        events=[_event(x) for x in candidates]
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
    venue_name=_deep_pick(full,'venueName','VenueName','stadiumName','StadiumName')
    home_formation=_deep_pick(lineup,'homeFormation','HomeFormation') if isinstance(lineup,dict) else None
    away_formation=_deep_pick(lineup,'awayFormation','AwayFormation') if isinstance(lineup,dict) else None
    home_coach=_deep_pick(lineup,'homeCoach','HomeCoach') if isinstance(lineup,dict) else _deep_pick(full,'homeCoach','HomeCoach','homeTeamCoachName','HomeTeamCoachName')
    away_coach=_deep_pick(lineup,'awayCoach','AwayCoach') if isinstance(lineup,dict) else _deep_pick(full,'awayCoach','AwayCoach','awayTeamCoachName','AwayTeamCoachName')
    if isinstance(venue,str):venue={'name':venue}
    if not venue and venue_name:venue={'name':venue_name}
    return {
        'live_raw':_live_snapshot(full),
        'statistics':_match_statistics(full),
        'referee':_deep_pick(full,'refereeName','RefereeName','referee','Referee'),
        'venue_full':{'id':_pick(venue,'id','Id'),'name':_pick(venue,'name','Name') or venue_name,'city':_pick(venue,'city','City'),'address':_pick(venue,'address','Address')} if isinstance(venue,dict) and venue else None,
        'events':events,
        'player_stats':stats,
        'lineups':{'home':side(home_team_id,home_formation,home_coach),'away':side(away_team_id,away_formation,away_coach)},
    }
