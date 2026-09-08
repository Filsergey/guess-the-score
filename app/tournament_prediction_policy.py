from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select

import app.tournament_predictions as tp
from app.competitions.champions_league import classify_ucl_round
from app.models import LeagueMember, Match, Player, Tournament, TournamentPrediction, User, UserLeague

_INSTALLED = False
_ORIGINAL_DEADLINE = tp._deadline


async def _round_of_16_deadline(db, provider: str, season: int, tournament_id: int | None = None):
    if not await tp._is_ucl_scope(db, provider, season, tournament_id):
        return await _ORIGINAL_DEADLINE(db, provider, season, tournament_id)

    stmt = select(Match).where(Match.provider == provider, Match.season == season)
    if tournament_id is not None:
        stmt = stmt.where(Match.tournament_id == tournament_id)
    matches = (await db.execute(stmt.order_by(Match.kickoff_at))).scalars().all()

    round_of_16 = []
    for match in matches:
        classified = classify_ucl_round(season, match.kickoff_at) or {}
        if classified.get("stage") == "round_of_16":
            round_of_16.append(match.kickoff_at)
    if round_of_16:
        return min(round_of_16)

    # The Round of 16 starts on 9 March 2027. If SStats does not yet expose the
    # placeholder fixtures, keep the entry window open until the usual earliest
    # UCL kickoff on that date. Real fixture times automatically replace this.
    if season == 2026:
        return datetime(2027, 3, 9, 17, 45, tzinfo=timezone.utc)

    return await _ORIGINAL_DEADLINE(db, provider, season, tournament_id)


async def _out_first_save_only(db, prediction, deadline, tournament_id=None):
    now = datetime.now(timezone.utc)
    closed = now >= deadline
    saved = prediction is not None
    result = {
        "provider": prediction.provider if prediction else None,
        "season": prediction.season if prediction else None,
        "tournament_id": prediction.tournament_id if prediction else tournament_id,
        "deadline_at": deadline,
        "started": closed,
        "locked": closed or saved,
        "can_save": not closed and not saved,
        "first_save_only": True,
        "reveal_after_save": True,
        "prediction": None,
    }
    if not prediction:
        return result

    ids = [
        value
        for value in (
            prediction.top_scorer_player_id,
            prediction.top_assistant_player_id,
            prediction.best_player_player_id,
        )
        if value
    ]
    players = (
        (await db.execute(select(Player).where(Player.id.in_(ids)))).scalars().all()
        if ids
        else []
    )
    result["prediction"] = tp._prediction_out(prediction, {player.id: player for player in players})
    return result


async def _scope_prediction(db, user_id: int, provider: str, season: int, tournament_id: int | None):
    stmt = select(TournamentPrediction).where(
        TournamentPrediction.user_id == user_id,
        TournamentPrediction.provider == provider,
        TournamentPrediction.season == season,
    )
    if tournament_id is not None:
        stmt = stmt.where(TournamentPrediction.tournament_id == tournament_id)
    else:
        stmt = stmt.where(TournamentPrediction.tournament_id.is_(None))
    return await db.scalar(stmt)


async def league_predictions_after_save(league_id: int, user: User, db):
    league = await db.get(UserLeague, league_id)
    if league is None:
        raise HTTPException(404, "Лига не найдена")

    membership = await db.scalar(
        select(LeagueMember.id).where(
            LeagueMember.league_id == league_id,
            LeagueMember.user_id == user.id,
        )
    )
    if membership is None and user.role != "superadmin":
        raise HTTPException(403, "Нет доступа к этой лиге")

    provider = league.tournament_provider
    season = league.tournament_season
    tournament_id = league.tournament_id
    deadline = await _round_of_16_deadline(db, provider, season, tournament_id)
    closed = datetime.now(timezone.utc) >= deadline
    mine = await _scope_prediction(db, user.id, provider, season, tournament_id)
    viewer_saved = mine is not None
    revealed = closed or viewer_saved

    base = {
        "league_id": league.id,
        "league_name": league.name,
        "provider": provider,
        "season": season,
        "tournament_id": tournament_id,
        "deadline_at": deadline,
        "started": closed,
        "revealed": revealed,
        "viewer_has_prediction": viewer_saved,
        "first_save_only": True,
        "reveal_after_save": True,
    }
    if not revealed:
        return {**base, "count": 0, "response": []}

    members = (
        await db.execute(
            select(LeagueMember, User)
            .join(User, User.id == LeagueMember.user_id)
            .where(LeagueMember.league_id == league_id)
            .order_by(LeagueMember.joined_at)
        )
    ).all()
    user_ids = [member_user.id for _, member_user in members]

    stmt = select(TournamentPrediction).where(
        TournamentPrediction.user_id.in_(user_ids),
        TournamentPrediction.provider == provider,
        TournamentPrediction.season == season,
    )
    if tournament_id is not None:
        stmt = stmt.where(TournamentPrediction.tournament_id == tournament_id)
    else:
        stmt = stmt.where(TournamentPrediction.tournament_id.is_(None))

    predictions = (await db.execute(stmt)).scalars().all() if user_ids else []
    by_user = {prediction.user_id: prediction for prediction in predictions}
    player_ids = {
        player_id
        for prediction in predictions
        for player_id in (
            prediction.top_scorer_player_id,
            prediction.top_assistant_player_id,
            prediction.best_player_player_id,
        )
        if player_id
    }
    players = (
        (await db.execute(select(Player).where(Player.id.in_(player_ids)))).scalars().all()
        if player_ids
        else []
    )
    by_player = {player.id: player for player in players}

    items = []
    for member, member_user in members:
        prediction = by_user.get(member_user.id)
        items.append(
            {
                "user_id": member_user.id,
                "display_name": member_user.display_name,
                "username": member_user.username,
                "avatar_url": member_user.avatar_url,
                "role": member.role,
                "is_me": member_user.id == user.id,
                "has_prediction": prediction is not None,
                "prediction": tp._prediction_out(prediction, by_player) if prediction else None,
            }
        )
    return {**base, "count": len(items), "response": items}


async def save_once(body, provider: str, season: int, tournament_id: int | None, user: User, db):
    if tournament_id is not None:
        tournament = await db.get(Tournament, tournament_id)
        if not tournament or tournament.provider != provider:
            raise HTTPException(422, "Invalid tournament")

    deadline = await _round_of_16_deadline(db, provider, season, tournament_id)
    now = datetime.now(timezone.utc)
    if now >= deadline:
        raise HTTPException(409, "Приём турнирных прогнозов завершён перед 1/8 финала.")

    existing = await _scope_prediction(db, user.id, provider, season, tournament_id)
    if existing is not None:
        raise HTTPException(409, "Прогноз уже сохранён. После сохранения изменить его нельзя.")

    values = {
        key: getattr(body, key).strip()
        for key in (
            "winner",
            "second_place",
            "third_place",
            "top_scorer",
            "top_assistant",
            "best_player",
        )
    }
    teams = await tp._competition_teams(db, provider, season, tournament_id)
    allowed = {item["name"].casefold(): item["name"] for item in teams}
    for key in ("winner", "second_place", "third_place"):
        canonical = allowed.get(values[key].casefold())
        if canonical is None:
            raise HTTPException(422, f"{values[key]} is not a team in this tournament")
        values[key] = canonical
    if len({values["winner"].casefold(), values["second_place"].casefold(), values["third_place"].casefold()}) < 3:
        raise HTTPException(422, "Winner, second and third place must be different teams")

    scorer = await tp._canonical_player(db, body.top_scorer_player_id, body.top_scorer, provider, season, tournament_id)
    assistant = await tp._canonical_player(db, body.top_assistant_player_id, body.top_assistant, provider, season, tournament_id)
    best = await tp._canonical_player(db, body.best_player_player_id, body.best_player, provider, season, tournament_id)
    values["top_scorer"] = scorer.name
    values["top_assistant"] = assistant.name
    values["best_player"] = best.name

    prediction = TournamentPrediction(
        user_id=user.id,
        provider=provider,
        season=season,
        tournament_id=tournament_id,
        deadline_at=deadline,
        **values,
        top_scorer_player_id=scorer.id,
        top_assistant_player_id=assistant.id,
        best_player_player_id=best.id,
    )
    db.add(prediction)
    await db.commit()
    await db.refresh(prediction)
    return await _out_first_save_only(db, prediction, deadline, tournament_id)


def install_tournament_prediction_policy() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    tp._deadline = _round_of_16_deadline
    tp._out = _out_first_save_only

    for route in tp.router.routes:
        path = getattr(route, "path", "")
        methods = set(getattr(route, "methods", set()) or set())
        if path.endswith("/league/{league_id}") and "GET" in methods:
            route.endpoint = league_predictions_after_save
            route.dependant.call = league_predictions_after_save
        elif path.endswith("/mine") and "PUT" in methods:
            route.endpoint = save_once
            route.dependant.call = save_once
