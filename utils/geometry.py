#!/usr/bin/env python

from functools import lru_cache
from math import atan2, degrees, hypot, radians, sin, cos, inf as INFINITY
from typing import Optional, Sequence

from numba import njit
from shapely.geometry import LineString, Polygon

from utils.data_types import Point, Number


def precalculate_8_angles():
    """
    Build dict of int angles. We chop 360 degrees circle by 8 slices
    each of 45 degrees. First slice has it's center at 0/360 degrees,
    second slice has it's center at 22.5 degrees etc. This dict allows
    for fast replacing angle of range 0-359 to one of 24 pre-calculated
    angles.
    """
    return {
        i: j if j < 8 else 0 for j in range(0, 9) for i in range(361)
        if (j * 45) - i < 22.5
    }


@njit
def calculate_angle(sx: float, sy: float, ex: float, ey: float) -> float:
    """
    Calculate angle in direction from 'start' to the 'end' point in degrees.

    :param:sx float -- x coordinate of start point
    :param:sy float -- y coordinate of start point
    :param:ex float -- x coordinate of end point
    :param:ey float -- y coordinate of end point
    :return: float -- degrees in range 0-360.
    """
    rads = atan2(ex - sx, ey - sy)
    return -degrees(rads) % 360


def distance_2d(coord_a: Point, coord_b: Point) -> float:
    """Calculate distance between two points in 2D space."""
    return hypot(coord_b[0] - coord_a[0], coord_b[1] - coord_a[1])


def close_enough(coord_a: Point, coord_b: Point, distance: float) -> bool:
    """
    Calculate distance between two points in 2D space and find if distance
    is less than minimum distance.

    :param coord_a: Point -- (x, y) coords of first point
    :param coord_b: Point -- (x, y) coords of second point
    :param distance: float -- minimal distance to check against
    :return: bool -- if distance is less than
    """
    return distance_2d(coord_a, coord_b) <= distance


@njit
def vector_2d(angle: float, scalar: float) -> Point:
    """
    Calculate x and y parts of the current vector.

    :param angle: float -- angle of the vector
    :param scalar: float -- scalar difference of the vector (e.g. max_speed)
    :return: Point -- x and y parts of the vector in format: (float, float)
    """
    rad = -radians(angle)
    return sin(rad) * scalar, cos(rad) * scalar


def move_along_vector(start: Point,
                      velocity: float,
                      target: Optional[Point] = None,
                      angle: Optional[float] = None) -> Point:
    """
    Create movement vector starting at 'start' point angled in direction of
    'target' point with scalar velocity 'velocity'. Optionally, instead of
    'target' position, you can pass starting 'angle' of the vector.

    Use 'current_waypoint' position only, when you now the point and do not know the
    angle between two points, but want quickly calculate position of the
    another point lying on the line connecting two, known points.

    :param start: tuple -- point from vector starts
    :param target: tuple -- current_waypoint that vector 'looks at'
    :param velocity: float -- scalar length of the vector
    :param angle: float -- angle of the vector direction
    :return: tuple -- (optional)position of the vector end
    """
    if target is None and angle is None:
        raise ValueError("You MUST pass current_waypoint position or vector angle!")
    p1 = (start[0], start[1])
    if target:
        p2 = (target[0], target[1])
        angle = calculate_angle(*p1, *p2)
    vector = vector_2d(angle, velocity)
    return p1[0] + vector[0], p1[1] + vector[1]


def is_visible(position_a: Point,
               position_b: Point,
               obstacles: Sequence,
               max_distance: float = INFINITY) -> bool:
    """
    Check if position_a is 'visible' from position_b and vice-versa. 'Visible'
    means, that you can connect both points with straight line without
    intersecting any obstacle.

    :param position_a: tuple -- coordinates of first position (x, y)
    :param position_b: tuple -- coordinates of second position (x, y)
    :param obstacles: list -- Obstacle objects to check against
    :param max_distance: float -- maximum visibility fistance
    :return: tuple -- (bool, list)
    """
    line_of_sight = LineString([position_a, position_b])
    if line_of_sight.length > max_distance:
        return False
    elif not obstacles:
        return True
    return not any((Polygon(o.get_adjusted_hit_box()).crosses(line_of_sight) for o in obstacles))


@lru_cache(maxsize=None)
@njit(['int64, int64, int64'], nogil=True, fastmath=True)
def calculate_circular_area(grid_x, grid_y, max_distance):
    radius = max_distance * 1.6
    observable_area = []
    for x in range(-max_distance, max_distance + 1):
        dist_x = abs(x)
        for y in range(-max_distance, max_distance + 1):
            dist_y = abs(y)
            if dist_x + dist_y < radius:
                observable_area.append((grid_x + x, grid_y + y))
    return observable_area


def clamp(value: Number, maximum: Number, minimum: Number = 0) -> Number:
    """Guarantee that number will by larger than min and less than max."""
    return max(minimum, min(value, maximum))


def average_position_of_points_group(positions: Sequence[Point]) -> Point:
    """
    :param positions: Sequence -- array of Points (x, y)
    :return: Point -- two-dimensional tuple (x, y) representing point
    """
    positions_count = len(positions)
    if positions_count == 1:
        return positions[0]
    sum_x, sum_y = 0, 0
    for position in positions:
        sum_x += position[0]
        sum_y += position[1]
    return sum_x / positions_count, sum_y / positions_count