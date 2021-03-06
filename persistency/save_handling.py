#!/usr/bin/env python

import os
import shelve
import time

from typing import List, Dict, Callable, Any

from utils.classes import Singleton
from utils.functions import find_paths_to_all_files_of_type
from utils.logging import log, logger
from utils.data_types import SavedGames
from players_and_factions.player import Faction
from map.map import Map, Pathfinder
from user_interface.minimap import MiniMap
from gameobjects.spawning import GameObjectsSpawner
from effects.explosions import ExplosionsPool
# CIRCULAR IMPORTS MOVED TO THE BOTTOM OF FILE!

MAP_EXTENSION = '.map'
SAVE_EXTENSION = '.sav'
SCENARIO_EXTENSION = '.scn'


class SaveManager(Singleton):
    """
    This manager works not only with player-created saved games, but also with
    predefined scenarios stored in the same file-format, but in ./scenarios
    direction.
    """
    game = None

    def __init__(self, saves_path: str, scenarios_path: str, window):
        self.window = window
        self.scenarios_path = os.path.abspath(scenarios_path)
        self.saves_path = os.path.abspath(saves_path)

        self.scenarios: SavedGames = {}
        self.saved_games: SavedGames = {}

        self.update_scenarios(SCENARIO_EXTENSION, self.scenarios_path)
        self.update_saves(SAVE_EXTENSION, self.saves_path)

        log(f'Found {len(self.scenarios)} scenarios in {self.saves_path}.')
        log(f'Found {len(self.saved_games)} saved games in {self.saves_path}.')

    def update_scenarios(self, extension: str, scenarios_path: str):
        self.scenarios = self.find_all_files(extension, scenarios_path)
        for name, path in self.scenarios.items():
            full_scenario_path = os.path.join(scenarios_path, name)
            with shelve.open(full_scenario_path, 'r') as scenario_file:
                self.window.missions.append(scenario_file['mission_descriptor'])

    def update_saves(self, extension: str, saves_path: str):
        self.saved_games = self.find_all_files(extension, saves_path)

    @staticmethod
    def find_all_files(extension: str, path: str) -> SavedGames:
        names_to_paths = find_paths_to_all_files_of_type(extension, path)
        return {
            name: os.path.join(path, name) for name, path in names_to_paths.items()
        }

    def save_game(self, save_name: str, game: 'Game', scenario: bool = False):
        extension = SCENARIO_EXTENSION if scenario else SAVE_EXTENSION
        path = self.scenarios_path if scenario else self.saves_path
        full_save_path = os.path.join(path, save_name + extension)
        self.delete_file(save_name, scenario)  # to avoid 'adding' to existing file
        with shelve.open(full_save_path) as file:
            file['saved_date'] = time.localtime()
            file['timer'] = game.save_timer()
            file['settings'] = game.settings
            file['viewports'] = game.viewport, game.window.menu_view.viewport
            file['map'] = game.map.save()
            file['factions'] = [f.save() for f in game.factions.values()]
            file['players'] = game.players
            file['local_human_player'] = game.local_human_player.id
            file['units'] = [unit.save() for unit in game.units]
            file['buildings'] = [building.save() for building in game.buildings]
            file['mission_descriptor'] = game.current_mission.get_descriptor
            file['mission'] = game.current_mission
            file['permanent_units_groups'] = game.units_manager.permanent_units_groups
            file['fog_of_war'] = game.fog_of_war
            file['mini_map'] = game.mini_map.save()
            file['scheduled_events'] = self.game.events_scheduler.save()
        self.update_saves(extension, path)
        log(f'Game saved successfully as: {save_name + extension}', True)

    def get_full_path_to_file_with_extension(self, save_name: str) -> str:
        """
        Since we do not know if player want's to load his own saved game or to
        start a new game from a predefined .scn file, we determine it checking
        the file name provided to us and adding proper path and extension.
        """
        if SAVE_EXTENSION in save_name:
            return os.path.join(self.saves_path, save_name)
        elif SCENARIO_EXTENSION in save_name:
            return os.path.join(self.scenarios_path, save_name)
        elif (full_name := save_name + SCENARIO_EXTENSION) in self.scenarios:
            return os.path.join(self.scenarios_path, full_name)
        else:
            return os.path.join(self.saves_path, save_name + SAVE_EXTENSION)

    def load_game(self, file_name: str):
        full_save_path = self.get_full_path_to_file_with_extension(file_name)
        with shelve.open(full_save_path) as file:
            loaded = ('timer', 'settings', 'viewports', 'map', 'factions',
                      'players', 'local_human_player', 'units', 'buildings',
                      'mission', 'permanent_units_groups', 'fog_of_war',
                      'mini_map', 'scheduled_events')
            progress = 1 / (len(loaded) + 1)
            for name in loaded:
                log(f'Loading: {name}...', console=True)
                function = eval(f'self.load_{name}')
                argument = file[name]
                yield self.loading_step(function, argument, progress)
        log(f'Game {file_name} loaded successfully!', console=True)
        yield progress

    @logger()
    def loading_step(self, function: Callable, argument: Any, progress: float):
        function(argument)
        return progress

    def load_timer(self, loaded_timer):
        self.game.timer = loaded_timer

    def load_settings(self, settings):
        self.game.window.settings = self.game.settings = settings
        # recalculating rendering layers is required since settings changed and
        # LayeredSpriteList instances where instantiated with settings values
        # from the menu, not from the loaded file
        for spritelist in self.game.updated:
            try:
                spritelist.rendering_layers = spritelist.create_rendering_layers()
            except AttributeError:
                pass

    def load_viewports(self, viewports):
        self.game.viewport = viewports[0]
        self.game.window.menu_view.viewport = viewports[1]

    def load_map(self, map_file):
        self.game.map = game_map = Map(map_settings=map_file)
        self.game.pathfinder = Pathfinder(game_map)

    def load_factions(self, factions):
        for f in factions:
            id, name, f, e = f['id'], f['name'], f['friends'], f['enemies']
            self.game.factions[id] = Faction(id, name, f, e)

    def load_players(self, players):
        self.game.players = {i: players[i] for i in players}

    def load_local_human_player(self, index):
        self.game.local_human_player = self.game.players[index]

    def load_units(self, units):
        return self.load_entities(units)

    def load_buildings(self, buildings):
        return self.load_entities(buildings)

    def load_entities(self, entities):
        """Respawn Units and Buildings."""
        if self.game.spawner is None:
            self.game.spawner = GameObjectsSpawner()
            self.game.explosions_pool = ExplosionsPool()
        for e in entities:
            entity = self.game.spawn(
                e['object_name'], e['player'], e['position'], id=e['id']
            )
            entity.load(e)

    def load_mission(self, mission):
        self.game.current_mission = mission

    def load_permanent_units_groups(self, groups):
        self.game.units_manager.permanent_units_groups = groups
        for group_id, group in groups.items():
            for unit in group:
                unit.set_permanent_units_group(group_id)

    def load_fog_of_war(self, fog_of_war):
        self.game.fog_of_war = fog_of_war

    def load_mini_map(self, minimap):
        self.game.mini_map = MiniMap(minimap, loaded=True)

    def load_scheduled_events(self, scheduled_events: List[Dict]):
        self.game.events_scheduler.load(scheduled_events)

    def delete_file(self, save_name: str, scenario: bool):
        paths = self.scenarios if scenario else self.saved_games
        try:
            os.remove(paths[save_name])
            del paths[save_name]
        except Exception as e:
            log(f'{str(e)}', console=True)

    def rename_saved_game(self, old_name: str, new_name: str):
        try:
            new = os.path.join(self.saves_path, new_name)
            os.rename(self.saved_games[old_name], new)
            self.saved_games[new_name] = new
            del self.saved_games[old_name]
        except Exception as e:
            log(f'{str(e)}', console=True)


# these imports are placed here to avoid circular-imports issue:
from game import Game
