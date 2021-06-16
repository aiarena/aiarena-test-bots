from sc2 import run_game, maps, Race, Difficulty, BotAI


class stop_bot(BotAI):
    def __init__(self):
        super().__init__()

    async def on_step(self, iteration):
        if iteration == 0:
            for w in self.workers:
                await self.do(w.stop())

