from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass

import pygame

from pacman.audio import AudioManager
from pacman.leaderboard import LeaderboardConfigError, LeaderboardService, LeaderboardServiceError, ScoreEntry
from pacman.maps import FRUIT_SCORES, build_stage_map, fruit_for_stage, stage_map_number, total_map_count

GRID_SIZE = 28
TOP_MARGIN = 96
SIDE_PANEL = 440
BOTTOM_MARGIN = 24
FPS = 60
BACKGROUND = (7, 8, 16)
MAZE_BACKGROUND = (11, 14, 28)
WALL_COLOR = (43, 94, 255)
WALL_ACCENT = (145, 182, 255)
PORTAL_COLOR = (104, 237, 255)
PORTAL_ACCENT = (176, 249, 255)
TEXT = (235, 235, 245)
SUBTLE_TEXT = (170, 176, 192)
HIGHLIGHT = (255, 216, 94)
PACMAN_YELLOW = (255, 221, 59)
DOT = (248, 233, 190)
POWER_PELLET = (255, 189, 255)
GHOST_COLORS = (
    (255, 72, 91),
    (255, 161, 78),
    (87, 213, 255),
    (255, 123, 247),
)
FRUIT_COLORS = {
    "cherry": (220, 30, 70),
    "strawberry": (247, 54, 92),
    "banana": (255, 219, 77),
    "apple": (94, 204, 76),
    "orange": (255, 150, 45),
    "pear": (189, 235, 92),
}
DIR_UP = pygame.Vector2(0, -1)
DIR_DOWN = pygame.Vector2(0, 1)
DIR_LEFT = pygame.Vector2(-1, 0)
DIR_RIGHT = pygame.Vector2(1, 0)
STOP = pygame.Vector2(0, 0)
DIRECTIONS = (DIR_UP, DIR_DOWN, DIR_LEFT, DIR_RIGHT)
ACTION_TO_DIRECTION = {
    "up": DIR_UP,
    "down": DIR_DOWN,
    "left": DIR_LEFT,
    "right": DIR_RIGHT,
}

GHOST_STAGE_EASY_END = 5
GHOST_STAGE_MEDIUM_END = 10

GHOST_SPEED_EASY_BASE = 4.12
GHOST_SPEED_EASY_STEP = 0.06
GHOST_SPEED_MEDIUM_BASE = 4.4
GHOST_SPEED_MEDIUM_STEP = 0.06
GHOST_SPEED_HARD_BASE = 4.7
GHOST_SPEED_HARD_STEP = 0.045
GHOST_SPEED_HARD_CAP = 5.18

GHOST_AGGRESSION_EASY_BASE = 0.64
GHOST_AGGRESSION_EASY_STEP = 0.04
GHOST_AGGRESSION_EASY_CAP = 0.8
GHOST_AGGRESSION_MEDIUM_BASE = 0.82
GHOST_AGGRESSION_MEDIUM_STEP = 0.02
GHOST_AGGRESSION_MEDIUM_CAP = 0.9
GHOST_AGGRESSION_HARD_BASE = 0.92
GHOST_AGGRESSION_HARD_STEP = 0.01
GHOST_AGGRESSION_HARD_CAP = 0.98
FRUIT_DESPAWN_SECONDS = 20.0
FRUIT_CENTER_TOLERANCE = 0.02


@dataclass(slots=True)
class MovingEntity:
    position: pygame.Vector2
    start_cell: tuple[int, int]
    direction: pygame.Vector2
    queued_direction: pygame.Vector2
    color: tuple[int, int, int]
    speed: float

    def reset(self) -> None:
        self.position = pygame.Vector2(self.start_cell)
        self.direction = STOP.copy()
        self.queued_direction = STOP.copy()


@dataclass(slots=True)
class Ghost(MovingEntity):
    name: str
    home_corner: tuple[int, int]
    release_delay: float
    mode: str = "normal"


@dataclass(slots=True)
class Fruit(MovingEntity):
    name: str


@dataclass(slots=True)
class Particle:
    position: pygame.Vector2
    velocity: pygame.Vector2
    color: tuple[int, int, int]
    size: float
    age: float
    duration: float


@dataclass(slots=True)
class RingEffect:
    position: pygame.Vector2
    color: tuple[int, int, int]
    start_radius: float
    end_radius: float
    age: float
    duration: float
    width: int


class GameApp:
    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption("Pacman")

        self.stage_map = build_stage_map(1)
        self.window_width = self.stage_map.width * GRID_SIZE + SIDE_PANEL + 48
        self.window_height = self.stage_map.height * GRID_SIZE + TOP_MARGIN + BOTTOM_MARGIN
        self.window_surface = self.create_window_surface()
        self.screen = pygame.Surface((self.window_width, self.window_height)).convert()
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 22)
        self.small_font = pygame.font.SysFont("consolas", 18)
        self.title_font = pygame.font.SysFont("consolas", 38, bold=True)
        self.big_font = pygame.font.SysFont("consolas", 54, bold=True)
        self.random = random.Random()

        self.key_bindings = {
            "up": pygame.K_UP,
            "down": pygame.K_DOWN,
            "left": pygame.K_LEFT,
            "right": pygame.K_RIGHT,
            "pause": pygame.K_p,
        }
        self.volume_steps = [index / 10 for index in range(0, 11)]
        self.volume_index = 5
        self.settings_return_state = "main_menu"

        self.audio = AudioManager(self.volume_steps[self.volume_index])
        self.audio.start_music()
        self.leaderboard = LeaderboardService()
        self.leaderboard_entries: list[ScoreEntry] = []
        self.high_score = 0
        self.leaderboard_error: str | None = self.leaderboard.last_error

        self.running = True
        self.state = "main_menu"
        self.main_menu_options = ["Play Game", "How to Play", "Leaderboard", "Settings", "Exit Game"]
        self.pause_menu_options = ["Resume", "Settings", "Restart Run", "Main Menu"]
        self.game_over_options = ["Play Again", "Main Menu"]
        self.confirm_options = ["Yes", "No"]
        self.main_menu_index = 0
        self.pause_menu_index = 0
        self.settings_index = 0
        self.confirm_index = 1
        self.game_over_index = 0
        self.confirm_return_state = "main_menu"

        self.message = ""
        self.message_timer = 0.0
        self.round_timer = 0.0
        self.stage_transition_timer = 0.0
        self.pending_stage_number: int | None = None
        self.chase_timer = 0.0
        self.vulnerability_timer = 0.0
        self.dot_eat_count = 0
        self.fruit_spawned = False
        self.fruit_eaten = False
        self.fruit: Fruit | None = None
        self.fruit_time_left: float | None = None
        self.fruit_name = fruit_for_stage(1)
        self.effect_particles: list[Particle] = []
        self.effect_rings: list[RingEffect] = []
        self.pacman_teleport_timer = 0.0
        self.pacman_teleport_path: tuple[tuple[int, int], tuple[int, int]] | None = None

        self.score = 0
        self.lives = 3
        self.stage_number = 1
        self.active_map_index = 0
        self.name_entry_value = ""
        self.pending_name_submission = False

        self.pacman = MovingEntity(
            position=pygame.Vector2(self.stage_map.pacman_start),
            start_cell=self.stage_map.pacman_start,
            direction=STOP.copy(),
            queued_direction=STOP.copy(),
            color=PACMAN_YELLOW,
            speed=4.32,
        )
        self.ghosts: list[Ghost] = []
        self._spawn_ghosts()
        self.refresh_leaderboard()
        self.start_new_run()
        self.state = "main_menu"

    def refresh_leaderboard(self) -> None:
        try:
            self.leaderboard_entries = self.leaderboard.fetch_top_scores()
            self.leaderboard_error = None
        except (LeaderboardConfigError, LeaderboardServiceError):
            self.leaderboard_entries = []
            self.leaderboard_error = self.leaderboard.last_error

        self.high_score = max([entry.score for entry in self.leaderboard_entries], default=0)

    def start_new_run(self) -> None:
        self.score = 0
        self.lives = 3
        self.stage_number = 1
        self.name_entry_value = ""
        self.load_stage(reset_score=False)
        self.state = "playing"
        self.round_timer = 1.5

    def load_stage(self, reset_score: bool = False) -> None:
        if reset_score:
            self.score = 0
        self.stage_map = build_stage_map(self.stage_number)
        self.pacman.start_cell = self.stage_map.pacman_start
        self.pacman.reset()
        self.dot_eat_count = 0
        self.fruit_spawned = False
        self.fruit_eaten = False
        self.fruit = None
        self.fruit_time_left = None
        self.fruit_name = fruit_for_stage(self.stage_number)
        self.effect_particles.clear()
        self.effect_rings.clear()
        self.pacman_teleport_timer = 0.0
        self.pacman_teleport_path = None
        self.stage_transition_timer = 0.0
        self.pending_stage_number = None
        self.chase_timer = 0.0
        self.vulnerability_timer = 0.0
        self._spawn_ghosts()
        self.round_timer = 1.5

    def _spawn_ghosts(self) -> None:
        corners = [
            (1, 1),
            (self.stage_map.width - 2, 1),
            (1, self.stage_map.height - 2),
            (self.stage_map.width - 2, self.stage_map.height - 2),
        ]
        self.ghosts = []
        for index, ghost_start in enumerate(self.stage_map.ghost_starts):
            self.ghosts.append(
                Ghost(
                    position=pygame.Vector2(ghost_start),
                    start_cell=ghost_start,
                    direction=STOP.copy(),
                    queued_direction=STOP.copy(),
                    color=GHOST_COLORS[index % len(GHOST_COLORS)],
                    speed=self.ghost_speed(),
                    name=f"Ghost {index + 1}",
                    home_corner=corners[index % len(corners)],
                    release_delay=index * 1.2,
                    mode="normal",
                )
            )

    @staticmethod
    def pacman_speed() -> float:
        return 4.705882355125

    def ghost_speed(self) -> float:
        stage = max(1, self.stage_number)
        if stage <= GHOST_STAGE_EASY_END:
            return GHOST_SPEED_EASY_BASE + GHOST_SPEED_EASY_STEP * (stage - 1)
        if stage <= GHOST_STAGE_MEDIUM_END:
            return GHOST_SPEED_MEDIUM_BASE + GHOST_SPEED_MEDIUM_STEP * (stage - (GHOST_STAGE_EASY_END + 1))
        return min(
            GHOST_SPEED_HARD_CAP,
            GHOST_SPEED_HARD_BASE + GHOST_SPEED_HARD_STEP * (stage - (GHOST_STAGE_MEDIUM_END + 1)),
        )

    def ghost_aggression(self) -> float:
        stage = max(1, self.stage_number)
        if stage <= GHOST_STAGE_EASY_END:
            return min(GHOST_AGGRESSION_EASY_CAP, GHOST_AGGRESSION_EASY_BASE + GHOST_AGGRESSION_EASY_STEP * (stage - 1))
        if stage <= GHOST_STAGE_MEDIUM_END:
            return min(
                GHOST_AGGRESSION_MEDIUM_CAP,
                GHOST_AGGRESSION_MEDIUM_BASE + GHOST_AGGRESSION_MEDIUM_STEP * (stage - (GHOST_STAGE_EASY_END + 1)),
            )
        return min(
            GHOST_AGGRESSION_HARD_CAP,
            GHOST_AGGRESSION_HARD_BASE + GHOST_AGGRESSION_HARD_STEP * (stage - (GHOST_STAGE_MEDIUM_END + 1)),
        )

    def fruit_speed(self) -> float:
        return 0.5 * (4.95 + min(0.14 * (self.stage_number - 1), 0.84))

    def vulnerability_duration(self) -> float:
        return max(3.5, 7.0 - 0.35 * (self.stage_number - 1))

    def show_message(self, text: str, duration: float = 3.0) -> None:
        self.message = text
        self.message_timer = duration

    def run(self) -> None:
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            self.handle_events()
            self.update(dt)
            self.draw()
            self.present()

        pygame.quit()

    def handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.open_exit_confirm()
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.handle_mouse_click(event.pos)
            elif event.type == pygame.KEYDOWN:
                self.handle_keydown(event)

    def create_window_surface(self) -> pygame.Surface:
        return pygame.display.set_mode(self.maximum_window_size(), pygame.FULLSCREEN)

    def maximum_window_size(self) -> tuple[int, int]:
        desktop_sizes = pygame.display.get_desktop_sizes()
        if desktop_sizes:
            return desktop_sizes[0]

        display_info = pygame.display.Info()
        return max(display_info.current_w, self.window_width), max(display_info.current_h, self.window_height)

    def present(self) -> None:
        _, scaled_width, scaled_height, offset_x, offset_y = self.get_present_metrics()

        if scaled_width == self.window_width and scaled_height == self.window_height:
            frame = self.screen
        else:
            frame = pygame.transform.smoothscale(self.screen, (scaled_width, scaled_height))

        self.window_surface.fill(BACKGROUND)
        self.window_surface.blit(frame, (offset_x, offset_y))
        pygame.display.flip()

    def get_present_metrics(self) -> tuple[float, int, int, int, int]:
        target_width, target_height = self.window_surface.get_size()
        scale = min(target_width / self.window_width, target_height / self.window_height)
        scaled_width = max(1, int(self.window_width * scale))
        scaled_height = max(1, int(self.window_height * scale))
        offset_x = (target_width - scaled_width) // 2
        offset_y = (target_height - scaled_height) // 2
        return scale, scaled_width, scaled_height, offset_x, offset_y

    def window_to_screen(
        self,
        window_position: tuple[int, int],
        *,
        allow_outside: bool = False,
    ) -> tuple[int, int] | None:
        scale, _, _, offset_x, offset_y = self.get_present_metrics()
        local_x = window_position[0] - offset_x
        local_y = window_position[1] - offset_y
        if not allow_outside and (local_x < 0 or local_y < 0):
            return None

        screen_x = math.floor(local_x / scale)
        screen_y = math.floor(local_y / scale)
        if not allow_outside and not pygame.Rect(0, 0, self.window_width, self.window_height).collidepoint((screen_x, screen_y)):
            return None
        return screen_x, screen_y

    def mouse_screen_position(self, *, allow_outside: bool = False) -> tuple[int, int] | None:
        return self.window_to_screen(pygame.mouse.get_pos(), allow_outside=allow_outside)

    def handle_mouse_click(self, window_position: tuple[int, int]) -> None:
        screen_position = self.window_to_screen(window_position)
        if screen_position is None:
            return

        if self.state == "main_menu":
            self.handle_option_click(screen_position, self.main_menu_options, 280, "main")
        elif self.state == "pause_menu":
            self.handle_overlay_option_click(screen_position, self.pause_menu_options, "pause")
        elif self.state == "game_over":
            self.handle_overlay_option_click(screen_position, self.game_over_options, "game_over", footer=f"Final score: {self.score}")
        elif self.state == "how_to_play":
            if self.get_top_button_rect().collidepoint(screen_position):
                self.play_button_click()
                self.state = "main_menu"
        elif self.state == "leaderboard":
            if self.get_top_button_rect().collidepoint(screen_position):
                self.play_button_click()
                self.state = "main_menu"
            elif self.get_secondary_top_button_rect().collidepoint(screen_position):
                self.play_button_click()
                self.refresh_leaderboard()
        elif self.state == "settings":
            self.handle_settings_click(screen_position)
        elif self.state == "playing":
            self.handle_playing_click(screen_position)
        elif self.state == "restart_confirm":
            self.handle_confirm_click(screen_position, "restart")
        elif self.state == "exit_confirm":
            self.handle_confirm_click(screen_position, "exit")
        elif self.state == "name_entry":
            self.handle_name_entry_click(screen_position)

    def handle_option_click(self, screen_position: tuple[int, int], options: list[str], start_y: int, menu_name: str) -> None:
        for index, rect in enumerate(self.get_option_rects(options, start_y)):
            if not rect.collidepoint(screen_position):
                continue
            if menu_name == "main":
                self.main_menu_index = index
                self.activate_main_menu()
            elif menu_name == "pause":
                self.pause_menu_index = index
                self.activate_pause_menu()
            elif menu_name == "game_over":
                self.game_over_index = index
                self.activate_game_over_menu()
            self.play_button_click()
            return

    def handle_overlay_option_click(
        self,
        screen_position: tuple[int, int],
        options: list[str],
        menu_name: str,
        footer: str | None = None,
    ) -> None:
        for index, rect in enumerate(self.get_menu_overlay_option_rects(options, footer=footer)):
            if not rect.collidepoint(screen_position):
                continue
            if menu_name == "pause":
                self.pause_menu_index = index
                self.activate_pause_menu()
            elif menu_name == "game_over":
                self.game_over_index = index
                self.activate_game_over_menu()
            self.play_button_click()
            return

    def handle_playing_click(self, screen_position: tuple[int, int]) -> None:
        if self.get_pause_button_rect().collidepoint(screen_position):
            self.play_button_click()
            self.state = "pause_menu"
            self.pause_menu_index = 0
            return

        if self.get_restart_button_rect().collidepoint(screen_position):
            self.play_button_click()
            self.confirm_return_state = "playing"
            self.state = "restart_confirm"
            self.confirm_index = 1
            return

    def handle_settings_click(self, screen_position: tuple[int, int]) -> None:
        controls = self.get_settings_control_rects()
        if controls["volume_down"].collidepoint(screen_position):
            self.play_button_click()
            self.volume_index = max(0, self.volume_index - 1)
            self.audio.apply_volume(self.volume_steps[self.volume_index])
        elif controls["volume_up"].collidepoint(screen_position):
            self.play_button_click()
            self.volume_index = min(len(self.volume_steps) - 1, self.volume_index + 1)
            self.audio.apply_volume(self.volume_steps[self.volume_index])
        elif controls["back"].collidepoint(screen_position):
            self.play_button_click()
            self.state = self.settings_return_state

    def handle_confirm_click(self, screen_position: tuple[int, int], confirm_type: str) -> None:
        yes_rect, no_rect = self.get_confirm_button_rects()
        if yes_rect.collidepoint(screen_position):
            self.play_button_click()
            self.confirm_index = 0
            if confirm_type == "restart":
                self.start_new_run()
            else:
                self.running = False
        elif no_rect.collidepoint(screen_position):
            self.play_button_click()
            self.confirm_index = 1
            self.state = self.confirm_return_state

    def handle_name_entry_click(self, screen_position: tuple[int, int]) -> None:
        for label, rect, action in self.get_name_entry_action_buttons():
            if not rect.collidepoint(screen_position):
                continue

            self.play_button_click()

            if action == "save":
                self.submit_high_score()
            elif action == "skip":
                self.state = "game_over"
            return

    def queue_direction_from_point(self, screen_position: tuple[int, int]) -> None:
        pacman_center = self.world_center(self.pacman.position)
        if not self.is_centered(self.pacman.position):
            self.pacman.queued_direction = self.direction_toward_point(screen_position, pacman_center)
            return

        current_cell = self.rounded_cell(self.pacman.position)
        target_cell = self.screen_to_cell(screen_position)
        if target_cell is None:
            self.pacman.queued_direction = self.direction_toward_point(screen_position, pacman_center)
            return

        if target_cell == current_cell:
            return

        if target_cell[1] == current_cell[1] and self.path_clear_between(current_cell, target_cell):
            self.pacman.queued_direction = (DIR_RIGHT if target_cell[0] > current_cell[0] else DIR_LEFT).copy()
            return

        if target_cell[0] == current_cell[0] and self.path_clear_between(current_cell, target_cell):
            self.pacman.queued_direction = (DIR_DOWN if target_cell[1] > current_cell[1] else DIR_UP).copy()
            return

        best_direction = self.shortest_direction_to_target(current_cell, target_cell)
        if best_direction is not None:
            self.pacman.queued_direction = best_direction.copy()
            return

        available = self.available_directions(current_cell)
        if not available:
            return

        fallback_direction = min(
            available,
            key=lambda direction: self.distance_cells(
                self.next_cell_in_direction(current_cell, direction),
                target_cell,
            ),
        )
        self.pacman.queued_direction = fallback_direction.copy()

    @staticmethod
    def direction_toward_point(
        screen_position: tuple[int, int],
        origin: tuple[int, int],
    ) -> pygame.Vector2:
        delta_x = screen_position[0] - origin[0]
        delta_y = screen_position[1] - origin[1]
        if delta_x == 0 and delta_y == 0:
            return STOP.copy()
        if abs(delta_x) >= abs(delta_y):
            return (DIR_RIGHT if delta_x >= 0 else DIR_LEFT).copy()
        return (DIR_DOWN if delta_y >= 0 else DIR_UP).copy()

    def screen_to_cell(self, screen_position: tuple[int, int]) -> tuple[int, int] | None:
        if not self.get_maze_rect().collidepoint(screen_position):
            return None

        cell_x = (screen_position[0] - 24) // GRID_SIZE
        cell_y = (screen_position[1] - TOP_MARGIN) // GRID_SIZE
        cell = (int(cell_x), int(cell_y))
        if cell in self.stage_map.walls or cell in self.stage_map.gates or cell in self.stage_map.house_cells:
            return None
        return cell

    def path_clear_between(self, start_cell: tuple[int, int], end_cell: tuple[int, int]) -> bool:
        if start_cell[0] == end_cell[0]:
            step = 1 if end_cell[1] > start_cell[1] else -1
            for y in range(start_cell[1] + step, end_cell[1], step):
                if not self.is_walkable_cell((start_cell[0], y)):
                    return False
            return True

        if start_cell[1] == end_cell[1]:
            step = 1 if end_cell[0] > start_cell[0] else -1
            for x in range(start_cell[0] + step, end_cell[0], step):
                if not self.is_walkable_cell((x, start_cell[1])):
                    return False
            return True

        return False

    def play_button_click(self) -> None:
        self.audio.play("menu")

    def next_cell_in_direction(self, cell: tuple[int, int], direction: pygame.Vector2) -> tuple[int, int]:
        next_cell = (cell[0] + int(direction.x), cell[1] + int(direction.y))
        return self.stage_map.portals.get(next_cell, next_cell)

    def is_walkable_cell(self, cell: tuple[int, int], *, is_ghost: bool = False) -> bool:
        if cell[0] < 0 or cell[1] < 0 or cell[0] >= self.stage_map.width or cell[1] >= self.stage_map.height:
            return False
        if cell in self.stage_map.walls:
            return False
        if cell in self.stage_map.gates and not is_ghost:
            return False
        if cell in self.stage_map.house_cells and not is_ghost:
            return False
        return True

    def shortest_direction_to_target(
        self,
        start_cell: tuple[int, int],
        target_cell: tuple[int, int],
        *,
        is_ghost: bool = False,
        blocked_cells: set[tuple[int, int]] | None = None,
    ) -> pygame.Vector2 | None:
        if start_cell == target_cell:
            return STOP.copy()

        frontier: deque[tuple[tuple[int, int], pygame.Vector2]] = deque()
        visited = {start_cell}

        for direction in self.available_directions(start_cell, is_ghost=is_ghost, blocked_cells=blocked_cells):
            next_cell = self.next_cell_in_direction(start_cell, direction)
            if next_cell in visited or not self.is_walkable_cell(next_cell, is_ghost=is_ghost):
                continue
            visited.add(next_cell)
            frontier.append((next_cell, direction.copy()))

        while frontier:
            cell, first_direction = frontier.popleft()
            if cell == target_cell:
                return first_direction

            for direction in self.available_directions(cell, is_ghost=is_ghost, blocked_cells=blocked_cells):
                next_cell = self.next_cell_in_direction(cell, direction)
                if next_cell in visited or not self.is_walkable_cell(next_cell, is_ghost=is_ghost):
                    continue
                visited.add(next_cell)
                frontier.append((next_cell, first_direction))

        return None

    def open_exit_confirm(self) -> None:
        self.confirm_index = 1
        self.confirm_return_state = self.state
        self.state = "exit_confirm"

    def handle_keydown(self, event: pygame.event.Event) -> None:
        if self.state == "playing":
            self.handle_playing_key(event.key)
        elif self.state == "main_menu":
            self.handle_menu_key(event.key, self.main_menu_options, "main")
        elif self.state == "pause_menu":
            self.handle_menu_key(event.key, self.pause_menu_options, "pause")
        elif self.state == "how_to_play":
            if event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_BACKSPACE):
                self.state = "main_menu"
        elif self.state == "leaderboard":
            if event.key == pygame.K_r:
                self.refresh_leaderboard()
            elif event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_BACKSPACE):
                self.state = "main_menu"
        elif self.state == "settings":
            self.handle_settings_key(event.key)
        elif self.state == "restart_confirm":
            self.handle_confirm_key(event.key, "restart")
        elif self.state == "exit_confirm":
            self.handle_confirm_key(event.key, "exit")
        elif self.state == "game_over":
            self.handle_menu_key(event.key, self.game_over_options, "game_over")
        elif self.state == "name_entry":
            self.handle_name_entry_key(event)

    def handle_playing_key(self, key: int) -> None:
        action = self.action_for_key(key)
        if action in ACTION_TO_DIRECTION:
            self.pacman.queued_direction = ACTION_TO_DIRECTION[action].copy()
        elif action == "pause" or key == pygame.K_ESCAPE:
            self.state = "pause_menu"
            self.pause_menu_index = 0
        elif key == pygame.K_r:
            self.confirm_return_state = "playing"
            self.state = "restart_confirm"
            self.confirm_index = 1

    def action_for_key(self, key: int) -> str | None:
        for action_name, bound_key in self.key_bindings.items():
            if key == bound_key:
                return action_name
        return None

    def handle_menu_key(self, key: int, options: list[str], menu_name: str) -> None:
        if key == pygame.K_UP:
            self.audio.play("menu")
            if menu_name == "main":
                self.main_menu_index = (self.main_menu_index - 1) % len(options)
            elif menu_name == "pause":
                self.pause_menu_index = (self.pause_menu_index - 1) % len(options)
            elif menu_name == "game_over":
                self.game_over_index = (self.game_over_index - 1) % len(options)
        elif key == pygame.K_DOWN:
            self.audio.play("menu")
            if menu_name == "main":
                self.main_menu_index = (self.main_menu_index + 1) % len(options)
            elif menu_name == "pause":
                self.pause_menu_index = (self.pause_menu_index + 1) % len(options)
            elif menu_name == "game_over":
                self.game_over_index = (self.game_over_index + 1) % len(options)
        elif key in (pygame.K_RETURN, pygame.K_SPACE):
            if menu_name == "main":
                self.activate_main_menu()
            elif menu_name == "pause":
                self.activate_pause_menu()
            elif menu_name == "game_over":
                self.activate_game_over_menu()
        elif key == pygame.K_ESCAPE:
            if menu_name == "pause":
                self.state = "playing"
            elif menu_name == "game_over":
                self.state = "main_menu"

    def activate_main_menu(self) -> None:
        option = self.main_menu_options[self.main_menu_index]
        if option == "Play Game":
            self.start_new_run()
        elif option == "How to Play":
            self.state = "how_to_play"
        elif option == "Leaderboard":
            self.refresh_leaderboard()
            self.state = "leaderboard"
        elif option == "Settings":
            self.settings_return_state = "main_menu"
            self.state = "settings"
        elif option == "Exit Game":
            self.open_exit_confirm()

    def activate_pause_menu(self) -> None:
        option = self.pause_menu_options[self.pause_menu_index]
        if option == "Resume":
            self.state = "playing"
        elif option == "Settings":
            self.settings_return_state = "pause_menu"
            self.state = "settings"
        elif option == "Restart Run":
            self.confirm_return_state = "pause_menu"
            self.state = "restart_confirm"
            self.confirm_index = 1
        elif option == "Main Menu":
            self.state = "main_menu"

    def activate_game_over_menu(self) -> None:
        option = self.game_over_options[self.game_over_index]
        if option == "Play Again":
            self.start_new_run()
        elif option == "Main Menu":
            self.state = "main_menu"

    def handle_settings_key(self, key: int) -> None:
        setting_count = 2
        if key == pygame.K_UP:
            self.settings_index = (self.settings_index - 1) % setting_count
        elif key == pygame.K_DOWN:
            self.settings_index = (self.settings_index + 1) % setting_count
        elif key in (pygame.K_LEFT, pygame.K_RIGHT):
            self.adjust_setting(key == pygame.K_RIGHT)
        elif key in (pygame.K_RETURN, pygame.K_SPACE):
            if self.settings_index == 1:
                self.state = self.settings_return_state
        elif key == pygame.K_ESCAPE:
            self.state = self.settings_return_state

    def adjust_setting(self, increase: bool) -> None:
        if self.settings_index == 0:
            self.volume_index = max(0, min(len(self.volume_steps) - 1, self.volume_index + (1 if increase else -1)))
            self.audio.apply_volume(self.volume_steps[self.volume_index])

    def handle_confirm_key(self, key: int, confirm_type: str) -> None:
        if key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN):
            self.confirm_index = 1 - self.confirm_index
        elif key in (pygame.K_RETURN, pygame.K_SPACE):
            if self.confirm_options[self.confirm_index] == "Yes":
                if confirm_type == "restart":
                    self.start_new_run()
                elif confirm_type == "exit":
                    self.running = False
            else:
                self.state = self.confirm_return_state
        elif key == pygame.K_ESCAPE:
            self.state = self.confirm_return_state

    def handle_name_entry_key(self, event: pygame.event.Event) -> None:
        if event.key == pygame.K_RETURN:
            self.submit_high_score()
        elif event.key == pygame.K_BACKSPACE:
            self.name_entry_value = self.name_entry_value[:-1]
        elif event.key == pygame.K_ESCAPE:
            self.state = "game_over"
        elif event.unicode and event.unicode.isprintable() and len(self.name_entry_value) < 12:
            self.name_entry_value += event.unicode

    def submit_high_score(self) -> None:
        player_name = self.name_entry_value.strip()
        if not player_name:
            self.show_message("Choose a name before saving.")
            return

        try:
            self.leaderboard.submit_score(player_name, self.score, self.stage_number)
        except (LeaderboardConfigError, LeaderboardServiceError):
            self.show_message(self.leaderboard.last_error or "Could not save leaderboard score.", 4.0)
            self.state = "game_over"
            return

        self.refresh_leaderboard()
        self.show_message("Score submitted to the leaderboard.")
        self.state = "leaderboard"

    def update(self, dt: float) -> None:
        if self.message_timer > 0:
            self.message_timer = max(0.0, self.message_timer - dt)
            if self.message_timer == 0:
                self.message = ""

        if self.state != "playing":
            return

        self.audio.start_music()
        self.pacman.speed = self.pacman_speed()
        self.chase_timer += dt

        if self.round_timer > 0:
            self.round_timer = max(0.0, self.round_timer - dt)
            return

        if self.stage_transition_timer > 0:
            self.stage_transition_timer = max(0.0, self.stage_transition_timer - dt)
            if self.stage_transition_timer <= 0 and self.pending_stage_number is not None:
                self.stage_number = self.pending_stage_number
                self.pending_stage_number = None
                self.load_stage()
                self.show_message(f"Stage {self.stage_number} begins! Fruit: {self.fruit_name.title()}", 3.0)
            return

        if self.vulnerability_timer > 0:
            self.vulnerability_timer = max(0.0, self.vulnerability_timer - dt)
            if self.vulnerability_timer == 0:
                for ghost in self.ghosts:
                    if ghost.mode == "vulnerable":
                        ghost.mode = "normal"

        if self.pacman_teleport_timer > 0:
            self.pacman_teleport_timer = max(0.0, self.pacman_teleport_timer - dt)
            if self.pacman_teleport_timer == 0:
                self.pacman_teleport_path = None

        self.update_effects(dt)

        self.update_cursor_direction()
        self.update_entity(self.pacman, dt)
        self.consume_current_cell()
        self.collect_fruit_if_touched()
        self.update_fruit(dt)
        self.collect_fruit_if_touched()

        for ghost in self.ghosts:
            if self.chase_timer < ghost.release_delay:
                continue
            blocked_cells = self.occupied_ghost_cells(exclude=ghost)
            previous_cell = self.rounded_cell(ghost.position)
            ghost.speed = self.ghost_speed() * (0.94 if ghost.mode == "vulnerable" else 1.1)
            if ghost.mode in {"respawning", "reviving"}:
                ghost.speed = self.ghost_speed() * 1.18
            self.choose_ghost_direction(ghost, blocked_cells=blocked_cells)
            self.update_entity(ghost, dt, blocked_cells=blocked_cells)
            current_cell = self.rounded_cell(ghost.position)
            if current_cell in blocked_cells:
                ghost.position = pygame.Vector2(previous_cell)
                ghost.direction = STOP.copy()
                ghost.queued_direction = STOP.copy()
                current_cell = previous_cell
            if ghost.mode == "respawning" and current_cell == ghost.start_cell:
                ghost.position = pygame.Vector2(ghost.start_cell)
                ghost.direction = STOP.copy()
                ghost.queued_direction = STOP.copy()
                ghost.mode = "reviving"
            elif ghost.mode == "reviving" and current_cell == self.stage_map.ghost_house_exit:
                ghost.mode = "normal"

        self.handle_collisions()
        self.check_stage_clear()

    @staticmethod
    def rounded_cell(position: pygame.Vector2) -> tuple[int, int]:
        return int(round(position.x)), int(round(position.y))

    @staticmethod
    def is_centered(position: pygame.Vector2, *, tolerance: float = 0.08) -> bool:
        return abs(position.x - round(position.x)) < tolerance and abs(position.y - round(position.y)) < tolerance

    def occupied_ghost_cells(self, *, exclude: Ghost | None = None) -> set[tuple[int, int]]:
        return {self.rounded_cell(ghost.position) for ghost in self.ghosts if ghost is not exclude}

    def can_move(
        self,
        cell: tuple[int, int],
        direction: pygame.Vector2,
        *,
        is_ghost: bool = False,
        blocked_cells: set[tuple[int, int]] | None = None,
    ) -> bool:
        if direction.length_squared() == 0:
            return True
        next_cell = self.next_cell_in_direction(cell, direction)
        if next_cell[0] < 0 or next_cell[1] < 0 or next_cell[0] >= self.stage_map.width or next_cell[1] >= self.stage_map.height:
            return False
        if next_cell in self.stage_map.walls:
            return False
        if next_cell in self.stage_map.gates and not is_ghost:
            return False
        if next_cell in self.stage_map.house_cells and not is_ghost:
            return False
        if is_ghost and blocked_cells and next_cell in blocked_cells:
            return False
        return True

    def available_directions(
        self,
        cell: tuple[int, int],
        *,
        is_ghost: bool = False,
        blocked_cells: set[tuple[int, int]] | None = None,
    ) -> list[pygame.Vector2]:
        return [
            direction
            for direction in DIRECTIONS
            if self.can_move(cell, direction, is_ghost=is_ghost, blocked_cells=blocked_cells)
        ]

    def update_entity(
        self,
        entity: MovingEntity,
        dt: float,
            *,
        blocked_cells: set[tuple[int, int]] | None = None,
    ) -> None:
        is_ghost = isinstance(entity, Ghost)
        center_tolerance = FRUIT_CENTER_TOLERANCE if isinstance(entity, Fruit) else 0.08
        if self.is_centered(entity.position, tolerance=center_tolerance):
            entity.position = pygame.Vector2(round(entity.position.x), round(entity.position.y))
            self.apply_portal(entity)
            current_cell = self.rounded_cell(entity.position)
            if self.can_move(current_cell, entity.queued_direction, is_ghost=is_ghost, blocked_cells=blocked_cells):
                entity.direction = entity.queued_direction.copy()
            elif not self.can_move(current_cell, entity.direction, is_ghost=is_ghost, blocked_cells=blocked_cells):
                entity.direction = STOP.copy()

        if entity.direction.length_squared() == 0:
            return

        entity.position += entity.direction * entity.speed * dt

        if self.is_centered(entity.position, tolerance=center_tolerance):
            entity.position = pygame.Vector2(round(entity.position.x), round(entity.position.y))
            self.apply_portal(entity)

    def apply_portal(self, entity: MovingEntity) -> None:
        current_cell = self.rounded_cell(entity.position)
        exit_cell = self.stage_map.portals.get(current_cell)
        if exit_cell is None or not self.should_wrap_through_portal(current_cell, entity.direction):
            return
        if entity is self.pacman:
            self.trigger_teleport_effect(current_cell, exit_cell)
        entity.position = pygame.Vector2(exit_cell)

    def should_wrap_through_portal(self, cell: tuple[int, int], direction: pygame.Vector2) -> bool:
        if direction.length_squared() == 0:
            return False
        if cell[0] == 0 and direction.x < 0:
            return True
        if cell[0] == self.stage_map.width - 1 and direction.x > 0:
            return True
        if cell[1] == 0 and direction.y < 0:
            return True
        if cell[1] == self.stage_map.height - 1 and direction.y > 0:
            return True
        return False

    def consume_current_cell(self) -> None:
        current_cell = self.rounded_cell(self.pacman.position)
        if not self.is_centered(self.pacman.position):
            return

        if current_cell in self.stage_map.dots:
            self.stage_map.dots.remove(current_cell)
            self.score += 1
            self.dot_eat_count += 1
            self.spawn_dot_effect(current_cell)
            self.audio.play("dot")
        elif current_cell in self.stage_map.pellets:
            self.stage_map.pellets.remove(current_cell)
            self.score += 10
            self.dot_eat_count += 1
            self.spawn_pellet_effect(current_cell)
            self.vulnerability_timer = self.vulnerability_duration()
            for ghost in self.ghosts:
                if ghost.mode not in {"respawning", "reviving"}:
                    ghost.mode = "vulnerable"
            self.audio.play("pellet")

        if not self.fruit_spawned and self.dot_eat_count >= 50:
            self.spawn_fruit(avoid_cell=current_cell)

        self.high_score = max(self.high_score, self.score)

    def fruit_spawn_candidates(self, *, avoid_cell: tuple[int, int]) -> list[tuple[int, int]]:
        occupied_ghost_cells = {self.rounded_cell(ghost.position) for ghost in self.ghosts}
        return [
            cell
            for cell in self.stage_map.open_cells
            if (
                cell not in self.stage_map.gates
                and cell not in self.stage_map.house_cells
                and cell not in self.stage_map.ghost_starts
                and cell != self.stage_map.pacman_start
                and cell not in self.stage_map.dots
                and cell not in self.stage_map.pellets
                and cell not in self.stage_map.portals
                and cell != avoid_cell
                and cell not in occupied_ghost_cells
                and bool(self.available_directions(cell))
            )
        ]

    def spawn_fruit(self, *, avoid_cell: tuple[int, int]) -> None:
        available_cells = self.fruit_spawn_candidates(avoid_cell=avoid_cell)
        if not available_cells:
            return

        spawn_cell = self.random.choice(available_cells)
        self.fruit = Fruit(
            position=pygame.Vector2(spawn_cell),
            start_cell=spawn_cell,
            direction=STOP.copy(),
            queued_direction=STOP.copy(),
            color=FRUIT_COLORS[self.fruit_name],
            speed=self.fruit_speed(),
            name=self.fruit_name,
        )
        self.fruit_spawned = True
        self.fruit_time_left = FRUIT_DESPAWN_SECONDS
        self.show_message(f"A {self.fruit_name.title()} appeared and started weaving around!", 2.2)

    def update_fruit(self, dt: float) -> None:
        if self.fruit is None or self.fruit_eaten:
            return

        if self.fruit_time_left is not None:
            self.fruit_time_left = max(0.0, self.fruit_time_left - dt)
            if self.fruit_time_left == 0:
                fruit_name = self.fruit.name
                self.fruit = None
                self.fruit_time_left = None
                self.show_message(f"The {fruit_name.title()} disappeared.", 1.8)
                return

        self.fruit.speed = self.fruit_speed()
        self.choose_fruit_direction(self.fruit)
        self.update_entity(self.fruit, dt)

    def choose_fruit_direction(self, fruit: Fruit) -> None:
        if not self.is_centered(fruit.position, tolerance=FRUIT_CENTER_TOLERANCE):
            return

        current_cell = self.rounded_cell(fruit.position)
        available = self.available_directions(current_cell)
        if not available:
            fruit.direction = STOP.copy()
            fruit.queued_direction = STOP.copy()
            return

        if len(available) == 1:
            fruit.queued_direction = available[0].copy()
            return

        pacman_cell = self.rounded_cell(self.pacman.position)
        current_distance = self.distance_cells(current_cell, pacman_cell)
        opposite = -fruit.direction
        options = [direction for direction in available if direction != opposite] or available

        blocked_cells = {pacman_cell}
        if self.pacman.direction.length_squared() > 0:
            blocked_cells.add(self.next_cell_in_direction(pacman_cell, self.pacman.direction))

        safe_options = [
            direction
            for direction in options
            if self.next_cell_in_direction(current_cell, direction) not in blocked_cells
        ]
        if not safe_options:
            safe_options = options

        best_neutral_options = sorted(
            safe_options,
            key=lambda direction: abs(
                self.distance_cells(self.next_cell_in_direction(current_cell, direction), pacman_cell) - current_distance
            ),
        )
        min_delta = abs(self.distance_cells(self.next_cell_in_direction(current_cell, best_neutral_options[0]), pacman_cell) - current_distance)
        tied_options = [
            direction
            for direction in best_neutral_options
            if abs(self.distance_cells(self.next_cell_in_direction(current_cell, direction), pacman_cell) - current_distance) == min_delta
        ]
        if fruit.direction.length_squared() > 0 and fruit.direction in tied_options and self.random.random() < 0.55:
            fruit.queued_direction = fruit.direction.copy()
            return
        fruit.queued_direction = self.random.choice(tied_options).copy()

    def collect_fruit_if_touched(self) -> None:
        if self.fruit is None or self.fruit_eaten:
            return

        if self.pacman.position.distance_to(self.fruit.position) > 0.58:
            return

        fruit_name = self.fruit.name
        self.spawn_fruit_eaten_effect(self.fruit.position, fruit_name)
        self.score += FRUIT_SCORES[fruit_name]
        self.fruit_eaten = True
        self.fruit = None
        self.fruit_time_left = None
        self.audio.play("fruit")
        self.show_message(f"{fruit_name.title()} collected for {FRUIT_SCORES[fruit_name]} points!", 2.4)
        self.high_score = max(self.high_score, self.score)

    def update_effects(self, dt: float) -> None:
        active_particles: list[Particle] = []
        for particle in self.effect_particles:
            particle.age += dt
            if particle.age >= particle.duration:
                continue
            particle.position += particle.velocity * dt
            particle.velocity *= 0.9
            active_particles.append(particle)
        self.effect_particles = active_particles

        active_rings: list[RingEffect] = []
        for ring in self.effect_rings:
            ring.age += dt
            if ring.age >= ring.duration:
                continue
            active_rings.append(ring)
        self.effect_rings = active_rings

    def spawn_particle_burst(
        self,
        center: tuple[int, int],
        color: tuple[int, int, int],
        *,
        count: int,
        min_speed: float,
        max_speed: float,
        size: float,
        duration: float,
    ) -> None:
        center_vector = pygame.Vector2(center)
        for _ in range(count):
            angle = self.random.random() * math.tau
            speed = self.random.uniform(min_speed, max_speed)
            velocity = pygame.Vector2(math.cos(angle), math.sin(angle)) * speed
            self.effect_particles.append(
                Particle(
                    position=center_vector.copy(),
                    velocity=velocity,
                    color=color,
                    size=size,
                    age=0.0,
                    duration=duration,
                )
            )

    def trigger_teleport_effect(self, start_cell: tuple[int, int], end_cell: tuple[int, int]) -> None:
        start_center = self.cell_center(start_cell)
        end_center = self.cell_center(end_cell)
        self.pacman_teleport_path = (start_center, end_center)
        self.pacman_teleport_timer = 0.26
        self.effect_rings.append(
            RingEffect(pygame.Vector2(start_center), PORTAL_COLOR, 8.0, 28.0, 0.0, 0.26, 2)
        )
        self.effect_rings.append(
            RingEffect(pygame.Vector2(end_center), PORTAL_ACCENT, 10.0, 30.0, 0.0, 0.26, 2)
        )
        self.spawn_particle_burst(
            end_center,
            PORTAL_ACCENT,
            count=10,
            min_speed=55.0,
            max_speed=130.0,
            size=3.4,
            duration=0.28,
        )

    def spawn_dot_effect(self, cell: tuple[int, int]) -> None:
        self.spawn_particle_burst(
            self.cell_center(cell),
            DOT,
            count=5,
            min_speed=26.0,
            max_speed=58.0,
            size=2.4,
            duration=0.18,
        )

    def spawn_pellet_effect(self, cell: tuple[int, int]) -> None:
        center = self.cell_center(cell)
        self.effect_rings.append(
            RingEffect(pygame.Vector2(center), POWER_PELLET, 7.0, 30.0, 0.0, 0.28, 2)
        )
        self.spawn_particle_burst(
            center,
            POWER_PELLET,
            count=11,
            min_speed=45.0,
            max_speed=120.0,
            size=3.3,
            duration=0.26,
        )

    def spawn_fruit_eaten_effect(self, position: pygame.Vector2, fruit_name: str) -> None:
        center = self.world_center(position)
        fruit_color = FRUIT_COLORS[fruit_name]
        self.effect_rings.append(
            RingEffect(pygame.Vector2(center), fruit_color, 9.0, 31.0, 0.0, 0.3, 3)
        )
        self.effect_rings.append(
            RingEffect(pygame.Vector2(center), HIGHLIGHT, 6.0, 24.0, 0.0, 0.24, 2)
        )
        self.spawn_particle_burst(
            center,
            fruit_color,
            count=12,
            min_speed=45.0,
            max_speed=125.0,
            size=3.6,
            duration=0.3,
        )

    def spawn_ghost_eaten_effect(self, position: pygame.Vector2) -> None:
        center = self.world_center(position)
        self.effect_rings.append(
            RingEffect(pygame.Vector2(center), (210, 230, 255), 10.0, 34.0, 0.0, 0.34, 3)
        )
        self.spawn_particle_burst(
            center,
            (220, 220, 250),
            count=14,
            min_speed=52.0,
            max_speed=145.0,
            size=3.8,
            duration=0.34,
        )

    def ghost_target_cell(self, ghost: Ghost) -> tuple[int, int]:
        pacman_cell = self.rounded_cell(self.pacman.position)
        if ghost.mode == "respawning":
            return ghost.start_cell
        if ghost.mode == "reviving":
            return self.stage_map.ghost_house_exit
        if ghost.mode == "vulnerable":
            return ghost.home_corner

        projected = (
            max(1, min(self.stage_map.width - 2, pacman_cell[0] + int(self.pacman.direction.x * 3))),
            max(1, min(self.stage_map.height - 2, pacman_cell[1] + int(self.pacman.direction.y * 3))),
        )

        if ghost.name.endswith("1"):
            return pacman_cell
        if ghost.name.endswith("2"):
            return projected
        if ghost.name.endswith("3"):
            return pacman_cell[0], ghost.home_corner[1]
        if self.distance_cells(self.rounded_cell(ghost.position), pacman_cell) > 6:
            return pacman_cell
        return ghost.home_corner

    def choose_ghost_direction(
        self,
        ghost: Ghost,
        *,
        blocked_cells: set[tuple[int, int]] | None = None,
    ) -> None:
        if not self.is_centered(ghost.position):
            return

        current_cell = self.rounded_cell(ghost.position)
        if ghost.mode in {"respawning", "reviving"}:
            target_cell = ghost.start_cell if ghost.mode == "respawning" else self.stage_map.ghost_house_exit
            best_direction = self.shortest_direction_to_target(
                current_cell,
                target_cell,
                is_ghost=True,
                blocked_cells=blocked_cells,
            )
            ghost.queued_direction = STOP.copy() if best_direction is None else best_direction.copy()
            return

        available = self.available_directions(current_cell, is_ghost=True, blocked_cells=blocked_cells)
        if len(available) > 1:
            opposite = -ghost.direction
            available = [direction for direction in available if direction != opposite] or available

        if not available:
            ghost.direction = STOP.copy()
            ghost.queued_direction = STOP.copy()
            return

        target = self.ghost_target_cell(ghost)
        chase_phase = self.chase_timer % 12.0 < 8.0

        if not chase_phase and ghost.mode == "normal":
            target = ghost.home_corner

        ranked = sorted(
            available,
            key=lambda direction: self.distance_cells(
                self.next_cell_in_direction(current_cell, direction),
                target,
            ),
            reverse=ghost.mode == "vulnerable",
        )

        aggression = self.ghost_aggression()
        if len(ranked) > 1 and ghost.mode == "normal" and self.random.random() > aggression:
            ghost.queued_direction = ranked[1].copy()
        else:
            ghost.queued_direction = ranked[0].copy()

    @staticmethod
    def distance_cells(first: tuple[int, int], second: tuple[int, int]) -> float:
        return abs(first[0] - second[0]) + abs(first[1] - second[1])

    def handle_collisions(self) -> None:
        pacman_position = self.pacman.position
        for ghost in self.ghosts:
            if ghost.mode in {"respawning", "reviving"}:
                continue

            if pacman_position.distance_to(ghost.position) > 0.55:
                continue

            if ghost.mode == "vulnerable":
                self.spawn_ghost_eaten_effect(ghost.position)
                ghost.position = pygame.Vector2(self.rounded_cell(ghost.position))
                ghost.mode = "respawning"
                ghost.direction = STOP.copy()
                ghost.queued_direction = STOP.copy()
                self.score += 50
                self.audio.play("ghost")
                self.show_message("Ghost eaten for 50 points!", 1.8)
                self.high_score = max(self.high_score, self.score)
                continue

            self.lose_life()
            break

    def lose_life(self) -> None:
        self.lives -= 1
        self.audio.play("lose_life")
        if self.lives <= 0:
            self.finish_run()
            return

        self.pacman.reset()
        for ghost in self.ghosts:
            ghost.reset()
            ghost.mode = "normal"
        self.vulnerability_timer = 0.0
        self.effect_particles.clear()
        self.effect_rings.clear()
        self.pacman_teleport_timer = 0.0
        self.pacman_teleport_path = None
        self.round_timer = 1.8
        self.chase_timer = 0.0
        self.show_message("Life lost! Get ready...", 2.0)

    def finish_run(self) -> None:
        self.refresh_leaderboard()
        if self.leaderboard.qualifies(self.score, self.leaderboard_entries) and self.leaderboard_error is None:
            self.state = "name_entry"
            self.name_entry_value = ""
        else:
            if self.leaderboard_error:
                self.show_message(self.leaderboard_error, 5.0)
            self.state = "game_over"
            self.game_over_index = 0

    def check_stage_clear(self) -> None:
        if self.stage_map.dots or self.stage_map.pellets or self.pending_stage_number is not None:
            return

        self.pending_stage_number = self.stage_number + 1
        self.stage_transition_timer = 1.5
        self.show_message("Stage cleared!", 1.8)

    def update_cursor_direction(self) -> None:
        mouse_position = self.mouse_screen_position(allow_outside=True)
        if mouse_position is None:
            return
        self.queue_direction_from_point(mouse_position)

    def get_maze_rect(self) -> pygame.Rect:
        return pygame.Rect(24, TOP_MARGIN, self.stage_map.width * GRID_SIZE, self.stage_map.height * GRID_SIZE)

    def get_side_panel_rect(self) -> pygame.Rect:
        panel_x = 48 + self.stage_map.width * GRID_SIZE
        return pygame.Rect(panel_x, TOP_MARGIN, SIDE_PANEL - 20, self.stage_map.height * GRID_SIZE)

    def get_option_rects(
        self,
        options: list[str],
        start_y: int,
        center_x: int | None = None,
        width: int = 360,
        height: int = 42,
        gap: int = 48,
    ) -> list[pygame.Rect]:
        if center_x is None:
            center_x = self.window_width // 2

        return [
            pygame.Rect(center_x - width // 2, start_y + index * gap, width, height)
            for index, _ in enumerate(options)
        ]

    def get_top_button_rect(self) -> pygame.Rect:
        return pygame.Rect(self.window_width - 220, 110, 140, 40)

    def get_secondary_top_button_rect(self) -> pygame.Rect:
        return pygame.Rect(self.window_width - 380, 110, 140, 40)

    def get_pause_button_rect(self) -> pygame.Rect:
        panel = self.get_side_panel_rect()
        return pygame.Rect(panel.x + 18, panel.y + 246, panel.width - 36, 42)

    def get_restart_button_rect(self) -> pygame.Rect:
        panel = self.get_side_panel_rect()
        return pygame.Rect(panel.x + 18, panel.y + 292, panel.width - 36, 42)

    @staticmethod
    def get_settings_control_rects() -> dict[str, pygame.Rect]:
        volume_y = 242
        return {
            "volume_down": pygame.Rect(380, volume_y, 48, 40),
            "volume_up": pygame.Rect(610, volume_y, 48, 40),
            "back": pygame.Rect(72, 392, 220, 46),
        }

    def get_menu_overlay_rect(self, options: list[str], footer: str | None = None) -> pygame.Rect:
        overlay_width = 460
        overlay_height = max(280, 120 + len(options) * 54 + (40 if footer else 0))
        return pygame.Rect(
            self.window_width // 2 - overlay_width // 2,
            self.window_height // 2 - overlay_height // 2,
            overlay_width,
            overlay_height,
        )

    def get_menu_overlay_option_rects(self, options: list[str], footer: str | None = None) -> list[pygame.Rect]:
        rect = self.get_menu_overlay_rect(options, footer=footer)
        return self.get_option_rects(options, rect.y + 92, center_x=rect.centerx, width=rect.width - 88)

    def get_confirm_button_rects(self) -> tuple[pygame.Rect, pygame.Rect]:
        rect = pygame.Rect(self.window_width // 2 - 180, 210, 360, 180)
        return (
            pygame.Rect(rect.centerx - 106, rect.y + 88, 90, 42),
            pygame.Rect(rect.centerx + 16, rect.y + 88, 90, 42),
        )

    def get_name_entry_rect(self) -> pygame.Rect:
        return pygame.Rect(self.window_width // 2 - 280, 150, 560, 260)

    def get_name_entry_action_buttons(self) -> list[tuple[str, pygame.Rect, str]]:
        rect = self.get_name_entry_rect()
        button_y = rect.bottom - 60
        return [
            ("Save", pygame.Rect(rect.centerx - 118, button_y, 100, 42), "save"),
            ("Skip", pygame.Rect(rect.centerx + 18, button_y, 100, 42), "skip"),
        ]

    def draw(self) -> None:
        self.screen.fill(BACKGROUND)
        self.draw_header()

        if self.state in {"playing", "pause_menu", "restart_confirm"}:
            self.draw_maze()
            self.draw_side_panel()
            if self.state == "playing":
                if self.round_timer > 0:
                    self.draw_center_overlay("Ready!")
                elif self.stage_transition_timer > 0:
                    self.draw_center_overlay("Stage Clear!")
            if self.state == "pause_menu":
                self.draw_menu_overlay("Paused", self.pause_menu_options, self.pause_menu_index)
            elif self.state == "restart_confirm":
                self.draw_confirm_overlay("Restart this run?")
        elif self.state == "main_menu":
            self.draw_main_menu()
        elif self.state == "how_to_play":
            self.draw_how_to_play()
        elif self.state == "leaderboard":
            self.draw_leaderboard()
        elif self.state == "settings":
            self.draw_settings()
        elif self.state == "game_over":
            self.draw_maze()
            self.draw_side_panel()
            self.draw_menu_overlay("Game Over", self.game_over_options, self.game_over_index, footer=f"Final score: {self.score}")
        elif self.state == "name_entry":
            self.draw_maze()
            self.draw_side_panel()
            self.draw_name_entry()
        elif self.state == "exit_confirm":
            if self.confirm_return_state == "main_menu":
                self.draw_main_menu()
            elif self.confirm_return_state == "how_to_play":
                self.draw_how_to_play()
            elif self.confirm_return_state == "leaderboard":
                self.draw_leaderboard()
            elif self.confirm_return_state == "settings":
                self.draw_settings()
            elif self.confirm_return_state == "game_over":
                self.draw_maze()
                self.draw_side_panel()
                self.draw_menu_overlay("Game Over", self.game_over_options, self.game_over_index, footer=f"Final score: {self.score}")
            elif self.confirm_return_state == "name_entry":
                self.draw_maze()
                self.draw_side_panel()
                self.draw_name_entry()
            else:
                self.draw_maze()
                self.draw_side_panel()
            self.draw_confirm_overlay("Exit the game?")

        if self.message:
            self.draw_message_banner(self.message)

    def draw_header(self) -> None:
        title = self.title_font.render("Pacman", True, HIGHLIGHT)
        self.screen.blit(title, (24, 22))

        stage_surface = self.font.render(f"Stage {self.stage_number}", True, TEXT)
        score_surface = self.font.render(f"Score {self.score}", True, TEXT)
        high_score_surface = self.font.render(f"High Score {self.high_score}", True, TEXT)
        lives_surface = self.font.render(f"Lives {self.lives}", True, TEXT)

        self.screen.blit(stage_surface, (220, 28))
        self.screen.blit(score_surface, (380, 28))
        self.screen.blit(high_score_surface, (540, 28))
        self.screen.blit(lives_surface, (780, 28))

        if self.vulnerability_timer > 0:
            timer_surface = self.small_font.render(f"Power {self.vulnerability_timer:0.1f}s", True, POWER_PELLET)
            self.screen.blit(timer_surface, (220, 58))

    def draw_maze(self) -> None:
        maze_rect = self.get_maze_rect()
        pygame.draw.rect(self.screen, MAZE_BACKGROUND, maze_rect, border_radius=14)

        time_seconds = pygame.time.get_ticks() / 1000.0

        for y in range(self.stage_map.height):
            for x in range(self.stage_map.width):
                tile_rect = pygame.Rect(24 + x * GRID_SIZE, TOP_MARGIN + y * GRID_SIZE, GRID_SIZE, GRID_SIZE)
                if (x, y) in self.stage_map.walls:
                    pygame.draw.rect(self.screen, WALL_COLOR, tile_rect.inflate(-4, -4), border_radius=8)
                    pygame.draw.rect(self.screen, WALL_ACCENT, tile_rect.inflate(-10, -10), width=2, border_radius=6)

        for house_cell in self.stage_map.house_cells:
            tile_rect = pygame.Rect(24 + house_cell[0] * GRID_SIZE, TOP_MARGIN + house_cell[1] * GRID_SIZE, GRID_SIZE, GRID_SIZE)
            pygame.draw.rect(self.screen, (27, 32, 52), tile_rect.inflate(-6, -6), border_radius=6)

        for gate_cell in self.stage_map.gates:
            tile_rect = pygame.Rect(24 + gate_cell[0] * GRID_SIZE, TOP_MARGIN + gate_cell[1] * GRID_SIZE, GRID_SIZE, GRID_SIZE)
            gate_rect = pygame.Rect(tile_rect.x + 4, tile_rect.centery - 3, tile_rect.width - 8, 6)
            pygame.draw.rect(self.screen, (255, 176, 209), gate_rect, border_radius=3)

        for portal_cell in self.stage_map.portals:
            tile_rect = pygame.Rect(24 + portal_cell[0] * GRID_SIZE, TOP_MARGIN + portal_cell[1] * GRID_SIZE, GRID_SIZE, GRID_SIZE)
            portal_rect = tile_rect.inflate(-10, -6)
            pygame.draw.rect(self.screen, PORTAL_COLOR, portal_rect, border_radius=10)
            pygame.draw.rect(self.screen, PORTAL_ACCENT, portal_rect.inflate(-8, -10), width=2, border_radius=8)

        pulse = 0.75 + 0.25 * math.sin(time_seconds * 7)
        for dot_cell in self.stage_map.dots:
            center = self.cell_center(dot_cell)
            pygame.draw.circle(self.screen, DOT, center, 3)

        for pellet_cell in self.stage_map.pellets:
            center = self.cell_center(pellet_cell)
            pygame.draw.circle(self.screen, POWER_PELLET, center, int(7 * pulse))

        self.draw_effects()

        if self.fruit is not None and not self.fruit_eaten:
            self.draw_fruit(self.fruit.position, self.fruit.name, bob=math.sin(time_seconds * 5))

        self.draw_pacman(time_seconds)
        for ghost in self.ghosts:
            if self.chase_timer >= ghost.release_delay:
                self.draw_ghost(ghost)

    def draw_side_panel(self) -> None:
        panel = self.get_side_panel_rect()
        pygame.draw.rect(self.screen, (17, 22, 39), panel, border_radius=18)
        pygame.draw.rect(self.screen, (52, 70, 120), panel, width=2, border_radius=18)

        lines = [
            f"Stage map {stage_map_number(self.stage_number)}/{total_map_count()}",
            f"Fruit {self.fruit_name.title()}",
            f"Fruit score {FRUIT_SCORES[self.fruit_name]}",
            self.fruit_status_text(),
            "Portal tunnels wrap edges",
            "Mouse controls",
            "Move the cursor anywhere",
            "Pacman follows the pointer",
        ]

        for index, line in enumerate(lines):
            color = HIGHLIGHT if index in {0, 1, 2, 5} else TEXT
            surface = self.small_font.render(line, True, color)
            self.screen.blit(surface, (panel.x + 18, panel.y + 18 + index * 24))

        self.draw_text_button("Pause", self.get_pause_button_rect(), self.get_pause_button_rect().collidepoint(self.mouse_screen_position() or (-1, -1)))
        self.draw_text_button(
            "Restart",
            self.get_restart_button_rect(),
            self.get_restart_button_rect().collidepoint(self.mouse_screen_position() or (-1, -1)),
        )

        help_rect = pygame.Rect(panel.x + 18, panel.y + 386, panel.width - 36, 62)
        pygame.draw.rect(self.screen, (23, 30, 52), help_rect, border_radius=12)
        pygame.draw.rect(self.screen, (86, 108, 168), help_rect, width=1, border_radius=12)
        self.draw_text_block(
            "Keep the cursor ahead of Pacman for smooth turns.",
            help_rect.x + 12,
            help_rect.y + 10,
            help_rect.width - 24,
            self.small_font,
            TEXT,
        )

    @staticmethod
    def cell_center(cell: tuple[int, int]) -> tuple[int, int]:
        return 24 + int((cell[0] + 0.5) * GRID_SIZE), TOP_MARGIN + int((cell[1] + 0.5) * GRID_SIZE)

    @staticmethod
    def world_center(position: pygame.Vector2) -> tuple[int, int]:
        return 24 + int((position.x + 0.5) * GRID_SIZE), TOP_MARGIN + int((position.y + 0.5) * GRID_SIZE)

    def fruit_status_text(self) -> str:
        if self.fruit is not None and not self.fruit_eaten:
            return "Fruit weaving around"
        if self.fruit_eaten:
            return "Fruit already collected"
        return f"{max(0, 50 - self.dot_eat_count)} dots to fruit"

    def draw_pacman(self, time_seconds: float) -> None:
        center = self.world_center(self.pacman.position)
        radius = GRID_SIZE // 2 - 2
        mouth_phase = 0.18 + 0.16 * (0.5 + 0.5 * math.sin(time_seconds * 12))
        direction = self.pacman.direction if self.pacman.direction.length_squared() > 0 else DIR_RIGHT

        if self.pacman_teleport_timer > 0:
            teleport_ratio = self.pacman_teleport_timer / 0.26
            aura_radius = radius + int(3 + teleport_ratio * 5)
            pygame.draw.circle(self.screen, PORTAL_COLOR, center, aura_radius, width=2)

        if direction == DIR_RIGHT:
            base_angle = 0
        elif direction == DIR_LEFT:
            base_angle = math.pi
        elif direction == DIR_UP:
            base_angle = -math.pi / 2
        else:
            base_angle = math.pi / 2

        pygame.draw.circle(self.screen, PACMAN_YELLOW, center, radius)
        mouth_points = [
            center,
            (
                center[0] + int(radius * math.cos(base_angle + mouth_phase)),
                center[1] + int(radius * math.sin(base_angle + mouth_phase)),
            ),
            (
                center[0] + int(radius * math.cos(base_angle - mouth_phase)),
                center[1] + int(radius * math.sin(base_angle - mouth_phase)),
            ),
        ]
        pygame.draw.polygon(self.screen, MAZE_BACKGROUND, mouth_points)

    def draw_effects(self) -> None:
        if self.pacman_teleport_timer > 0 and self.pacman_teleport_path is not None:
            start, end = self.pacman_teleport_path
            path_ratio = self.pacman_teleport_timer / 0.26
            line_width = max(1, int(1 + path_ratio * 4))
            pygame.draw.line(self.screen, PORTAL_ACCENT, start, end, line_width)

        for ring in self.effect_rings:
            ratio = ring.age / ring.duration
            remaining = max(0.0, 1.0 - ratio)
            radius = ring.start_radius + (ring.end_radius - ring.start_radius) * ratio
            color = (
                int(ring.color[0] * remaining),
                int(ring.color[1] * remaining),
                int(ring.color[2] * remaining),
            )
            pygame.draw.circle(
                self.screen,
                color,
                (int(ring.position.x), int(ring.position.y)),
                max(1, int(radius)),
                width=ring.width,
            )

        for particle in self.effect_particles:
            ratio = particle.age / particle.duration
            remaining = max(0.0, 1.0 - ratio)
            color = (
                int(particle.color[0] * remaining),
                int(particle.color[1] * remaining),
                int(particle.color[2] * remaining),
            )
            radius = max(1, int(particle.size * (0.55 + 0.45 * remaining)))
            pygame.draw.circle(
                self.screen,
                color,
                (int(particle.position.x), int(particle.position.y)),
                radius,
            )

    def draw_ghost(self, ghost: Ghost) -> None:
        center_x, center_y = self.world_center(ghost.position)
        radius = GRID_SIZE // 2 - 3
        body_color = (80, 100, 255) if ghost.mode == "vulnerable" else ghost.color
        if ghost.mode == "respawning":
            body_color = (210, 210, 235)

        head_center = (center_x, center_y - 3)
        pygame.draw.circle(self.screen, body_color, head_center, radius)
        body_rect = pygame.Rect(center_x - radius, center_y - 3, radius * 2, radius + 7)
        pygame.draw.rect(self.screen, body_color, body_rect)

        for offset in (-radius + 4, -2, radius - 8):
            pygame.draw.circle(self.screen, MAZE_BACKGROUND, (center_x + offset, center_y + radius + 1), 4)

        eye_y = center_y - 6
        eye_offsets = (-6, 6)
        pupil_offset_x = int(ghost.direction.x * 2)
        pupil_offset_y = int(ghost.direction.y * 2)
        for offset in eye_offsets:
            pygame.draw.circle(self.screen, (255, 255, 255), (center_x + offset, eye_y), 4)
            pygame.draw.circle(self.screen, (20, 40, 90), (center_x + offset + pupil_offset_x, eye_y + pupil_offset_y), 2)

    def draw_fruit(self, position: pygame.Vector2, fruit_name: str, bob: float) -> None:
        center_x, center_y = self.world_center(position)
        center_y += int(bob * 2)
        color = FRUIT_COLORS[fruit_name]
        pygame.draw.circle(self.screen, color, (center_x, center_y + 2), 8)
        pygame.draw.line(self.screen, (80, 180, 70), (center_x, center_y - 9), (center_x + 4, center_y - 15), 3)
        pygame.draw.ellipse(self.screen, (120, 220, 90), pygame.Rect(center_x + 2, center_y - 15, 10, 6))

    def draw_main_menu(self) -> None:
        title = self.big_font.render("Pacman", True, HIGHLIGHT)
        subtitle = self.small_font.render("Click an option to begin.", True, SUBTLE_TEXT)
        self.screen.blit(title, (self.window_width // 2 - title.get_width() // 2, 120))
        self.screen.blit(subtitle, (self.window_width // 2 - subtitle.get_width() // 2, 188))
        self.draw_option_list(self.main_menu_options, self.main_menu_index, 280)
        hint = self.small_font.render("Desktop controls use the mouse.", True, SUBTLE_TEXT)
        self.screen.blit(hint, (self.window_width // 2 - hint.get_width() // 2, 520))

    def draw_how_to_play(self) -> None:
        title = self.title_font.render("How to Play", True, HIGHLIGHT)
        self.screen.blit(title, (48, 112))
        text = (
            "Guide Pacman through the maze to eat every dot and power pellet. "
            "Dots are worth 1 point, power pellets are worth 10 points, and vulnerable ghosts "
            "are worth 50 points. After eating 50 dots in a stage, one fruit spawns and keeps weaving "
            "around the maze while trying not to run directly toward or away from Pacman. Fruit type depends on the "
            "stage: cherry, strawberry, banana, apple, orange, then pear from stage 6 onward. Cyan portal "
            "tunnels wrap Pacman and ghosts across the maze edges on the redesigned maps. Clear every "
            "collectible to advance while the ghosts get faster."
        )
        paragraph_bottom = self.draw_text_block(text, 48, 170, self.window_width - 96, self.font, TEXT)
        controls = [
            "Move the cursor inside the maze to guide Pacman.",
            "Keep the cursor in front of Pacman to line up the next turn.",
            "Use the Pause and Restart buttons on the right side panel.",
            "Click Back to return to the main menu.",
        ]
        controls_start_y = paragraph_bottom + 22
        for index, line in enumerate(controls):
            surface = self.small_font.render(line, True, TEXT)
            self.screen.blit(surface, (48, controls_start_y + index * 30))
        self.draw_text_button("Back", self.get_top_button_rect(), self.get_top_button_rect().collidepoint(self.mouse_screen_position() or (-1, -1)))

    def draw_leaderboard(self) -> None:
        title = self.title_font.render("Leaderboard", True, HIGHLIGHT)
        self.screen.blit(title, (48, 112))
        subtitle = self.small_font.render("Click Refresh to update scores.", True, SUBTLE_TEXT)
        self.screen.blit(subtitle, (48, 158))
        self.draw_text_button("Back", self.get_top_button_rect(), self.get_top_button_rect().collidepoint(self.mouse_screen_position() or (-1, -1)))
        self.draw_text_button(
            "Refresh",
            self.get_secondary_top_button_rect(),
            self.get_secondary_top_button_rect().collidepoint(self.mouse_screen_position() or (-1, -1)),
        )

        if self.leaderboard_error:
            self.draw_text_block(self.leaderboard_error, 48, 230, self.window_width - 96, self.font, (255, 160, 160))
            return

        if not self.leaderboard_entries:
            no_scores = self.font.render("No scores recorded yet.", True, TEXT)
            self.screen.blit(no_scores, (48, 230))
            return

        headers = ["Rank", "Player", "Score", "Stage", "Date"]
        x_positions = [48, 140, 360, 500, 620]
        for header, x_position in zip(headers, x_positions):
            surface = self.font.render(header, True, TEXT)
            self.screen.blit(surface, (x_position, 220))

        for index, entry in enumerate(self.leaderboard_entries, start=1):
            values = [
                str(index),
                entry.player_name,
                str(entry.score),
                str(entry.stage_reached),
                entry.played_at.strftime("%Y-%m-%d"),
            ]
            for value, x_position in zip(values, x_positions):
                surface = self.small_font.render(value, True, TEXT)
                self.screen.blit(surface, (x_position, 260 + (index - 1) * 30))

    def draw_settings(self) -> None:
        title = self.title_font.render("Settings", True, HIGHLIGHT)
        self.screen.blit(title, (48, 112))
        subtitle = self.small_font.render("Use the mouse to adjust sound.", True, SUBTLE_TEXT)
        self.screen.blit(subtitle, (48, 158))
        controls = self.get_settings_control_rects()

        volume_label = self.font.render("Volume", True, TEXT)
        volume_value = self.font.render(f"{int(self.volume_steps[self.volume_index] * 100)}%", True, HIGHLIGHT)

        self.screen.blit(volume_label, (72, 246))
        self.screen.blit(volume_value, (470, 246))

        for key in ("volume_down", "volume_up"):
            label = "-" if key.endswith("down") else "+"
            self.draw_text_button(label, controls[key], controls[key].collidepoint(self.mouse_screen_position() or (-1, -1)))

        self.draw_text_button("Back", controls["back"], controls["back"].collidepoint(self.mouse_screen_position() or (-1, -1)))

    def draw_menu_overlay(self, title: str, options: list[str], selected_index: int, footer: str | None = None) -> None:
        rect = self.get_menu_overlay_rect(options, footer=footer)
        pygame.draw.rect(self.screen, (10, 14, 24), rect, border_radius=16)
        pygame.draw.rect(self.screen, (70, 99, 166), rect, width=2, border_radius=16)
        title_surface = self.title_font.render(title, True, HIGHLIGHT)
        self.screen.blit(title_surface, (rect.centerx - title_surface.get_width() // 2, rect.y + 24))
        self.draw_option_list(options, selected_index, rect.y + 92, center_x=rect.centerx, width=rect.width - 88)
        if footer:
            footer_surface = self.small_font.render(footer, True, SUBTLE_TEXT)
            self.screen.blit(footer_surface, (rect.centerx - footer_surface.get_width() // 2, rect.bottom - 34))

    def draw_confirm_overlay(self, prompt: str) -> None:
        rect = pygame.Rect(self.window_width // 2 - 180, 210, 360, 180)
        pygame.draw.rect(self.screen, (10, 14, 24), rect, border_radius=16)
        pygame.draw.rect(self.screen, (70, 99, 166), rect, width=2, border_radius=16)
        prompt_surface = self.font.render(prompt, True, TEXT)
        self.screen.blit(prompt_surface, (rect.centerx - prompt_surface.get_width() // 2, rect.y + 34))
        yes_rect, no_rect = self.get_confirm_button_rects()
        mouse_position = self.mouse_screen_position() or (-1, -1)
        self.draw_text_button("Yes", yes_rect, yes_rect.collidepoint(mouse_position) or self.confirm_index == 0)
        self.draw_text_button("No", no_rect, no_rect.collidepoint(mouse_position) or self.confirm_index == 1)

    def draw_name_entry(self) -> None:
        rect = self.get_name_entry_rect()
        pygame.draw.rect(self.screen, (10, 14, 24), rect, border_radius=16)
        pygame.draw.rect(self.screen, (70, 99, 166), rect, width=2, border_radius=16)
        title = self.font.render("New High Score! Choose your name.", True, HIGHLIGHT)
        self.screen.blit(title, (rect.centerx - title.get_width() // 2, rect.y + 28))
        score_line = self.small_font.render(f"Score {self.score}   Stage {self.stage_number}", True, TEXT)
        self.screen.blit(score_line, (rect.centerx - score_line.get_width() // 2, rect.y + 70))
        input_rect = pygame.Rect(rect.x + 60, rect.y + 108, rect.width - 120, 44)
        pygame.draw.rect(self.screen, (24, 32, 56), input_rect, border_radius=8)
        pygame.draw.rect(self.screen, HIGHLIGHT, input_rect, width=2, border_radius=8)
        input_surface = self.font.render(self.name_entry_value or "_", True, TEXT)
        self.screen.blit(
            input_surface,
            (
                input_rect.centerx - input_surface.get_width() // 2,
                input_rect.centery - input_surface.get_height() // 2,
            ),
        )
        hint = self.small_font.render("Type your name, then press Enter or click Save.", True, SUBTLE_TEXT)
        self.screen.blit(hint, (rect.centerx - hint.get_width() // 2, rect.y + 172))

        mouse_position = self.mouse_screen_position() or (-1, -1)
        for label, button_rect, _ in self.get_name_entry_action_buttons():
            self.draw_text_button(label, button_rect, button_rect.collidepoint(mouse_position), font=self.small_font)

    def draw_option_list(
        self,
        options: list[str],
        selected_index: int,
        start_y: int,
        center_x: int | None = None,
        width: int = 360,
    ) -> None:
        rects = self.get_option_rects(options, start_y, center_x=center_x, width=width)
        mouse_position = self.mouse_screen_position() or (-1, -1)
        for index, option in enumerate(options):
            hover = rects[index].collidepoint(mouse_position)
            self.draw_text_button(option, rects[index], hover or index == selected_index)

    def draw_message_banner(self, message: str) -> None:
        rect = pygame.Rect(24, self.window_height - 58, self.window_width - 48, 34)
        pygame.draw.rect(self.screen, (30, 34, 54), rect, border_radius=8)
        pygame.draw.rect(self.screen, (75, 94, 140), rect, width=1, border_radius=8)
        surface = self.small_font.render(message, True, TEXT)
        self.screen.blit(surface, (rect.x + 12, rect.y + 7))

    def draw_center_overlay(self, label: str) -> None:
        rect = pygame.Rect(self.window_width // 2 - 160, self.window_height // 2 - 48, 320, 96)
        pygame.draw.rect(self.screen, (10, 14, 24), rect, border_radius=16)
        pygame.draw.rect(self.screen, (86, 108, 168), rect, width=2, border_radius=16)
        surface = self.title_font.render(label, True, HIGHLIGHT)
        self.screen.blit(surface, (rect.centerx - surface.get_width() // 2, rect.centery - surface.get_height() // 2))

    def draw_text_button(
        self,
        label: str,
        rect: pygame.Rect,
        active: bool,
        font: pygame.font.Font | None = None,
    ) -> None:
        if font is None:
            font = self.font
        fill = (48, 62, 105) if active else (28, 38, 68)
        border = HIGHLIGHT if active else (86, 108, 168)
        text_color = HIGHLIGHT if active else TEXT
        pygame.draw.rect(self.screen, fill, rect, border_radius=10)
        pygame.draw.rect(self.screen, border, rect, width=2, border_radius=10)
        surface = font.render(label, True, text_color)
        self.screen.blit(surface, (rect.centerx - surface.get_width() // 2, rect.centery - surface.get_height() // 2))

    def draw_text_block(
        self,
        text: str,
        x: int,
        y: int,
        max_width: int,
        font: pygame.font.Font,
        color: tuple[int, int, int],
    ) -> int:
        lines = self.wrapped_lines(text, max_width, font)

        line_spacing = font.get_linesize() + 2
        for index, line in enumerate(lines):
            surface = font.render(line, True, color)
            self.screen.blit(surface, (x, y + index * line_spacing))

        return y + len(lines) * line_spacing

    @staticmethod
    def wrapped_lines(text: str, max_width: int, font: pygame.font.Font) -> list[str]:
        words = text.split()
        lines: list[str] = []
        current_line = ""

        for word in words:
            candidate = word if not current_line else f"{current_line} {word}"
            if font.size(candidate)[0] <= max_width:
                current_line = candidate
            else:
                lines.append(current_line)
                current_line = word

        if current_line:
            lines.append(current_line)

        return lines
