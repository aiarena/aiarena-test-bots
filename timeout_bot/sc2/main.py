import asyncio
import logging
import time

import async_timeout
from s2clientprotocol import sc2api_pb2 as sc_pb

from .client import Client
from .data import CreateGameError, Result
from .game_state import GameState
from .player import Bot, Human
from .portconfig import Portconfig
from .protocol import ConnectionAlreadyClosed, ProtocolError
from .sc2process import SC2Process
from .unit import UnitGameData

logger = logging.getLogger(__name__)


class SlidingTimeWindow:
    def __init__(self, size: int):
        assert size > 0

        self.window_size = size
        self.window = []

    def push(self, value: float):
        self.window = (self.window + [value])[-self.window_size:]

    def clear(self):
        self.window = []

    @property
    def sum(self) -> float:
        return sum(self.window)

    @property
    def available(self) -> float:
        return sum(self.window[1:])

    @property
    def available_fmt(self) -> float:
        return ",".join(f"{w:.2f}" for w in self.window[1:])


async def _play_game_human(client, player_id, realtime, game_time_limit):
    while True:
        state = await client.observation()
        if client._game_result:
            return client._game_result[player_id]

        if game_time_limit and (state.observation.observation.game_loop * 0.725 * (1 / 16)) > game_time_limit:
            print(state.observation.game_loop, state.observation.game_loop * 0.14)
            return Result.Tie

        if not realtime:
            await client.step()

async def _play_game_ai(client, player_id, ai, realtime, step_time_limit, game_time_limit):
    if realtime:
        assert step_time_limit is None

    # step_time_limit works like this:
    # * If None, then step time is not limited
    # * If given integer or float, the bot will simpy resign if any step takes longer than that
    # * Otherwise step_time_limit must be an object, with following settings:
    #
    # Key         | Value      | Description
    # ------------|------------|-------------
    # penalty     | None       | No penalty, the bot can continue on next step
    # penalty     | N: int     | Cooldown penalty, BotAI.on_step will not be called for N steps
    # penalty     | "resign"   | Bot resigns when going over time limit
    # time_limit  | int/float  | Time limit for a single step
    # window_size | N: int     | The time limit will be used for last N steps, instad of 1
    #
    # Cooldown is a harsh penalty. The both loses the ability to act, but even worse,
    # the observation data from skipped steps is also lost. It's like falling asleep in
    # a middle of the game.
    time_penalty_cooldown = 0
    if step_time_limit is None:
        time_limit = None
        time_window = None
        time_penalty = None
    elif isinstance(step_time_limit, (int, float)):
        time_limit = float(step_time_limit)
        time_window = SlidingTimeWindow(1)
        time_penalty = "resign"
    else:
        assert isinstance(step_time_limit, dict)
        time_penalty = step_time_limit.get("penalty", None)
        time_window = SlidingTimeWindow(int(step_time_limit.get("window_size", 1)))
        time_limit = float(step_time_limit.get("time_limit", None))


    game_data = await client.get_game_data()
    # Used in PassengerUnit, Unit and Units
    UnitGameData._game_data = game_data
    UnitGameData._bot_object = ai
    game_info = await client.get_game_info()

    # This game_data will become self._game_data in botAI
    ai._prepare_start(client, player_id, game_info, game_data)
    state = await client.observation()
    # check game result every time we get the observation
    if client._game_result:
        ai.on_end(client._game_result[player_id])
        return client._game_result[player_id]
    gs = GameState(state.observation)
    proto_game_info = await client._execute(game_info=sc_pb.RequestGameInfo())
    ai._prepare_step(gs, proto_game_info)
    ai._prepare_first_step()
    try:
        ai.on_start()
        await ai.on_start_async()
    except Exception as e:
        logger.exception(f"AI on_start threw an error")
        logger.error(f"resigning due to previous error")
        ai.on_end(Result.Defeat)
        return Result.Defeat

    iteration = 0
    while True:
        if iteration != 0:
            state = await client.observation()
            # check game result every time we get the observation
            if client._game_result:
                ai.on_end(client._game_result[player_id])
                return client._game_result[player_id]
            gs = GameState(state.observation)
            logger.debug(f"Score: {gs.score.summary}")

            if game_time_limit and (gs.game_loop * 0.725 * (1 / 16)) > game_time_limit:
                ai.on_end(Result.Tie)
                return Result.Tie
            proto_game_info = await client._execute(game_info=sc_pb.RequestGameInfo())
            ai._prepare_step(gs, proto_game_info)

        logger.debug(f"Running AI step, it={iteration} {gs.game_loop * 0.725 * (1 / 16):.2f}s")

        try:
            await ai.issue_events()
            if realtime:
                await ai.on_step(iteration)
            else:
                if time_penalty_cooldown > 0:
                    time_penalty_cooldown -= 1
                    logger.warning(f"Running AI step: penalty cooldown: {time_penalty_cooldown}")
                    iteration -= 1 # Do not increment the iteration on this round
                elif time_limit is None:
                    await ai.on_step(iteration)
                else:
                    out_of_budget = False
                    budget = time_limit - time_window.available

                    # Tell the bot how much time it has left attribute
                    ai.time_budget_available = budget

                    if budget < 0:
                        logger.warning(f"Running AI step: out of budget before step")
                        step_time = 0.0
                        out_of_budget = True
                    else:
                        step_start = time.monotonic()
                        try:
                            async with async_timeout.timeout(budget):
                                await ai.on_step(iteration)
                        except asyncio.TimeoutError:
                            step_time = time.monotonic() - step_start
                            logger.warning(
                                f"Running AI step: out of budget; " +
                                f"budget={budget:.2f}, steptime={step_time:.2f}, " +
                                f"window={time_window.available_fmt}"
                            )
                            out_of_budget = True
                        step_time = time.monotonic() - step_start

                    time_window.push(step_time)

                    if out_of_budget and time_penalty is not None:
                        if time_penalty == "resign":
                            raise RuntimeError("Out of time")
                        else:
                            time_penalty_cooldown = int(time_penalty)
                            time_window.clear()
        except Exception as e:
            if isinstance(e, ProtocolError) and e.is_game_over_error:
                if realtime:
                    return None
                result = client._game_result[player_id]
                if result is None:
                    logger.error("Game over, but no results gathered")
                    raise
                ai.on_end(result)
                return result
            # NOTE: this message is caught by pytest suite
            logger.exception(f"AI step threw an error") # DO NOT EDIT!
            logger.error(f"resigning due to previous error")
            ai.on_end(Result.Defeat)
            return Result.Defeat

        logger.debug(f"Running AI step: done")

        if not realtime:
            if not client.in_game:  # Client left (resigned) the game
                ai.on_end(client._game_result[player_id])
                return client._game_result[player_id]

            await client.step()

        iteration += 1

async def _play_game(player, client, realtime, portconfig, step_time_limit=None, game_time_limit=None, rgb_render_config=None):
    assert isinstance(realtime, bool), repr(realtime)

    player_id = await client.join_game(
        player.name, player.race, portconfig=portconfig, rgb_render_config=rgb_render_config
    )
    logging.info(f"Player {player_id} - {player.name if player.name else str(player)}")

    if isinstance(player, Human):
        result = await _play_game_human(client, player_id, realtime, game_time_limit)
    else:
        result = await _play_game_ai(client, player_id, player.ai, realtime, step_time_limit, game_time_limit)

    logging.info(f"Result for player {player_id} - {player.name if player.name else str(player)}: {result._name_}")

    return result

async def _setup_host_game(server, map_settings, players, realtime, random_seed=None):
    r = await server.create_game(map_settings, players, realtime, random_seed)
    if r.create_game.HasField("error"):
        err = f"Could not create game: {CreateGameError(r.create_game.error)}"
        if r.create_game.HasField("error_details"):
            err += f": {r.create_game.error_details}"
        logger.critical(err)
        raise RuntimeError(err)

    return Client(server._ws)


async def _host_game(map_settings, players, realtime, portconfig=None, save_replay_as=None, step_time_limit=None,
                     game_time_limit=None, rgb_render_config=None, random_seed=None):
    assert len(players) > 0, "Can't create a game without players"

    assert any(isinstance(p, (Human, Bot)) for p in players)

    async with SC2Process(fullscreen=players[0].fullscreen, render=rgb_render_config is not None) as server:
        await server.ping()

        client = await _setup_host_game(server, map_settings, players, realtime, random_seed)

        try:
            result = await _play_game(players[0], client, realtime, portconfig, step_time_limit, game_time_limit, rgb_render_config)
            if save_replay_as is not None:
                await client.save_replay(save_replay_as)
            await client.leave()
            await client.quit()
        except ConnectionAlreadyClosed:
            logging.error(f"Connection was closed before the game ended")
            return None

        return result

async def _host_game_aiter(map_settings, players, realtime, portconfig=None, save_replay_as=None, step_time_limit=None, game_time_limit=None):
    assert players, "Can't create a game without players"

    assert any(isinstance(p, (Human, Bot)) for p in players)

    async with SC2Process() as server:
        while True:
            await server.ping()

            client = await _setup_host_game(server, map_settings, players, realtime)

            try:
                result = await _play_game(players[0], client, realtime, portconfig, step_time_limit, game_time_limit)

                if save_replay_as is not None:
                    await client.save_replay(save_replay_as)
                await client.leave()
            except ConnectionAlreadyClosed:
                logging.error(f"Connection was closed before the game ended")
                return

            new_players = yield result
            if new_players is not None:
                players = new_players

def _host_game_iter(*args, **kwargs):
    game = _host_game_aiter(*args, **kwargs)
    new_playerconfig = None
    while True:
        new_playerconfig = yield asyncio.get_event_loop().run_until_complete(game.asend(new_playerconfig))


async def _join_game(players, realtime, portconfig, save_replay_as=None, step_time_limit=None, game_time_limit=None):
    async with SC2Process(fullscreen=players[1].fullscreen) as server:
        await server.ping()

        client = Client(server._ws)

        try:
            result = await _play_game(players[1], client, realtime, portconfig, step_time_limit, game_time_limit)
            if save_replay_as is not None:
                await client.save_replay(save_replay_as)
            await client.leave()
            await client.quit()
        except ConnectionAlreadyClosed:
            logging.error(f"Connection was closed before the game ended")
            return None

        return result

def run_game(map_settings, players, **kwargs):
    if sum(isinstance(p, (Human, Bot)) for p in players) > 1:
        host_only_args = ["save_replay_as", "rgb_render_config", "random_seed"]
        join_kwargs = {k: v for k, v in kwargs.items() if k not in host_only_args}

        portconfig = Portconfig()
        result = asyncio.get_event_loop().run_until_complete(asyncio.gather(
            _host_game(map_settings, players, **kwargs, portconfig=portconfig),
            _join_game(players, **join_kwargs, portconfig=portconfig)
        ))
    else:
        result = asyncio.get_event_loop().run_until_complete(
            _host_game(map_settings, players, **kwargs)
        )
    return result
