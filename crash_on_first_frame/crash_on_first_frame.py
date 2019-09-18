from sc2 import run_game, maps, Race, Difficulty, BotAI
from sc2.player import Bot, Computer

class crash_on_first_frame(BotAI):
    def __init__(self):
        super().__init__()
        self.actions = []

    async def on_step(self, iteration):
        self.actions = []

        if iteration == 0:
            import non_existing_lib