#!/usr/bin/env python
from __future__ import annotations

from typing import Optional, Sequence, Set, Tuple, Dict, Iterator, Union, \
    Collection

from arcade import Sprite, SpriteSolidColor, load_textures, load_texture
from arcade.arcade_types import Color, Point
from arcade.key import LCTRL

from buildings.buildings import Building
from effects.sound import (
    UNITS_SELECTION_CONFIRMATIONS, UNITS_MOVE_ORDERS_CONFIRMATIONS
)
from utils.classes import HashedList
from utils.colors import GREEN, RED, YELLOW
from game import Game
from players_and_factions.player import PlayerEntity
from units.units import Unit, Vehicle
from utils.functions import get_path_to_file, ignore_in_menu
from utils.geometry import average_position_of_points_group

UNIT_HEALTH_BAR_WIDTH = 5
SOLDIER_HEALTH_BAR_WIDTH = 4
BUILDING_HEALTH_BAR_WIDTH = 10
UNIT_HEALTHBAR_LENGTH_RATIO = 0.6
SOLDIER_HEALTHBAR_LENGTH_RATIO = 0.4
BUILDING_HEALTHBAR_LENGTH_RATIO = 1.8

selection_textures = load_textures(
    get_path_to_file('unit_selection_marker.png'),
    [(i * 60, 0, 60, 60) for i in range(10)]
)
building_selection_texture = load_texture(
    get_path_to_file('building_selection_marker.png'), 0, 0, 180, 180
)
soldier_selection_texture = load_texture(
    get_path_to_file('soldier_selection_marker.png'), 0, 0, 40, 40
)


def selected_unit_marker(entity):
    if entity.is_infantry:
        return SelectedSoldierMarker(entity)
    else:
        return SelectedUnitMarker(entity)


class SelectedEntityMarker:
    """
    This class produces rectangle-unit-or-building-selection markers showing
    that a particular Unit or Building is selected by player and displaying
    some info about selected, like health level or lack of fuel icon. Each
    marker can contain many Sprites which are dynamically created, updated and
    destroyed. You must cache SelectionMarker instances and their Sprites in
    distinct data-structures. Markers are stored in ordinary list and
    Sprites in SpriteLists.
    """
    game: Optional[Game] = None
    healthbar_width = 0
    healthbar_length_ratio = 1

    def __init__(self, selected: PlayerEntity):
        selected.selection_marker = self
        self.position = selected.position
        self.selected = selected
        self.borders = Sprite()
        self.sprites = []  # not updated, used to cache and kill sprites only

        self.health = health = selected.health
        width, height, color = self.health_to_color_and_size(health)
        self.healthbar = healthbar = SpriteSolidColor(width, height, color)

        self.sprites = sprites = [self.borders, healthbar]
        self.game.selection_markers_sprites.extend(sprites)

    def health_to_color_and_size(self, health: float) -> Tuple[int, int, Color]:
        length = int(self.healthbar_length_ratio * health)
        if health > 66:
            return length, self.healthbar_width, GREEN
        elif health > 33:
            return length, self.healthbar_width, YELLOW
        return length, self.healthbar_width, RED

    def update(self):
        self.position = x, y = self.selected.position
        self.update_healthbar(x)
        for sprite in self.sprites[:-1]:
            sprite.position = x, y

    def update_healthbar(self, x):
        if (health := self.selected.health) != self.health:
            width, height, color = self.health_to_color_and_size(health)
            if color != self.healthbar.color:
                self.replace_healthbar_with_new_color(color, height, width)
            else:
                self.healthbar.width = width
        ratio = self.healthbar_length_ratio * 0.5
        self.healthbar.position = x - (100 - health) * ratio, self.borders.top

    def replace_healthbar_with_new_color(self, color, height, width):
        self.healthbar.kill()
        self.healthbar = bar = SpriteSolidColor(width, height, color)
        self.sprites.append(self.healthbar)
        self.game.selection_markers_sprites.append(bar)

    def kill(self):
        self.selected.selection_marker = None
        for sprite in self.sprites:
            sprite.kill()


class SelectedUnitMarker(SelectedEntityMarker):
    healthbar_width = UNIT_HEALTH_BAR_WIDTH
    healthbar_length_ratio = UNIT_HEALTHBAR_LENGTH_RATIO

    def __init__(self, selected: Unit):
        super().__init__(selected)
        # units selection marker has 10 versions, blank + 9 different numbers
        # to show which PermanentUnitsGroup an Unit belongs to:
        group_index = selected.permanent_units_group
        self.borders.texture = selection_textures[group_index]


class SelectedSoldierMarker(SelectedEntityMarker):
    healthbar_width = SOLDIER_HEALTH_BAR_WIDTH
    healthbar_length_ratio = SOLDIER_HEALTHBAR_LENGTH_RATIO

    def __init__(self, selected: Unit):
        super().__init__(selected)
        # units selection marker has 10 versions, blank + 9 different numbers
        # to show which PermanentUnitsGroup an Unit belongs to:
        self.borders.texture = soldier_selection_texture


class SelectedVehicleMarker(SelectedUnitMarker):

    def __init__(self, selected: Vehicle):
        super().__init__(selected)
        self.fuel = selected.fuel
        self.fuel_bar = None
        
    def update(self):
        self.position = x, y = self.selected.position
        self.update_healthbar(x)
        self.update_fuel_bar(x)
        for sprite in self.sprites[:-1]:
            sprite.position = x, y

    def update_fuel_bar(self, x):
        pass


class SelectedBuildingMarker(SelectedEntityMarker):
    healthbar_width = BUILDING_HEALTH_BAR_WIDTH
    healthbar_length_ratio = BUILDING_HEALTHBAR_LENGTH_RATIO

    def __init__(self, building: PlayerEntity):
        super().__init__(building)
        self.borders.texture = building_selection_texture


class PermanentUnitsGroup:
    """
    Player can group units by selecting them with mouse and pressing CTRL +
    numeric keys (1-9). Such groups could be then quickly selected by pressing
    their numbers.
    """
    game: Optional[Game] = None

    def __init__(self, group_id: int, units: Sequence[Unit]):
        self.group_id = group_id
        self.units: Set[Unit] = set(units)
        self.game.units_manager.permanent_units_groups[group_id] = self
        for unit in units:
            unit.set_permanent_units_group(group_id)

    def __contains__(self, unit: Unit) -> bool:
        return unit in self.units

    def __iter__(self) -> Iterator:
        return iter(self.units)

    @property
    def position(self) -> Point:
        positions = [(u.center_x, u.center_y) for u in self.units]
        return average_position_of_points_group(positions)

    def discard(self, unit: Unit):
        self.units.discard(unit)
        if not self.units:
            del self.game.units_manager.permanent_units_groups[self.group_id]

    def __getstate__(self) -> Dict:
        return {'group_id': self.group_id, 'units': [u.id for u in self.units]}

    def __setstate__(self, state: Dict):
        self.__dict__.update(state)
        self.units = {self.game.units.get_by_id(u_id) for u_id in self.units}

    def __del__(self):
        for unit in self.units:
            unit.permanent_units_group = 0


class UnitsManager:
    """
    This class is an intermediary between Cursor class and PlayerEntities. It
    allows player to interact with units, buildings etc. by the mouse-cursor.
    It keeps track of the currently selected units and provides a way for the
    player to give them orders by the mouse-clicks. UnitsManager should be an
    attribute of Cursor class. Game should also have it's reference.
    """
    game: Optional[Game] = None

    def __init__(self, cursor):
        self.cursor = cursor
        self.window = cursor.window
        # after left button is released, Units from drag-selection are selected
        # permanently, and will be cleared after new selection or deselecting
        # them with right-button click:
        self.selected_units: HashedList[Unit] = HashedList()
        self.selected_building: Optional[Building] = None

        # for each selected Unit create SelectedUnitMarker, a Sprite showing
        # that this unit is currently selected and will react for player's
        # actions. Sprites are actually drawn and updated in Game class, but
        # here we keep them cashed to easily manipulate them:
        self.selection_markers: Set[SelectedEntityMarker] = set()

        # Player can create group of Units by CTRL + 0-9 keys, and then
        # select those groups quickly with 0-9 keys, or even move screen tp
        # the position of the group by pressing numeric key twice. See the
        # PermanentUnitsGroup class in units_management.py
        self.permanent_units_groups: Dict[int, PermanentUnitsGroup] = {}

    @property
    def units_or_building_selected(self) -> bool:
        return self.selected_units or self.selected_building is not None

    @ignore_in_menu
    def on_left_click_without_selection(self, modifiers, x, y):
        pointed = self.cursor.pointed_unit or self.cursor.pointed_building
        if pointed is not None:
            self.on_player_entity_clicked(pointed)
        elif units := self.selected_units:
            self.on_terrain_click_with_units(x, y, modifiers, units)

    @ignore_in_menu
    def on_terrain_click_with_units(self, x, y, modifiers, units):
        if self.game.map.position_to_node(x, y).walkable:
            self.create_movement_order(units, x, y)
        else:
            x, y = self.game.pathfinder.get_closest_walkable_position(x, y)
            self.on_terrain_click_with_units(x, y, modifiers, units)

    def create_movement_order(self, units, x, y):
        if LCTRL in self.game.window.keyboard.keys_pressed:
            self.game.pathfinder.enqueue_waypoint(units, x, y)
        else:
            self.send_units_to_pointed_location(units, x, y)
        self.window.sound_player.play_random(UNITS_MOVE_ORDERS_CONFIRMATIONS)

    def send_units_to_pointed_location(self, units, x, y):
        self.game.pathfinder.navigate_units_to_destination(units, x, y)

    def on_player_entity_clicked(self, clicked: PlayerEntity):
        if clicked.selectable:
            self.on_friendly_player_entity_clicked(clicked)
        elif units := self.selected_units:
            self.on_hostile_player_entity_clicked(clicked, units)

    def on_friendly_player_entity_clicked(self, clicked: PlayerEntity):
        clicked: Union[Unit, Building]
        self.unselect_all_selected()
        if clicked.is_building:
            self.on_building_clicked(clicked)
        else:
            self.on_unit_clicked(clicked)

    def on_hostile_player_entity_clicked(self, clicked: PlayerEntity, units):
        cx, cy = clicked.position
        x, y = self.game.pathfinder.get_closest_walkable_position(cx, cy)
        self.send_units_to_pointed_location(units, x, y)

    def on_unit_clicked(self, clicked_unit: Unit):
        self.select_units(clicked_unit)

    def on_building_clicked(self, clicked_building: Building):
        # TODO: resolving possible building-related tasks for units first
        self.select_building(clicked_building)

    def select_building(self, building: Building):
        self.selected_building = building
        self.create_selection_markers(building=building)
        self.game.update_interface_content(context=building)

    def update_selection_markers_set(self, new, lost):
        discarded = {m for m in self.selection_markers if m.selected in lost}
        self.clear_selection_markers(discarded)
        self.create_selection_markers(new)

    @ignore_in_menu
    def select_units(self, *units: Unit):
        self.selected_units.extend(units)
        self.create_selection_markers(units)
        self.game.update_interface_content(context=units)
        self.window.sound_player.play_random(UNITS_SELECTION_CONFIRMATIONS)

    def create_selection_markers(self, units=None, building=None):
        if units is not None:
            self.create_units_selection_markers(units)
        if building is not None:
            self.create_building_selection_marker(building)

    def create_units_selection_markers(self, units: Collection[Unit]):
        self.selection_markers.update(
            SelectedSoldierMarker(unit) if unit.is_infantry
            else SelectedUnitMarker(unit) for unit in units
        )

    def create_building_selection_marker(self, building: Building):
        marker = SelectedBuildingMarker(building)
        self.selection_markers.add(marker)

    def remove_from_selection_markers(self, entity: PlayerEntity):
        for marker in self.selection_markers.copy():
            if marker.selected is entity:
                self.kill_selection_marker(marker)

    def kill_selection_marker(self, marker):
        self.selection_markers.discard(marker)
        marker.kill()

    @ignore_in_menu
    def unselect_all_selected(self):
        self.selected_units.clear()
        self.clear_selection_markers()
        self.selected_building = None
        self.game.update_interface_content(context=None)

    def clear_selection_markers(self,
                                killed: Set[SelectedUnitMarker] = None):
        killed = self.selection_markers.copy() if killed is None else killed
        for marker in killed:
            self.kill_selection_marker(marker)

    def update_selection_markers(self):
        for marker in self.selection_markers:
            marker.update() if marker.selected.alive else marker.kill()

    def create_new_permanent_units_group(self, digit: int):
        units = self.selected_units.copy()
        new_group = PermanentUnitsGroup(group_id=digit, units=units)
        self.permanent_units_groups[digit] = new_group
        self.unselect_all_selected()
        self.select_units(*units)

    @ignore_in_menu
    def select_permanent_units_group(self, group_id: int):
        try:
            group = self.permanent_units_groups[group_id]
            selected = self.selected_units
            if selected and set(selected) == group.units:
                self.window.move_viewport_to_the_position(*group.position)
            else:
                self.unselect_all_selected()
                self.select_units(*group.units)
        except KeyError:
            pass

    def on_human_entity_being_killed(self, entity: PlayerEntity):
        if len(self.selected_units) == 1 and entity in self.selected_units:
            self.unselect_all_selected()
        self.cursor.update_cursor_texture()
