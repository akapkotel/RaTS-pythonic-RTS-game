#!/usr/bin/env python
from __future__ import annotations

from typing import Optional, Dict

from arcade import AnimatedTimeBasedSprite
from arcade.arcade_types import Point

from game import Game
from utils.enums import Robustness, UnitWeight
from utils.functions import get_path_to_file
from utils.logging import log
from utils.improved_spritelists import SelectiveSpriteList
from utils.scheduling import EventsCreator
from utils.ownership_relations import OwnedObject


class GameObject(AnimatedTimeBasedSprite, EventsCreator, OwnedObject):
    """
    GameObject represents all in-game objects, like units, buildings,
    terrain props, trees etc.
    """
    game: Optional[Game] = None
    total_objects_count = 0

    def __init__(self,
                 object_name: str,
                 robustness: Robustness = 0,
                 position: Point = (0, 0),
                 id: Optional[int] = None):
        x, y = position
        filename = get_path_to_file(object_name)
        super().__init__(filename, center_x=x, center_y=y)
        OwnedObject.__init__(self, owners=True)
        EventsCreator.__init__(self)
        self.object_name = object_name

        GameObject.total_objects_count += 1
        if id is None:
            self.id = GameObject.total_objects_count
        else:
            self.id = id

        self._robustness = robustness  # used to determine if object makes a
        # tile not-walkable or can be destroyed by vehicle entering the MapTile

        self.updated = True
        self.rendered = True

        self.selective_spritelist: Optional[SelectiveSpriteList] = None

    def __repr__(self) -> str:
        return f'GameObject: {self.object_name} id: {self.id}'

    def save(self) -> Dict:
        return {
            'id': self.id,
            'object_name': self.object_name,
            'position': self._position,  # (self.center_x, self.center_y)
            'scheduled_events': self.scheduled_events_to_shelve_data()
        }

    def destructible(self, weight: UnitWeight = 0) -> bool:
        return weight > self._robustness

    def on_update(self, delta_time: float = 1 / 60):
        self.center_x += self.change_x
        self.center_y += self.change_y
        if self.frames:
            self.update_animation(delta_time)

    def update_animation(self, delta_time: float = 1 / 60):
        super().update_animation(delta_time)

    def start_drawing(self):
        self.rendered = True

    def stop_drawing(self):
        self.rendered = False

    def start_updating(self):
        self.updated = True

    def stop_updating(self):
        self.updated = False

    def kill(self):
        log(f'Removing GameObject: {self.object_name}')
        self.unregister_from_all_owners()
        self.selective_spritelist.remove(self)
        super().kill()


class TerrainObject(GameObject):

    def __init__(self, filename: str, robustness: Robustness, position: Point):
        super().__init__(filename, robustness, position)
        node = self.game.map.position_to_node(*self.position)
        node.set_pathable(False)

    def kill(self):
        node = self.game.map.position_to_node(*self.position)
        node.set_pathable(True)
        super().kill()
