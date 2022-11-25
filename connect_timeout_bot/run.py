# pylint: disable=E0401
import sys

from __init__ import run_ladder_game

# Load bot
from bot import TestBot

from sc2 import maps
from sc2.data import Difficulty, Race
from sc2.main import run_game
from sc2.player import Bot, Computer

bot = Bot(Race.Terran, TestBot())

# Start game
if __name__ == "__main__":
    if "--LadderServer" in sys.argv:
        while True:
            pass
    else:
        # Local game
        print("Starting local game...")
        run_game(maps.get("Abyssal Reef LE"), [bot, Computer(Race.Protoss, Difficulty.VeryHard)], realtime=True)