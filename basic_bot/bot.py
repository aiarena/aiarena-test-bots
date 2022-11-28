from sc2.bot_ai import BotAI
from sc2.data import Result


class TestBot(BotAI):
    async def on_step(self, iteration):
        if iteration == 0:
            for worker in self.workers:
                worker.attack(self.enemy_start_locations[0])

        self.game_step = 100
