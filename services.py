import math
from typing import List, Tuple
from models import Point, Rectangle, Obstacle

class WallFinishingPlanner:
    """Advanced path planner for wall-finishing robots with continuous movement"""
    
    def __init__(self, wall_width: float, wall_height: float, 
                 obstacles: List[Rectangle], tool_width: float = 0.2):
        self.wall_width = wall_width
        self.wall_height = wall_height
        self.obstacles = obstacles
        self.tool_width = tool_width
        self.path: List[Point] = []
        self.coverage_segments: List[Tuple[float, float, float]] = []
        
        # Consistent parameter definitions
        self.tool_radius = tool_width / 2.0  # Tool extends this much from robot center
        self.base_clearance = 0.05  # Base 5cm clearance for safety
        self.safety_margin = self.tool_radius + self.base_clearance  # Total safety margin around obstacles
        self.min_gap_width = tool_width + 2 * self.base_clearance  # Minimum navigable gap
        
        # Movement precision thresholds
        self.position_tolerance = 0.01  # 1cm tolerance for position comparisons
        self.vertical_movement_threshold = self.position_tolerance  # When to consider movement vertical vs horizontal
        
        # Path validation parameters
        self.min_paint_distance = self.position_tolerance  # Minimum distance to consider painting
        self.max_reasonable_paint_distance = 2.0  # Maximum reasonable painting distance in one segment
        self.sweep_line_overlap_factor = 0.1  # 10% overlap factor for final sweep line
        
        print(f"Tool configuration:")
        print(f"  - Tool width: {tool_width}m, Tool radius: {self.tool_radius}m")
        print(f"  - Base clearance: {self.base_clearance}m")
        print(f"  - Safety margin: {self.safety_margin}m")
        print(f"  - Min gap width: {self.min_gap_width}m")
        print(f"  - Position tolerance: {self.position_tolerance}m")

    
    def plan_coverage_path(self) -> Tuple[List[Tuple[float, float]], float, float]:
        """Generate continuous coverage path with proper obstacle navigation"""
        self.path = []
        self.coverage_segments = []
        
        # Calculate sweep lines
        y_positions = self._calculate_sweep_lines()
        
        direction = 1  # 1 for left-to-right, -1 for right-to-left
        current_x = 0  # Track robot's current X position
        
        for i, y in enumerate(y_positions):
            # Get free segments for current sweep line
            free_segments = self._get_free_segments(y)
            
            if not free_segments:
                # If no free segments, move vertically to next level
                if i < len(y_positions) - 1:
                    next_y = y_positions[i + 1]
                    self._add_vertical_movement(current_x, y, next_y)
                direction *= -1
                continue
            
            # Process segments with proper inter-segment navigation
            if direction == 1:
                # Left to right direction
                free_segments.sort(key=lambda seg: seg[0])
                current_x = self._process_segments_left_to_right(free_segments, y, current_x)
            else:
                # Right to left direction
                free_segments.sort(key=lambda seg: seg[1], reverse=True)
                current_x = self._process_segments_right_to_left(free_segments, y, current_x)
            
            # Move to next sweep line
            if i < len(y_positions) - 1:
                next_y = y_positions[i + 1]
                self._add_vertical_movement(current_x, y, next_y)
            
            # Alternate direction
            direction *= -1
        
        # Calculate metrics
        path_points = [(p.x, p.y) for p in self.path]
        coverage_area = self._calculate_coverage_area()
        path_length = self._calculate_path_length()
        
        return path_points, coverage_area, path_length
    
    def _process_segments_left_to_right(self, segments: List[Tuple[float, float]], 
                                      y: float, start_x: float) -> float:
        """Process segments from left to right, ensuring proper navigation between segments"""
        current_x = start_x
        
        for seg_idx, (seg_start, seg_end) in enumerate(segments):
            # Navigate to start of segment if we're not already there
            if abs(current_x - seg_start) > self.position_tolerance:
                # Check if direct horizontal path is blocked
                path_to_segment = self._find_horizontal_path(current_x, seg_start, y)
                self.path.extend(path_to_segment)
                current_x = seg_start
            
            # Ensure we're at the correct position to start painting
            if (len(self.path) == 0 or 
                abs(self.path[-1].x - seg_start) > self.position_tolerance or 
                abs(self.path[-1].y - y) > self.position_tolerance):
                self.path.append(Point(seg_start, y))
            
            # Paint across the segment
            self.path.append(Point(seg_end, y))
            self.coverage_segments.append((y, seg_start, seg_end))
            current_x = seg_end
        
        return current_x
    
    def _process_segments_right_to_left(self, segments: List[Tuple[float, float]], 
                                       y: float, start_x: float) -> float:
        """Process segments from right to left, ensuring proper navigation between segments"""
        current_x = start_x
        
        for seg_idx, (seg_start, seg_end) in enumerate(segments):
            # Navigate to end of segment (right side first for right-to-left)
            if abs(current_x - seg_end) > self.position_tolerance:
                # Check if direct horizontal path is blocked
                path_to_segment = self._find_horizontal_path(current_x, seg_end, y)
                self.path.extend(path_to_segment)
                current_x = seg_end
            
            # Ensure we're at the correct position to start painting
            if (len(self.path) == 0 or 
                abs(self.path[-1].x - seg_end) > self.position_tolerance or 
                abs(self.path[-1].y - y) > self.position_tolerance):
                self.path.append(Point(seg_end, y))
            
            # Paint across the segment (right to left)
            self.path.append(Point(seg_start, y))
            self.coverage_segments.append((y, seg_start, seg_end))
            current_x = seg_start
        
        return current_x
    
    def _find_horizontal_path(self, start_x: float, end_x: float, y: float) -> List[Point]:
        """Find horizontal path between two X coordinates at the same Y level"""
        if abs(start_x - end_x) < self.position_tolerance:
            return []
        
        # Check if direct horizontal path is clear
        if self._is_horizontal_path_clear(start_x, end_x, y):
            return [Point(end_x, y)]
        
        # Find the first blocking obstacle
        blocking_obstacles = self._find_blocking_obstacles_for_horizontal_path(start_x, end_x, y)
        
        if not blocking_obstacles:
            return [Point(end_x, y)]
        
        # Use simple single obstacle navigation for the first blocking obstacle
        waypoints = self._navigate_around_single_obstacle(start_x, end_x, y, blocking_obstacles[0])
        return waypoints
    
    def _navigate_around_single_obstacle(self, start_x: float, end_x: float, y: float, 
                                       obstacle: Rectangle) -> List[Point]:
        """Navigate around a single obstacle using consistent safety margins"""
        waypoints = []
        expanded_obs = Rectangle(
            obstacle.x - self.safety_margin,
            obstacle.y - self.safety_margin,
            obstacle.width + 2 * self.safety_margin,
            obstacle.height + 2 * self.safety_margin
        )
        
        # Choose detour direction (above or below obstacle)
        space_above = self.wall_height - (expanded_obs.y + expanded_obs.height)
        space_below = expanded_obs.y
        
        # Determine detour Y coordinate
        detour_y = None
        
        if space_above > self.safety_margin and space_below > self.safety_margin:
            # Both directions available - choose based on robot position
            if y > (obstacle.y + obstacle.height / 2):
                # Robot is above obstacle center - go above
                detour_y = min(self.wall_height - self.tool_radius, 
                              expanded_obs.y + expanded_obs.height + self.base_clearance)
            else:
                # Robot is below obstacle center - go below
                detour_y = max(self.tool_radius, expanded_obs.y - self.base_clearance)
        elif space_above > self.safety_margin:
            # Only above available
            detour_y = min(self.wall_height - self.tool_radius, 
                          expanded_obs.y + expanded_obs.height + self.base_clearance)
        elif space_below > self.safety_margin:
            # Only below available
            detour_y = max(self.tool_radius, expanded_obs.y - self.base_clearance)
        
        if detour_y is not None:
            # Use only horizontal + vertical movements
            # 1. Move vertically to detour level
            waypoints.append(Point(start_x, detour_y))
            # 2. Move horizontally to destination X
            waypoints.append(Point(end_x, detour_y))
            # 3. Move vertically back to target Y
            waypoints.append(Point(end_x, y))
        else:
            # No vertical detour possible - try horizontal detour
            if start_x < end_x:
                # Moving right - try to go around right side of obstacle
                if expanded_obs.x + expanded_obs.width < self.wall_width - self.tool_radius:
                    detour_x = expanded_obs.x + expanded_obs.width + self.base_clearance
                    waypoints.append(Point(detour_x, y))
            else:
                # Moving left - try to go around left side of obstacle
                if expanded_obs.x > self.tool_radius:
                    detour_x = expanded_obs.x - self.base_clearance
                    waypoints.append(Point(detour_x, y))
        
        return waypoints
    
    def _add_vertical_movement(self, x: float, from_y: float, to_y: float):
        """Add vertical movement from one Y coordinate to another"""
        if abs(from_y - to_y) > self.position_tolerance:
            self.path.append(Point(x, to_y))
    
    def _is_horizontal_path_clear(self, start_x: float, end_x: float, y: float) -> bool:
        """Check if horizontal path at Y level is clear of obstacles"""
        min_x, max_x = min(start_x, end_x), max(start_x, end_x)
        
        for obstacle in self.obstacles:
            expanded_obs = Rectangle(
                obstacle.x - self.safety_margin,
                obstacle.y - self.safety_margin,
                obstacle.width + 2 * self.safety_margin,
                obstacle.height + 2 * self.safety_margin
            )
            
            # Check if obstacle intersects with horizontal line
            if (expanded_obs.y <= y <= expanded_obs.y + expanded_obs.height and
                not (max_x <= expanded_obs.x or min_x >= expanded_obs.x + expanded_obs.width)):
                return False
        
        return True
    
    def _find_blocking_obstacles_for_horizontal_path(self, start_x: float, end_x: float, y: float) -> List[Rectangle]:
        """Find obstacles that block horizontal movement between start_x and end_x at Y level"""
        blocking = []
        min_x, max_x = min(start_x, end_x), max(start_x, end_x)
        
        for obstacle in self.obstacles:
            expanded_obs = Rectangle(
                obstacle.x - self.safety_margin,
                obstacle.y - self.safety_margin,
                obstacle.width + 2 * self.safety_margin,
                obstacle.height + 2 * self.safety_margin
            )
            
            # Check if obstacle blocks the horizontal path
            if (expanded_obs.y <= y <= expanded_obs.y + expanded_obs.height and
                not (max_x <= expanded_obs.x or min_x >= expanded_obs.x + expanded_obs.width)):
                blocking.append(obstacle)
        
        return blocking
    
    def _calculate_sweep_lines(self) -> List[float]:
        """Calculate Y positions for sweep lines based on tool width"""
        sweep_lines = []
        y = self.tool_radius  # Start at tool radius from bottom (centered tool coverage)
        
        while y <= self.wall_height - self.tool_radius:
            sweep_lines.append(y)
            y += self.tool_width  # Move by full tool width each time
        
        # Add final line if needed to ensure complete coverage
        if sweep_lines and sweep_lines[-1] < self.wall_height - self.tool_radius:
            final_y = self.wall_height - self.tool_radius
            if final_y > sweep_lines[-1] + self.tool_width * self.sweep_line_overlap_factor:
                sweep_lines.append(final_y)
        
        return sweep_lines
    
    def _get_free_segments(self, y: float) -> List[Tuple[float, float]]:
        """Get free segments on horizontal line y"""
        segments = [(0.0, self.wall_width)]
        
        # Remove obstacle intersections
        for obstacle in self.obstacles:
            # Add safety margin
            expanded_obs = Rectangle(
                max(0, obstacle.x - self.safety_margin),
                obstacle.y - self.safety_margin,
                min(self.wall_width, obstacle.width + 2 * self.safety_margin),
                obstacle.height + 2 * self.safety_margin
            )
            
            new_segments = []
            for start_x, end_x in segments:
                if expanded_obs.intersects_horizontal_line(y, start_x, end_x):
                    # Split segment around obstacle
                    if start_x < expanded_obs.x:
                        new_segments.append((start_x, min(expanded_obs.x, end_x)))
                    if expanded_obs.x + expanded_obs.width < end_x:
                        new_segments.append((max(expanded_obs.x + expanded_obs.width, start_x), end_x))
                else:
                    new_segments.append((start_x, end_x))
            
            segments = new_segments
        
        # Filter segments that are too small for the robot to navigate
        segments = [(s, e) for s, e in segments if e - s >= self.min_gap_width]
        
        return segments
    
    def _calculate_coverage_area(self) -> float:
        """Calculate total coverage area"""
        total_area = 0.0
        for y, x_start, x_end in self.coverage_segments:
            segment_length = x_end - x_start
            total_area += segment_length * self.tool_width
        return total_area
    
    def _calculate_path_length(self) -> float:
        """Calculate total path length"""
        if len(self.path) < 2:
            return 0.0
        
        total_length = 0.0
        for i in range(1, len(self.path)):
            total_length += self.path[i-1].distance_to(self.path[i])
        
        return total_length

def generate_advanced_coverage_path(
    wall_width: float,
    wall_height: float,
    obstacles: List[Obstacle],
    tool_width: float = 0.2,
) -> Tuple[List[Tuple[float, float]], float, float, float]:
    """
    Generate advanced coverage path with proper obstacle avoidance
    Returns: (path_points, coverage_area, path_length, efficiency)
    """
    # Convert obstacles to rectangles
    obstacle_rects = [obs.to_rectangle() for obs in obstacles]
    
    # Create planner and generate path
    planner = WallFinishingPlanner(wall_width, wall_height, obstacle_rects, tool_width)
    path_points, coverage_area, path_length = planner.plan_coverage_path()
    
    # Calculate efficiency (coverage area / total wall area)
    total_wall_area = wall_width * wall_height
    obstacle_area = sum(obs.width * obs.height for obs in obstacles)
    available_area = total_wall_area - obstacle_area
    efficiency = coverage_area / available_area if available_area > 0 else 0.0
    
    return path_points, coverage_area, path_length, efficiency

# Utility Functions
def calculate_coverage_from_path(path_points: List[tuple], tool_width: float = 0.2) -> float:
    """Calculate coverage area from path points"""
    if len(path_points) < 2:
        return 0.0
    
    # Use consistent parameters
    position_tolerance = 0.01
    max_reasonable_paint_distance = 2.0
    
    total_coverage = 0.0
    for i in range(1, len(path_points)):
        x1, y1 = path_points[i-1]
        x2, y2 = path_points[i]
        
        # Only count horizontal movements as painting
        if abs(y1 - y2) < position_tolerance:  
            distance = abs(x2 - x1)
            # Only count reasonable painting distances
            if position_tolerance < distance < max_reasonable_paint_distance:
                total_coverage += distance * tool_width
    
    return total_coverage

def calculate_path_length_from_points(path_points: List[tuple]) -> float:
    """Calculate total path length"""
    if len(path_points) < 2:
        return 0.0
    
    total_length = 0.0
    for i in range(1, len(path_points)):
        x1, y1 = path_points[i-1]
        x2, y2 = path_points[i]
        distance = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
        total_length += distance
    
    return total_length

def calculate_efficiency(wall_dims: dict, obstacle_dims: List[dict], coverage_area: float) -> float:
    """Calculate efficiency ratio"""
    total_wall_area = wall_dims['width'] * wall_dims['height']
    obstacle_area = sum(obs['width'] * obs['height'] for obs in obstacle_dims)
    available_area = total_wall_area - obstacle_area
    return coverage_area / available_area if available_area > 0 else 0.0