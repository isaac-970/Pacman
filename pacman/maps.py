from __future__ import annotations

from dataclasses import dataclass

CARDINAL_DIRECTIONS = ((0, -1), (1, 0), (0, 1), (-1, 0))
PACMAN_WALKABLE_TILES = {".", "o", "P", "T"}
PROTECTED_STRUCTURE_TILES = {"T", "=", "H", "h", "1", "2", "3", "4"}

FRUIT_SEQUENCE = ("cherry", "strawberry", "banana", "apple", "orange", "pear")
FRUIT_SCORES = {
    "cherry": 20,
    "strawberry": 40,
    "banana": 60,
    "apple": 80,
    "orange": 100,
    "pear": 120,
}

RAW_MAPS = [
    [
        "#####################",
        "#o.#......#.#.#..#.o#",
        "#.....#.#...........#",
        "#.##...#.#.#.#...#.##",
        "#..#.#...#.....#....#",
        "#.......##=##.....#.#",
        "##..#.#.#2H3#.#.#...#",
        "T...#...#HHH#...#...T",
        "#.#.#...#1H4#...#.#.#",
        "#.......##=##.......#",
        "#.##....#...#..#.##.#",
        "#....##.#.P.#.##....#",
        "#.#...............#.#",
        "#..#.#..##.##..#.#..#",
        "#..#....##.##....#..#",
        "#o...#.........#...o#",
        "#####################",
    ],
    [
        "#####################",
        "#o....#.......#....o#",
        "T..##.#.###.#.#.##..T",
        "#.#...............#.#",
        "#...##......#..##...#",
        "#......###=###......#",
        "#.#.#...#2H3##....#.#",
        "#.#..#..#HHH#..#..#.#",
        "#.#....##1H4##..#.#.#",
        "#...#...##=##.#..#..#",
        "#.#...#.......#.....#",
        "##..#.##..P..#..#.###",
        "#.#.................#",
        "T....######...###.#.T",
        "#.##.#.#o...#..#....#",
        "#o.................o#",
        "#####################",
    ],
    [
        "#####################",
        "T......#....o#......T",
        "#.o..#.#..#..#.#..o.#",
        "#.##.#...###...#.##.#",
        "#......#.....#......#",
        "#.#.#...##=##...#.#.#",
        "#...#...#2H4#...#...#",
        "T.#.##.##HHH##.##.#.T",
        "#.#.....#1H3#.....#.#",
        "#.#...#.##=##.#...#.#",
        "#.#.....#...#...#.#.#",
        "#....##.#.P.#.#.#...#",
        "#...#............#..#",
        "##.#....###..##..#.##",
        "#...#.#.#o..#...#...#",
        "T.o...............o.T",
        "#####################",
    ],
]


def fruit_for_stage(stage: int) -> str:
    index = min(max(stage, 1) - 1, len(FRUIT_SEQUENCE) - 1)
    return FRUIT_SEQUENCE[index]


def stage_map_number(stage_number: int) -> int:
    stage = max(stage_number, 1)
    if stage <= 2:
        return 1
    if stage <= 4:
        return 2
    return 3


def total_map_count() -> int:
    return len(RAW_MAPS)


@dataclass(slots=True)
class StageMap:
    layout: list[str]
    width: int
    height: int
    walls: set[tuple[int, int]]
    gates: set[tuple[int, int]]
    house_cells: set[tuple[int, int]]
    dots: set[tuple[int, int]]
    pellets: set[tuple[int, int]]
    portals: dict[tuple[int, int], tuple[int, int]]
    open_cells: list[tuple[int, int]]
    pacman_start: tuple[int, int]
    ghost_starts: list[tuple[int, int]]
    ghost_house_exit: tuple[int, int]

    @classmethod
    def from_rows(cls, rows: list[str]) -> "StageMap":
        width = max(len(row) for row in rows)
        normalized_rows = [row.ljust(width, "#") for row in rows]
        walls: set[tuple[int, int]] = set()
        gates: set[tuple[int, int]] = set()
        house_cells: set[tuple[int, int]] = set()
        dots: set[tuple[int, int]] = set()
        pellets: set[tuple[int, int]] = set()
        portal_rows: dict[int, list[tuple[int, int]]] = {}
        portal_columns: dict[int, list[tuple[int, int]]] = {}
        portal_cells: set[tuple[int, int]] = set()
        open_cells: list[tuple[int, int]] = []
        pacman_start = (1, 1)
        ghost_markers: list[tuple[int, tuple[int, int]]] = []

        for y, row in enumerate(normalized_rows):
            for x, tile in enumerate(row):
                if tile == "#":
                    walls.add((x, y))
                    continue

                open_cells.append((x, y))

                if tile == ".":
                    dots.add((x, y))
                elif tile == "o":
                    pellets.add((x, y))
                elif tile == "=":
                    gates.add((x, y))
                elif tile in {"H", "h"}:
                    house_cells.add((x, y))
                elif tile == "T":
                    portal_rows.setdefault(y, []).append((x, y))
                    portal_columns.setdefault(x, []).append((x, y))
                    portal_cells.add((x, y))
                elif tile == "P":
                    pacman_start = (x, y)
                elif tile in {"1", "2", "3", "4"}:
                    house_cells.add((x, y))
                    ghost_markers.append((int(tile), (x, y)))

        ghost_starts = [position for _, position in sorted(ghost_markers, key=lambda marker: marker[0])]

        if not ghost_starts:
            ghost_starts = [(width // 2, len(normalized_rows) // 2)]

        portals: dict[tuple[int, int], tuple[int, int]] = {}
        for portal_cell in sorted(portal_cells, key=lambda cell: (cell[1], cell[0])):
            portal_x, portal_y = portal_cell
            if portal_x not in {0, width - 1} and portal_y not in {0, len(normalized_rows) - 1}:
                raise ValueError(f"Portal at {portal_cell} must be placed on the outer boundary.")

            candidates: list[tuple[int, int]] = []

            row_edge_portals = [
                position for position in portal_rows.get(portal_y, []) if position[0] in {0, width - 1}
            ]
            if portal_x in {0, width - 1} and len(row_edge_portals) == 2:
                left_portal, right_portal = sorted(row_edge_portals, key=lambda position: position[0])
                if left_portal[0] == 0 and right_portal[0] == width - 1:
                    candidates.append(right_portal if portal_cell == left_portal else left_portal)

            column_edge_portals = [
                position for position in portal_columns.get(portal_x, []) if position[1] in {0, len(normalized_rows) - 1}
            ]
            if portal_y in {0, len(normalized_rows) - 1} and len(column_edge_portals) == 2:
                top_portal, bottom_portal = sorted(column_edge_portals, key=lambda position: position[1])
                if top_portal[1] == 0 and bottom_portal[1] == len(normalized_rows) - 1:
                    candidates.append(bottom_portal if portal_cell == top_portal else top_portal)

            if len(candidates) != 1:
                raise ValueError(f"Portal at {portal_cell} must resolve to exactly one matching endpoint.")

            portals[portal_cell] = candidates[0]

        ghost_house_exit = pacman_start
        for gate_x, gate_y in sorted(gates, key=lambda cell: (cell[1], cell[0])):
            adjacent_cells = [
                (gate_x, gate_y - 1),
                (gate_x, gate_y + 1),
                (gate_x - 1, gate_y),
                (gate_x + 1, gate_y),
            ]
            touches_house = any(cell in house_cells for cell in adjacent_cells)
            exit_candidates = [
                cell
                for cell in adjacent_cells
                if 0 <= cell[0] < width
                and 0 <= cell[1] < len(normalized_rows)
                and cell not in walls
                and cell not in gates
                and cell not in house_cells
            ]
            if touches_house and exit_candidates:
                ghost_house_exit = sorted(exit_candidates, key=lambda cell: (cell[1], cell[0]))[0]
                break

        return cls(
            layout=normalized_rows,
            width=width,
            height=len(normalized_rows),
            walls=walls,
            gates=gates,
            house_cells=house_cells,
            dots=dots,
            pellets=pellets,
            portals=portals,
            open_cells=open_cells,
            pacman_start=pacman_start,
            ghost_starts=ghost_starts,
            ghost_house_exit=ghost_house_exit,
        )


def pacman_dead_end_cells(stage_map: StageMap) -> list[tuple[int, int]]:
    walkable_cells = {
        cell
        for cell in stage_map.open_cells
        if cell not in stage_map.gates and cell not in stage_map.house_cells
    }

    portal_adjacent_cells: set[tuple[int, int]] = set()
    for portal_cell in stage_map.portals:
        for delta_x, delta_y in CARDINAL_DIRECTIONS:
            neighbor = (portal_cell[0] + delta_x, portal_cell[1] + delta_y)
            if neighbor in walkable_cells:
                portal_adjacent_cells.add(neighbor)

    dead_ends: list[tuple[int, int]] = []
    for cell in sorted(walkable_cells, key=lambda position: (position[1], position[0])):
        if cell in stage_map.portals or cell in portal_adjacent_cells:
            continue

        neighbor_count = 0
        for delta_x, delta_y in CARDINAL_DIRECTIONS:
            neighbor = (cell[0] + delta_x, cell[1] + delta_y)
            if neighbor in walkable_cells:
                neighbor_count += 1
        if cell in stage_map.portals:
            neighbor_count += 1

        if neighbor_count <= 1:
            dead_ends.append(cell)

    return dead_ends


def _normalized_rows(rows: list[str]) -> list[str]:
    width = max(len(row) for row in rows)
    return [row.ljust(width, "#") for row in rows]


def _protected_cells(rows: list[str]) -> set[tuple[int, int]]:
    normalized_rows = _normalized_rows(rows)
    width = len(normalized_rows[0])
    height = len(normalized_rows)
    protected: set[tuple[int, int]] = set()

    for x in range(width):
        protected.add((x, 0))
        protected.add((x, height - 1))
    for y in range(height):
        protected.add((0, y))
        protected.add((width - 1, y))

    for y, row in enumerate(normalized_rows):
        for x, tile in enumerate(row):
            if tile not in PROTECTED_STRUCTURE_TILES:
                continue
            for delta_x, delta_y in ((0, 0), *CARDINAL_DIRECTIONS):
                neighbor_x = x + delta_x
                neighbor_y = y + delta_y
                if 0 <= neighbor_x < width and 0 <= neighbor_y < height:
                    protected.add((neighbor_x, neighbor_y))

    return protected


def _carve_dead_end(rows: list[str], dead_end: tuple[int, int]) -> list[str] | None:
    normalized_rows = _normalized_rows(rows)
    width = len(normalized_rows[0])
    height = len(normalized_rows)
    protected = _protected_cells(normalized_rows)
    stage_map = StageMap.from_rows(normalized_rows)
    walkable_cells = {
        cell
        for cell in stage_map.open_cells
        if cell not in stage_map.gates and cell not in stage_map.house_cells
    }

    candidates: list[tuple[int, tuple[int, int]]] = []
    for delta_x, delta_y in CARDINAL_DIRECTIONS:
        wall_x = dead_end[0] + delta_x
        wall_y = dead_end[1] + delta_y
        beyond_x = dead_end[0] + delta_x * 2
        beyond_y = dead_end[1] + delta_y * 2
        wall_cell = (wall_x, wall_y)
        beyond_cell = (beyond_x, beyond_y)

        if not (1 <= wall_x < width - 1 and 1 <= wall_y < height - 1):
            continue
        if not (1 <= beyond_x < width - 1 and 1 <= beyond_y < height - 1):
            continue
        if wall_cell in protected or beyond_cell in protected:
            continue
        if normalized_rows[wall_y][wall_x] != "#":
            continue
        if normalized_rows[beyond_y][beyond_x] not in PACMAN_WALKABLE_TILES - {"T"}:
            continue

        beyond_degree = sum(
            1
            for step_x, step_y in CARDINAL_DIRECTIONS
            if (beyond_x + step_x, beyond_y + step_y) in walkable_cells
        )
        candidates.append((beyond_degree, wall_cell))

    if not candidates:
        return None

    _, chosen_wall = max(candidates, key=lambda item: (item[0], -item[1][1], -item[1][0]))
    updated_rows = [list(row) for row in normalized_rows]
    updated_rows[chosen_wall[1]][chosen_wall[0]] = "."
    return ["".join(row) for row in updated_rows]


def _remove_dead_ends(rows: list[str]) -> list[str]:
    normalized_rows = _normalized_rows(rows)
    iteration_limit = len(normalized_rows) * len(normalized_rows[0])

    for _ in range(iteration_limit):
        dead_ends = pacman_dead_end_cells(StageMap.from_rows(normalized_rows))
        if not dead_ends:
            return normalized_rows

        carved_rows: list[str] | None = None
        for dead_end in dead_ends:
            carved_rows = _carve_dead_end(normalized_rows, dead_end)
            if carved_rows is not None:
                normalized_rows = carved_rows
                break

        if carved_rows is None:
            unresolved = ", ".join(str(cell) for cell in dead_ends[:5])
            raise ValueError(f"Could not remove dead ends from map; unresolved cells: {unresolved}")

    raise ValueError("Dead-end removal exceeded safe iteration limit.")


def build_stage_map(stage_number: int) -> StageMap:
    raw_map = RAW_MAPS[stage_map_number(stage_number) - 1]
    processed_rows = _remove_dead_ends(raw_map)
    stage_map = StageMap.from_rows(processed_rows)
    dead_ends = pacman_dead_end_cells(stage_map)
    if dead_ends:
        raise ValueError(f"Stage map still contains dead ends: {dead_ends[:5]}")
    return stage_map
