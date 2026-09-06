import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.leagues import _membership, _oracle_score, _score_points, serialize_league
from app.match_status import FINAL_MATCH_STATUSES, LIVE_MATCH_STATUSES
from app.models import LeagueMember, Match, OraclePrediction, Prediction, User, UserLeague
from app.predictions import prediction_points

router = APIRouter(prefix="/api/leagues", tags=["leagues-live"])


def _oracle_live_score(op: OraclePrediction | None, match: Match):
    if op is None or op.generated_at is None or op.generated_at >= match.kickoff_at:
        return None
    if match.home_goals is None or match.away_goals is None:
        return None
    try:
        data = json.loads(op.payload_json)
        ph = int(data["home_score"])
        pa = int(data["away_score"])
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None
    return ph, pa, _score_points(ph, pa, match.home_goals, match.away_goals)


@router.get('/{league_id}/live-standings')
async def live_standings(league_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = await _membership(league_id, user, db)
    league = await db.get(UserLeague, league_id)
    if league is None:
        raise HTTPException(404, 'League not found')

    final_matches = (await db.execute(select(Match).where(
        Match.provider == league.tournament_provider,
        Match.season == league.tournament_season,
        Match.status_short.in_(tuple(FINAL_MATCH_STATUSES)),
        Match.home_goals.is_not(None), Match.away_goals.is_not(None),
    ))).scalars().all()
    live_matches = (await db.execute(select(Match).where(
        Match.provider == league.tournament_provider,
        Match.season == league.tournament_season,
        Match.status_short.in_(tuple(LIVE_MATCH_STATUSES)),
        Match.home_goals.is_not(None), Match.away_goals.is_not(None),
    ).order_by(Match.kickoff_at))).scalars().all()

    members = (await db.execute(select(LeagueMember, User).join(User, User.id == LeagueMember.user_id).where(LeagueMember.league_id == league_id))).all()
    all_ids = [m.id for m in final_matches + live_matches]
    member_ids = [u.id for _, u in members]
    predictions = (await db.execute(select(Prediction).where(Prediction.user_id.in_(member_ids), Prediction.match_id.in_(all_ids)))).scalars().all() if member_ids and all_ids else []
    pred_map = {(p.user_id, p.match_id): p for p in predictions}

    rows = []
    for member, u in members:
        base_points = base_exacts = base_outcomes = 0
        for m in final_matches:
            if m.kickoff_at < u.registered_at:
                continue
            p = pred_map.get((u.id, m.id))
            pts = prediction_points(p, m) if p else None
            if pts is None:
                continue
            base_points += pts
            if pts == 3: base_exacts += 1
            elif pts == 1: base_outcomes += 1

        live_points = live_exacts = live_outcomes = 0
        live_breakdown = []
        for m in live_matches:
            if m.kickoff_at < u.registered_at:
                continue
            p = pred_map.get((u.id, m.id))
            pts = _score_points(p.home_score, p.away_score, m.home_goals, m.away_goals) if p else 0
            live_points += pts
            if pts == 3: live_exacts += 1
            elif pts == 1: live_outcomes += 1
            live_breakdown.append({'match_id': m.id, 'points': pts, 'has_prediction': p is not None})

        rows.append({'user_id': u.id, 'display_name': u.display_name, 'username': u.username, 'avatar_url': u.avatar_url, 'member_role': member.role, 'is_oracle': False, 'base_points': base_points, 'base_exacts': base_exacts, 'base_outcomes': base_outcomes, 'live_points': live_points, 'live_exacts': live_exacts, 'live_outcomes': live_outcomes, 'projected_points': base_points + live_points, 'live_breakdown': live_breakdown})

    if league.include_oracle:
        ids = [m.id for m in final_matches + live_matches]
        ops = (await db.execute(select(OraclePrediction).where(OraclePrediction.match_id.in_(ids)))).scalars().all() if ids else []
        op_map = {x.match_id: x for x in ops}
        base_points = base_exacts = base_outcomes = 0
        for m in final_matches:
            score = _oracle_score(op_map.get(m.id), m)
            if score is None: continue
            _, _, pts = score; base_points += pts
            if pts == 3: base_exacts += 1
            elif pts == 1: base_outcomes += 1
        live_points = live_exacts = live_outcomes = 0; live_breakdown = []
        for m in live_matches:
            score = _oracle_live_score(op_map.get(m.id), m)
            pts = score[2] if score is not None else 0
            live_points += pts
            if pts == 3: live_exacts += 1
            elif pts == 1: live_outcomes += 1
            live_breakdown.append({'match_id': m.id, 'points': pts, 'has_prediction': score is not None})
        rows.append({'user_id': None, 'display_name': 'Оракул', 'username': None, 'avatar_url': None, 'member_role': 'oracle', 'is_oracle': True, 'base_points': base_points, 'base_exacts': base_exacts, 'base_outcomes': base_outcomes, 'live_points': live_points, 'live_exacts': live_exacts, 'live_outcomes': live_outcomes, 'projected_points': base_points + live_points, 'live_breakdown': live_breakdown})

    base_sorted = sorted(rows, key=lambda x: (-x['base_points'], -x['base_exacts'], -x['base_outcomes'], x['display_name'].lower()))
    for i, row in enumerate(base_sorted, 1): row['base_place'] = i
    projected = sorted(rows, key=lambda x: (-x['projected_points'], -(x['base_exacts'] + x['live_exacts']), -(x['base_outcomes'] + x['live_outcomes']), x['display_name'].lower()))
    for i, row in enumerate(projected, 1): row['projected_place'] = i

    live_payload = [{'match_id': m.id, 'home_goals': m.home_goals, 'away_goals': m.away_goals, 'elapsed': m.elapsed, 'status': m.status_short} for m in live_matches]
    return {'league': serialize_league(league, membership.role if membership else 'superadmin', len(members)), 'live': bool(live_matches), 'live_matches': live_payload, 'count': len(projected), 'response': projected}
