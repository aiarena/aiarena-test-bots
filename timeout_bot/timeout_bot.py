from sc2 import run_game, maps, Race, Difficulty, BotAI
from sc2.player import Bot, Computer
import random
import asyncio

class timeout_bot(BotAI):
    def __init__(self):
        super().__init__()
        self.actions = []

    async def on_step(self, iteration):
       pass

