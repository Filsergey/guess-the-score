import asyncio


async def generate_due_oracle_predictions() -> dict:
    """Oracle no longer contacts OpenAI from a scheduler.

    Initial forecasts are created by league/match creation events. Delta refreshes
    are user-driven when somebody opens "Прогноз ИИ".
    """
    return {"generated": 0, "reason": "oracle-openai-scheduler-disabled"}


async def oracle_scheduler_loop() -> None:
    """Compatibility no-op for older deployments that still enable this task."""
    while True:
        await asyncio.sleep(3600)
