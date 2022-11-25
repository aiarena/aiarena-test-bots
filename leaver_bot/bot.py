from sc2.bot_ai import BotAI


class TestBot(BotAI):
    async def on_step(self, iteration):
        if iteration == 0:
            self.game_step = 20
        if iteration >= 5:
            await self.client.leave()
