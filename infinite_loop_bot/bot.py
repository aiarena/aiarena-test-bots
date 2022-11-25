import time

from sc2.bot_ai import BotAI


class TestBot(BotAI):
    async def on_step(self, iteration):
        if iteration == 0:
            self.game_step = 20
            for worker in self.workers:
                worker.attack(self.enemy_start_locations[0])

        if iteration >= 5:
            while True:
                time.sleep(10)
