import sc2, sys
from __init__ import run_ladder_game
from sc2 import Race, Difficulty
from sc2.player import Bot, Computer
import os

# Load bot
from basic_bot import basic_bot
bot = Bot(Race.Terran, basic_bot())

# Start game
try:
    if __name__ == '__main__':
        if "--LadderServer" in sys.argv:
            # Ladder game started by LadderManager
            print("Starting ladder game...")
            result, opponentid = run_ladder_game(bot)
            print(result," against opponent ", opponentid)
        else:
            # Local game
            print("Starting local game...")
            sc2.run_game(sc2.maps.get("AutomatonLE"), [
                bot,
                Computer(Race.Protoss, Difficulty.CheatInsane)
            ], realtime=False)
except Exception as e:
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),"data/errors.txt"),"a+") as f:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        f.write(str(exc_type)+" "+fname+" "+ exc_tb.tb_lineno)


