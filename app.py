import time
import json
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

# Local imports
import config
from models import (
    TrajectoryModel, CoverageInput, TrajectoryResponse, 
    Base, engine, get_db
)
from services import (
    generate_advanced_coverage_path,
    calculate_coverage_from_path,
    calculate_path_length_from_points,
    calculate_efficiency
)

# Create database tables
Base.metadata.create_all(bind=engine)

# Initialize FastAPI app
app = FastAPI(
    title=config.API_TITLE,
    description=config.API_DESCRIPTION,
    version=config.API_VERSION
)

# CORS middleware for seperating frontend server
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add timing middleware
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    print(f"Request: {request.method} {request.url.path} - {process_time:.4f}s")
    return response

# Mount static files
app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")

# Routes
@app.get("/")
async def read_index():
    return FileResponse("frontend/index.html")

@app.post("/plan-trajectory/", status_code=201)
def create_advanced_trajectory(payload: CoverageInput, db: Session = Depends(get_db)): 
    """Generate optimized trajectory with advanced path planning and proper tool width storage"""
    try:
        # Validate input  
        payload.validate_obstacles()
        
        print(f"Planning trajectory with tool width: {payload.tool_width}m")
        
        # Generate path with tool width
        path_points, coverage_area, path_length, efficiency = generate_advanced_coverage_path(
            payload.wall_width, 
            payload.wall_height, 
            payload.obstacles,
            payload.tool_width
        )
        
        # Store in database
        wall_dimensions = {
            "width": payload.wall_width, 
            "height": payload.wall_height,
            "tool_width": payload.tool_width
        }
        
        obstacle_data = [obs.dict() for obs in payload.obstacles]
        
        try:
            db_trajectory = TrajectoryModel(
                wall_dimensions=json.dumps(wall_dimensions),
                obstacle_dimensions=json.dumps(obstacle_data),
                path_points=json.dumps(path_points),
                coverage_area=coverage_area,
                path_length=path_length,
                efficiency=efficiency
            )
            
            db.add(db_trajectory)
            db.commit()
            db.refresh(db_trajectory)
            
            print(f"Trajectory {db_trajectory.id} saved with tool width: {payload.tool_width}m")
            
        except Exception as db_error:
            print(f"Database error: {db_error}")
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Database error: {str(db_error)}")
        
        # Return response with calculated metrics
        return {
            "id": db_trajectory.id,
            "wall_dimensions": wall_dimensions,
            "obstacle_dimensions": obstacle_data,
            "path_points": path_points,
            "coverage_area": coverage_area,
            "path_length": path_length,
            "efficiency": efficiency,
            "total_points": len(path_points)
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/trajectories/")
def get_all_trajectories(db: Session = Depends(get_db)):
    """Get all trajectories with enhanced metrics and proper tool width handling"""
    trajectories = db.query(TrajectoryModel).order_by(TrajectoryModel.id.desc()).all()
    
    response_list = []
    for traj in trajectories:
        try:
            wall_dims = json.loads(traj.wall_dimensions)
            obstacle_dims = json.loads(traj.obstacle_dimensions or "[]")
            path_points = json.loads(traj.path_points)
            
            tool_width = wall_dims.get('tool_width', 0.2)
            if 'tool_width' not in wall_dims:
                wall_dims['tool_width'] = tool_width
                print(f"Added missing tool_width {tool_width} for trajectory {traj.id}")
            
            # Calculate metrics if not stored (backward compatibility)
            coverage_area = getattr(traj, 'coverage_area', None)
            if coverage_area is None:
                coverage_area = calculate_coverage_from_path(path_points, tool_width)
            
            path_length = getattr(traj, 'path_length', None)
            if path_length is None:
                path_length = calculate_path_length_from_points(path_points)
            
            efficiency = getattr(traj, 'efficiency', None)
            if efficiency is None:
                efficiency = calculate_efficiency(wall_dims, obstacle_dims, coverage_area)
            
            response_list.append({
                "id": traj.id,
                "wall_dimensions": wall_dims,
                "obstacle_dimensions": obstacle_dims,
                "path_points": path_points,
                "coverage_area": coverage_area,
                "path_length": path_length,
                "efficiency": efficiency,
                "total_points": len(path_points)
            })
            
        except Exception as e:
            print(f"Error processing trajectory {traj.id}: {e}")
            continue
            
    return response_list

@app.get("/trajectories/{trajectory_id}", response_model=TrajectoryResponse)
def get_trajectory_by_id(trajectory_id: int, db: Session = Depends(get_db)):
    """Get specific trajectory with metrics and proper tool width"""
    db_trajectory = db.query(TrajectoryModel).filter(TrajectoryModel.id == trajectory_id).first()
    if db_trajectory is None:
        raise HTTPException(status_code=404, detail="Trajectory not found")

    try:
        wall_dims = json.loads(db_trajectory.wall_dimensions)
        obstacle_dims = json.loads(db_trajectory.obstacle_dimensions or "[]")
        path_points = json.loads(db_trajectory.path_points)
        
        tool_width = wall_dims.get('tool_width', 0.2)
        if 'tool_width' not in wall_dims:
            wall_dims['tool_width'] = tool_width
            print(f"Added missing tool_width {tool_width} for trajectory {trajectory_id}")
        
        # Get stored metrics or calculate if missing
        coverage_area = getattr(db_trajectory, 'coverage_area', None) or calculate_coverage_from_path(path_points, tool_width)
        path_length = getattr(db_trajectory, 'path_length', None) or calculate_path_length_from_points(path_points)
        efficiency = getattr(db_trajectory, 'efficiency', None) or calculate_efficiency(wall_dims, obstacle_dims, coverage_area)

        return TrajectoryResponse(
            id=db_trajectory.id,
            wall_dimensions=wall_dims,
            obstacle_dimensions=obstacle_dims,
            path_points=path_points,
            coverage_area=coverage_area,
            path_length=path_length,
            efficiency=efficiency,
            total_points=len(path_points)
        )
        
    except Exception as e:
        print(f"Error retrieving trajectory {trajectory_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing trajectory: {str(e)}")

@app.get("/trajectories/{trajectory_id}/metrics")
def get_trajectory_metrics(trajectory_id: int, db: Session = Depends(get_db)):
    """Get detailed metrics for a trajectory with enhanced tool width information"""
    db_trajectory = db.query(TrajectoryModel).filter(TrajectoryModel.id == trajectory_id).first()
    if db_trajectory is None:
        raise HTTPException(status_code=404, detail="Trajectory not found")
    
    try:
        wall_dims = json.loads(db_trajectory.wall_dimensions)
        obstacles = json.loads(db_trajectory.obstacle_dimensions or "[]")
        path_points = json.loads(db_trajectory.path_points)
        
        tool_width = wall_dims.get('tool_width', 0.2)
        
        total_wall_area = wall_dims["width"] * wall_dims["height"]
        obstacle_area = sum(obs["width"] * obs["height"] for obs in obstacles)
        available_area = total_wall_area - obstacle_area
        
        # Get stored metrics or calculate
        coverage_area = getattr(db_trajectory, 'coverage_area', None) or calculate_coverage_from_path(path_points, tool_width)
        path_length = getattr(db_trajectory, 'path_length', None) or calculate_path_length_from_points(path_points)
        efficiency = getattr(db_trajectory, 'efficiency', None) or calculate_efficiency(wall_dims, obstacles, coverage_area)
        
        return {
            "trajectory_id": trajectory_id,
            "total_wall_area": total_wall_area,
            "obstacle_area": obstacle_area,
            "available_area": available_area,
            "coverage_area": coverage_area,
            "path_length": path_length,
            "efficiency": efficiency,
            "coverage_percentage": (coverage_area / available_area) * 100 if available_area > 0 else 0,
            "path_density": path_length / total_wall_area if total_wall_area > 0 else 0,
            "tool_width": tool_width,
            "tool_coverage_per_pass": tool_width,
            "estimated_time_per_meter": 2.0,  # seconds per meter
            "estimated_total_time": path_length * 2.0  # rough estimate
        }
        
    except Exception as e:
        print(f"Error calculating metrics for trajectory {trajectory_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error calculating metrics: {str(e)}")

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": time.time()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)