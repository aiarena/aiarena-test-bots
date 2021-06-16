from typing import Any, Dict, List, Optional, Set, Tuple, Union  # mypy type checking

from .constants import geyser_ids, mineral_ids
from .data import Alliance, DisplayType
from .ids.effect_id import EffectId
from .ids.upgrade_id import UpgradeId
from .pixel_map import PixelMap
from .position import Point2, Point3
from .power_source import PsionicMatrix
from .score import ScoreDetails
from .unit import Unit
from .units import Units


class Blip:
    def __init__(self, proto):
        self._proto = proto

    @property
    def is_blip(self) -> bool:
        """Detected by sensor tower."""
        return self._proto.is_blip

    @property
    def is_snapshot(self) -> bool:
        return self._proto.display_type == DisplayType.Snapshot.value

    @property
    def is_visible(self) -> bool:
        return self._proto.display_type == DisplayType.Visible.value

    @property
    def alliance(self) -> Alliance:
        return self._proto.alliance

    @property
    def is_mine(self) -> bool:
        return self._proto.alliance == Alliance.Self.value

    @property
    def is_enemy(self) -> bool:
        return self._proto.alliance == Alliance.Enemy.value

    @property
    def position(self) -> Point2:
        """2d position of the blip."""
        return self.position3d.to2

    @property
    def position3d(self) -> Point3:
        """3d position of the blip."""
        return Point3.from_proto(self._proto.pos)


class Common:
    ATTRIBUTES = [
        "player_id",
        "minerals", "vespene",
        "food_cap", "food_used",
        "food_army", "food_workers",
        "idle_worker_count", "army_count",
        "warp_gate_count", "larva_count"
    ]

    def __init__(self, proto):
        self._proto = proto

    def __getattr__(self, attr):
        assert attr in self.ATTRIBUTES, f"'{attr}' is not a valid attribute"
        return int(getattr(self._proto, attr))


class EffectData:
    def __init__(self, proto):
        self._proto = proto

    @property
    def id(self) -> EffectId:
        return EffectId(self._proto.effect_id)

    @property
    def positions(self) -> Set[Point2]:
        return {Point2.from_proto(p) for p in self._proto.pos}

    @property
    def alliance(self) -> Alliance:
        return self._proto.alliance

    @property
    def owner(self) -> int:
        return self._proto.owner

    @property
    def radius(self) -> float:
        return self._proto.radius

    def __repr__(self) -> str:
        return f"{self.id} with radius {self.radius} at {self.positions}"


class GameState:
    def __init__(self, response_observation):
        self.response_observation = response_observation
        self.actions = response_observation.actions  # successful actions since last loop
        self.action_errors = response_observation.action_errors  # error actions since last loop

        # https://github.com/Blizzard/s2client-proto/blob/51662231c0965eba47d5183ed0a6336d5ae6b640/s2clientprotocol/sc2api.proto#L575
        # TODO: implement alerts https://github.com/Blizzard/s2client-proto/blob/51662231c0965eba47d5183ed0a6336d5ae6b640/s2clientprotocol/sc2api.proto#L640
        self.observation = response_observation.observation
        self.observation_raw = self.observation.raw_data
        self.dead_units: Set[int] = self.observation_raw.event.dead_units  # returns set of tags of units that died
        self.alerts = self.observation.alerts
        self.player_result = response_observation.player_result
        self.chat = response_observation.chat
        self.common: Common = Common(self.observation.player_common)

        # Area covered by Pylons and Warpprisms
        self.psionic_matrix: PsionicMatrix = PsionicMatrix.from_proto(self.observation_raw.player.power_sources)
        self.game_loop: int = self.observation.game_loop  # 22.4 per second on faster game speed

        # https://github.com/Blizzard/s2client-proto/blob/33f0ecf615aa06ca845ffe4739ef3133f37265a9/s2clientprotocol/score.proto#L31
        self.score: ScoreDetails = ScoreDetails(self.observation.score)
        self.abilities = self.observation.abilities  # abilities of selected units

        self._blipUnits = []
        self.own_units: Units = Units([])
        self.enemy_units: Units = Units([])
        self.mineral_field: Units = Units([])
        self.vespene_geyser: Units = Units([])
        self.resources: Units = Units([])
        self.destructables: Units = Units([])
        self.watchtowers: Units = Units([])
        self.units: Units = Units([])

        for unit in self.observation.raw_data.units:
            if unit.is_blip:
                self._blipUnits.append(unit)
            else:
                unit_obj = Unit(unit)
                self.units.append(unit_obj)
                alliance = unit.alliance
                # Alliance.Neutral.value = 3
                if alliance == 3:
                    unit_type = unit.unit_type
                    # XELNAGATOWER = 149
                    if unit_type == 149:
                        self.watchtowers.append(unit_obj)
                    # mineral field enums
                    elif unit_type in mineral_ids:
                        self.mineral_field.append(unit_obj)
                        self.resources.append(unit_obj)
                    # geyser enums
                    elif unit_type in geyser_ids:
                        self.vespene_geyser.append(unit_obj)
                        self.resources.append(unit_obj)
                    # all destructable rocks
                    else:
                        self.destructables.append(unit_obj)
                # Alliance.Self.value = 1
                elif alliance == 1:
                    self.own_units.append(unit_obj)
                # Alliance.Enemy.value = 4
                elif alliance == 4:
                    self.enemy_units.append(unit_obj)
        self.upgrades: Set[UpgradeId] = {UpgradeId(upgrade) for upgrade in self.observation_raw.player.upgrade_ids}

        # Set of unit tags that died this step
        self.dead_units: Set[int] = {dead_unit_tag for dead_unit_tag in self.observation_raw.event.dead_units}
        # Set of enemy units detected by own sensor tower, as blips have less unit information than normal visible units
        self.blips: Set[Blip] = {Blip(unit) for unit in self._blipUnits}
        # self.visibility[point]: 0=Hidden, 1=Fogged, 2=Visible
        self.visibility: PixelMap = PixelMap(self.observation_raw.map_state.visibility, mirrored=True)
        # self.creep[point]: 0=No creep, 1=creep
        self.creep: PixelMap = PixelMap(self.observation_raw.map_state.creep, mirrored=True, in_bits=True)

        # Effects like ravager bile shot, lurker attack, everything in effect_id.py
        self.effects: Set[EffectData] = {EffectData(effect) for effect in self.observation_raw.effects}
        """ Usage:
        for effect in self.state.effects:
            if effect.id == EffectId.RAVAGERCORROSIVEBILECP:
                positions = effect.positions
                # dodge the ravager biles
        """
