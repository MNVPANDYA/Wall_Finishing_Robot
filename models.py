import time
import json
import math
from typing import List
from dataclasses import dataclass
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from config import SQLALCHEMY_DATABASE_URL

# Database Setup
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# SQLAlchemy Model
class TrajectoryModel(Base):
    """Enhanced SQLAlchemy model for storing trajectory data."""
    __tablename__ = "trajectories"

    id = Column(Integer, primary_key=True, index=True)
    wall_dimensions = Column(String, nullable=False)
    obstacle_dimensions = Column(String, nullable=True)
    path_points = Column(String, nullable=False)
    coverage_area = Column(Float, nullable=True, default=0.0)
    path_length = Column(Float, nullable=True, default=0.0)
    efficiency = Column(Float, nullable=True, default=0.0)
    creation_time = Column(Integer, default=lambda: int(time.time()), index=True)

# Data Classes
@dataclass
class Point:
    x: float
    y: float
    
    def distance_to(self, other: 'Point') -> float:
        return math.sqrt((self.x - other.x)**2 + (self.y - other.y)**2)

@dataclass
class Rectangle:
    x: float
    y: float
    width: float
    height: float
    
    def contains_point(self, point: Point) -> bool:
        return (self.x <= point.x <= self.x + self.width and 
                self.y <= point.y <= self.y + self.height)
    
    def intersects_horizontal_line(self, y: float, x_start: float, x_end: float) -> bool:
        """Check if horizontal line intersects this rectangle"""
        if not (self.y <= y <= self.y + self.height):
            return False
        return not (x_end <= self.x or x_start >= self.x + self.width)

# Pydantic Models
class Obstacle(BaseModel):
    """Enhanced obstacle with validation"""
    x: float = Field(..., ge=0, description="X coordinate of obstacle's bottom-left corner")
    y: float = Field(..., ge=0, description="Y coordinate of obstacle's bottom-left corner")
    width: float = Field(..., gt=0, description="Width of the obstacle")
    height: float = Field(..., gt=0, description="Height of the obstacle")
    
    def to_rectangle(self) -> Rectangle:
        return Rectangle(self.x, self.y, self.width, self.height)

class CoverageInput(BaseModel):
    """Enhanced input schema with validation"""
    wall_width: float = Field(..., gt=0, le=50, description="Wall width in meters (max 50m)")
    wall_height: float = Field(..., gt=0, le=20, description="Wall height in meters (max 20m)")
    obstacles: List[Obstacle] = Field(default=[], max_items=20, description="Max 20 obstacles")
    tool_width: float = Field(default=0.2, gt=0, le=1.0, description="Tool width in meters")
    
    def validate_obstacles(self) -> bool:
        """Validate obstacles don't overlap and fit within wall"""
        for obs in self.obstacles:
            if obs.x + obs.width > self.wall_width or obs.y + obs.height > self.wall_height:
                raise ValueError(f"Obstacle extends beyond wall boundaries")
        
        # Check for overlapping obstacles
        for i, obs1 in enumerate(self.obstacles):
            for j, obs2 in enumerate(self.obstacles[i+1:], i+1):
                if self._obstacles_overlap(obs1, obs2):
                    raise ValueError(f"Obstacles {i} and {j} overlap")
        return True
    
    def _obstacles_overlap(self, obs1: Obstacle, obs2: Obstacle) -> bool:
        return not (obs1.x + obs1.width <= obs2.x or obs2.x + obs2.width <= obs1.x or
                   obs1.y + obs1.height <= obs2.y or obs2.y + obs2.height <= obs1.y)

class TrajectoryResponse(BaseModel):
    """Enhanced response schema"""
    id: int
    wall_dimensions: dict
    obstacle_dimensions: list
    path_points: list
    coverage_area: float
    path_length: float
    efficiency: float
    total_points: int

# Database Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()