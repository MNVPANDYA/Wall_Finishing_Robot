document.addEventListener("DOMContentLoaded", () => {
  // --- DOM Elements ---
  const planBtn = document.getElementById("plan-btn");
  const visualizeBtn = document.getElementById("visualize-btn");
  const addObstacleBtn = document.getElementById("add-obstacle-btn");
  const obstaclesListDiv = document.getElementById("obstacles-list");
  const trajectoriesSelect = document.getElementById("trajectories-select");
  const canvas = document.getElementById("drawing-canvas");
  const statusMessage = document.getElementById("status-message");

  let obstacleCounter = 0;
  let currentAnimation = null;

  // --- Utility Functions ---

  /**
   * Converts robot coordinates (bottom-left origin) to SVG coordinates (top-left origin)
   */
  const robotToSvg = (x, y, wallHeight) => {
    return [x, wallHeight - y];
  };

  // --- API Functions ---

  /**
   * Fetches all existing trajectories and populates the dropdown.
   */
  const fetchTrajectories = async () => {
    try {
      const response = await fetch("/trajectories/");
      if (!response.ok) throw new Error("Failed to fetch trajectories");
      const trajectories = await response.json();

      trajectoriesSelect.innerHTML = ""; // Clear existing options
      if (trajectories.length === 0) {
        trajectoriesSelect.innerHTML = "<option>No plans available</option>";
        return;
      }
      trajectories.forEach((t) => {
        const option = document.createElement("option");
        option.value = t.id;
        const toolWidth = t.wall_dimensions.tool_width || 0.2;
        option.textContent = `Plan ID: ${t.id} (${t.wall_dimensions.width}x${t.wall_dimensions.height}m, Tool: ${toolWidth}m)`;
        trajectoriesSelect.appendChild(option);
      });
    } catch (error) {
      console.error("Error:", error);
      statusMessage.textContent = `Error: ${error.message}`;
    }
  };

  // --- Drawing Functions ---

  /**
   * Clears and sets up the SVG canvas with wall and obstacles.
   */
  const drawEnvironment = (data) => {
    canvas.innerHTML = ""; // Clear previous drawings
    const { wall_dimensions, obstacle_dimensions } = data;
    const toolWidth = wall_dimensions.tool_width || 0.2;

    // Set SVG viewbox for automatic scaling
    canvas.setAttribute(
      "viewBox",
      `0 0 ${wall_dimensions.width} ${wall_dimensions.height}`
    );

    // Draw Wall background
    const wall = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    wall.setAttribute("x", 0);
    wall.setAttribute("y", 0);
    wall.setAttribute("width", wall_dimensions.width);
    wall.setAttribute("height", wall_dimensions.height);
    wall.setAttribute("class", "wall");
    canvas.appendChild(wall);

    // Draw Obstacles as solid blocks
    obstacle_dimensions.forEach((obs, index) => {
      // Convert obstacle coordinates from robot space to SVG space
      const [svgX, svgY] = robotToSvg(
        obs.x,
        obs.y + obs.height,
        wall_dimensions.height
      );

      // Main obstacle rectangle - solid design
      const obstacleRect = document.createElementNS(
        "http://www.w3.org/2000/svg",
        "rect"
      );
      obstacleRect.setAttribute("x", svgX);
      obstacleRect.setAttribute("y", svgY);
      obstacleRect.setAttribute("width", obs.width);
      obstacleRect.setAttribute("height", obs.height);
      obstacleRect.setAttribute("fill", "#dc2626"); // Solid red
      obstacleRect.setAttribute("stroke", "#991b1b"); // Darker red border
      obstacleRect.setAttribute("stroke-width", "0.02");
      canvas.appendChild(obstacleRect);

      // Add obstacle label with positioning
      const label = document.createElementNS(
        "http://www.w3.org/2000/svg",
        "text"
      );
      label.setAttribute("x", svgX + obs.width / 2);
      label.setAttribute("y", svgY + obs.height / 2);
      label.setAttribute("text-anchor", "middle");
      label.setAttribute("dominant-baseline", "middle");
      label.setAttribute("fill", "white");
      label.setAttribute("font-weight", "bold");
      label.setAttribute("font-family", "Arial, sans-serif");

      // Dynamic font size based on obstacle size
      const fontSize = Math.min(0.15, obs.height * 0.3, obs.width * 0.25);
      label.setAttribute("font-size", fontSize.toString());
      label.textContent = `Obs${index + 1}`;
      canvas.appendChild(label);
    });

    // Add coordinate system indicators
    const origin = document.createElementNS(
      "http://www.w3.org/2000/svg",
      "circle"
    );
    origin.setAttribute("cx", 0);
    origin.setAttribute("cy", wall_dimensions.height);
    origin.setAttribute("r", "0.08");
    origin.setAttribute("fill", "#ef4444");
    origin.setAttribute("stroke", "#dc2626");
    origin.setAttribute("stroke-width", "0.02");
    canvas.appendChild(origin);

    const originLabel = document.createElementNS(
      "http://www.w3.org/2000/svg",
      "text"
    );
    originLabel.setAttribute("x", 0.15);
    originLabel.setAttribute("y", wall_dimensions.height - 0.05);
    originLabel.setAttribute("font-size", "0.12");
    originLabel.setAttribute("fill", "#dc2626");
    originLabel.setAttribute("font-weight", "bold");
    originLabel.textContent = "(0,0)";
    canvas.appendChild(originLabel);

    // Add tool width indicator in corner
    const toolWidthIndicator = document.createElementNS(
      "http://www.w3.org/2000/svg",
      "text"
    );
    toolWidthIndicator.setAttribute("x", wall_dimensions.width - 0.1);
    toolWidthIndicator.setAttribute("y", 0.2);
    toolWidthIndicator.setAttribute("text-anchor", "end");
    toolWidthIndicator.setAttribute("font-size", "0.12");
    toolWidthIndicator.setAttribute("fill", "#0369a1");
    toolWidthIndicator.setAttribute("font-weight", "bold");
    toolWidthIndicator.textContent = `Tool: ${toolWidth}m`;
    canvas.appendChild(toolWidthIndicator);

    // Add sweep line visualization (show where robot will paint)
    const sweepLines = [];
    let y = toolWidth / 2;
    while (y <= wall_dimensions.height - toolWidth / 2) {
      const sweepLine = document.createElementNS(
        "http://www.w3.org/2000/svg",
        "line"
      );
      sweepLine.setAttribute("x1", "0");
      sweepLine.setAttribute("y1", wall_dimensions.height - y);
      sweepLine.setAttribute("x2", wall_dimensions.width);
      sweepLine.setAttribute("y2", wall_dimensions.height - y);
      sweepLine.setAttribute("stroke", "#16a34a");
      sweepLine.setAttribute("stroke-width", "0.008");
      sweepLine.setAttribute("stroke-dasharray", "0.04,0.04");
      sweepLine.setAttribute("opacity", "0.4");
      canvas.appendChild(sweepLine);
      y += toolWidth;
    }
  };

  // --- Animation Functions ---

  /**
   * Determines if the robot should be painting between two points
   */
  const shouldPaint = (point1, point2, allPoints, currentIndex, obstacles) => {
    const [x1, y1] = point1;
    const [x2, y2] = point2;

    // If it's a vertical movement (Y changes significantly), don't paint
    if (Math.abs(y1 - y2) > 0.15) {
      return false;
    }

    // If it's not on the same horizontal line, don't paint
    if (Math.abs(y1 - y2) > 0.01) {
      return false;
    }

    // Check if this is a jump over an obstacle
    const distance = Math.abs(x2 - x1);
    if (distance > 0.3) {
      // Large horizontal jump likely means obstacle avoidance
      return false;
    }

    // If we're moving horizontally on the same Y level with small steps, we're painting
    return Math.abs(y1 - y2) < 0.01 && distance > 0.01;
  };

  /**
   * Animates the robot's path on the canvas with proper tool size visualization.
   */
  const animatePath = (points, wallHeight, toolWidth = 0.2) => {
    // Stop any existing animation
    if (currentAnimation) {
      clearTimeout(currentAnimation);
    }

    // Convert all points to SVG coordinates
    const svgPoints = points.map(([x, y]) => robotToSvg(x, y, wallHeight));

    // Create robot group with properly sized tool indicator
    const robotGroup = document.createElementNS(
      "http://www.w3.org/2000/svg",
      "g"
    );

    // Robot center point - small fixed size
    const robot = document.createElementNS(
      "http://www.w3.org/2000/svg",
      "circle"
    );
    robot.setAttribute("class", "robot-center");
    robot.setAttribute("r", "0.05");
    robot.setAttribute("fill", "#f97316");
    robot.setAttribute("stroke", "#ea580c");
    robot.setAttribute("stroke-width", "0.02");
    robotGroup.appendChild(robot);

    // Tool coverage area - size matches user input
    const toolIndicator = document.createElementNS(
      "http://www.w3.org/2000/svg",
      "rect"
    );
    toolIndicator.setAttribute("fill", "rgba(249, 115, 22, 0.3)");
    toolIndicator.setAttribute("stroke", "#f97316");
    toolIndicator.setAttribute("stroke-width", "0.015");
    toolIndicator.setAttribute("stroke-dasharray", "0.03,0.02");
    toolIndicator.setAttribute("width", toolWidth.toString());
    toolIndicator.setAttribute("height", toolWidth.toString());
    toolIndicator.setAttribute("rx", "0.02"); // Slightly rounded corners
    robotGroup.appendChild(toolIndicator);

    canvas.appendChild(robotGroup);

    // Create robot trail (movement path - dotted line)
    const movementPath = document.createElementNS(
      "http://www.w3.org/2000/svg",
      "polyline"
    );
    movementPath.setAttribute("fill", "none");
    movementPath.setAttribute("stroke", "#64748b");
    movementPath.setAttribute("stroke-width", "0.015");
    movementPath.setAttribute("stroke-dasharray", "0.05,0.05");
    movementPath.setAttribute("opacity", "0.6");
    canvas.appendChild(movementPath);

    let i = 0;
    let currentPaintSegment = null;
    const speed = 120; // Milliseconds between points

    function drawNextPoint() {
      if (i < svgPoints.length) {
        const [x, y] = svgPoints[i];
        const [robotX, robotY] = points[i];

        // Update robot center position
        robot.setAttribute("cx", x);
        robot.setAttribute("cy", y);

        // Update tool indicator position (centered on robot)
        toolIndicator.setAttribute("x", x - toolWidth / 2);
        toolIndicator.setAttribute("y", y - toolWidth / 2);

        // Add to movement trail
        const currentTrail = movementPath.getAttribute("points") || "";
        movementPath.setAttribute("points", currentTrail + ` ${x},${y}`);

        // Determine if we should be painting
        if (i > 0) {
          const shouldBePainting = shouldPaint(
            points[i - 1],
            points[i],
            points,
            i
          );

          if (shouldBePainting) {
            // Continue or start a new paint segment
            if (!currentPaintSegment) {
              currentPaintSegment = document.createElementNS(
                "http://www.w3.org/2000/svg",
                "polyline"
              );
              currentPaintSegment.setAttribute("class", "robot-path");
              currentPaintSegment.setAttribute("fill", "none");
              currentPaintSegment.setAttribute("stroke", "#0369a1");
              currentPaintSegment.setAttribute(
                "stroke-width",
                (toolWidth * 12).toString()
              );
              currentPaintSegment.setAttribute("stroke-linecap", "round");
              currentPaintSegment.setAttribute("stroke-linejoin", "round");
              currentPaintSegment.setAttribute("opacity", "0.8");
              currentPaintSegment.setAttribute(
                "points",
                `${svgPoints[i - 1][0]},${svgPoints[i - 1][1]}`
              );
              canvas.appendChild(currentPaintSegment);
            }

            // Add current point to paint segment
            const currentPaintPoints =
              currentPaintSegment.getAttribute("points");
            currentPaintSegment.setAttribute(
              "points",
              currentPaintPoints + ` ${x},${y}`
            );
          } else {
            // Stop painting (vertical movement or jump over obstacle)
            currentPaintSegment = null;
          }
        }

        // Update status with robot coordinates and action
        const action =
          i > 0 && shouldPaint(points[i - 1], points[i], points, i)
            ? "🎨 PAINTING"
            : "🚶 MOVING";
        statusMessage.textContent = `${action} - Robot at (${robotX.toFixed(
          2
        )}, ${robotY.toFixed(2)}) - Point ${i + 1}/${
          points.length
        } - Tool: ${toolWidth}m`;

        i++;
        currentAnimation = setTimeout(drawNextPoint, speed);
      } else {
        statusMessage.textContent = `✅ Playback complete! Total path points: ${points.length} (Tool width: ${toolWidth}m)`;
      }
    }

    statusMessage.textContent = "🚀 Starting visualization...";
    drawNextPoint();
  };

  // --- Planning Functions ---

  /**
   * Gathers input, sends it to the backend to plan a new trajectory.
   */
  const planNewTrajectory = async () => {
    const wall_width = parseFloat(document.getElementById("wall-width").value);
    const wall_height = parseFloat(
      document.getElementById("wall-height").value
    );
    const tool_width = parseFloat(document.getElementById("tool-width").value);

    const obstacles = [];
    document.querySelectorAll(".obstacle-entry").forEach((entry) => {
      const x = parseFloat(entry.querySelector('[name="obs-x"]').value);
      const y = parseFloat(entry.querySelector('[name="obs-y"]').value);
      const width = parseFloat(entry.querySelector('[name="obs-width"]').value);
      const height = parseFloat(
        entry.querySelector('[name="obs-height"]').value
      );

      if (!isNaN(x) && !isNaN(y) && !isNaN(width) && !isNaN(height)) {
        obstacles.push({ x, y, width, height });
      }
    });

    if (
      isNaN(wall_width) ||
      isNaN(wall_height) ||
      isNaN(tool_width) ||
      wall_width <= 0 ||
      wall_height <= 0 ||
      tool_width <= 0
    ) {
      alert("Please enter valid dimensions (positive numbers).");
      return;
    }

    const payload = { wall_width, wall_height, obstacles, tool_width };
    statusMessage.textContent = "⚙️ Planning trajectory...";

    try {
      const response = await fetch("/plan-trajectory/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Server error ${response.status}: ${errorText}`);
      }

      const newData = await response.json();
      statusMessage.textContent = `✅ New plan created with ID: ${
        newData.id
      } (Coverage: ${newData.coverage_area.toFixed(2)}m², Efficiency: ${(
        newData.efficiency * 100
      ).toFixed(1)}%)`;

      drawEnvironment(newData);
      animatePath(
        newData.path_points,
        newData.wall_dimensions.height,
        newData.wall_dimensions.tool_width
      );

      fetchTrajectories(); // Refresh the dropdown
    } catch (error) {
      console.error("Error:", error);
      statusMessage.textContent = `❌ Error: ${error.message}`;
    }
  };

  // --- UI Management Functions ---

  /**
   * Adds a set of input fields for an obstacle.
   */
  const addObstacleInput = () => {
    obstacleCounter++;
    const newObstacleDiv = document.createElement("div");
    newObstacleDiv.className = "obstacle-entry";
    newObstacleDiv.innerHTML = `
      <span>#${obstacleCounter}:</span>
      <label>X:</label><input type="number" name="obs-x" value="1" step="0.1" min="0">
      <label>Y:</label><input type="number" name="obs-y" value="1" step="0.1" min="0">
      <label>W:</label><input type="number" name="obs-width" value="0.5" step="0.1" min="0.1">
      <label>H:</label><input type="number" name="obs-height" value="0.5" step="0.1" min="0.1">
      <button type="button" onclick="this.parentElement.remove()" style="background-color: #dc3545; color: white; padding: 4px 8px; border-radius: 4px; border: none; cursor: pointer;">Remove</button>
    `;
    obstaclesListDiv.appendChild(newObstacleDiv);
  };

  // --- Event Listeners ---
  planBtn.addEventListener("click", planNewTrajectory);

  visualizeBtn.addEventListener("click", async () => {
    const selectedId = trajectoriesSelect.value;
    if (!selectedId || isNaN(selectedId)) {
      alert("Please select a valid plan to visualize.");
      return;
    }

    statusMessage.textContent = `📋 Loading plan ID: ${selectedId}...`;

    try {
      const response = await fetch(`/trajectories/${selectedId}`);
      if (!response.ok) {
        throw new Error(`Could not load trajectory: ${response.status}`);
      }

      const data = await response.json();
      drawEnvironment(data);
      const toolWidth = data.wall_dimensions.tool_width || 0.2;
      animatePath(data.path_points, data.wall_dimensions.height, toolWidth);
    } catch (error) {
      console.error("Error:", error);
      statusMessage.textContent = `❌ Error: ${error.message}`;
    }
  });

  addObstacleBtn.addEventListener("click", addObstacleInput);

  // --- Initial Load ---
  fetchTrajectories();
  addObstacleInput(); // Start with one obstacle entry by default
});
