# PHOEBE Lab UI Architecture Documentation

## Overview

PHOEBE Lab UI is a web-based educational interface for the [PHOEBE](https://phoebe-project.org) stellar modeling software. The system provides an interactive environment for students to explore binary star parameters and visualize their effects on light curves and radial velocity curves.

## System Architecture

The application follows a **multi-layered distributed architecture** with clear separation of concerns:

<div align="center">

| Web Browser (Client)
|:---------------------:|
| NiceGUI Frontend
| FastAPI Web Layer
| Session Manager
| ZeroMQ Communication
| PHOEBE Servers
| Python PHOEBE Backend

</div>

## Directory Structure

### `/ui/` - User Interface Layer

**Purpose**: Web-based frontend built with NiceGUI framework

- **`phoebe_ui.py`** - Main UI application class
  - **`PhoebeUI`** - Primary application class managing the entire interface
  - **`PhoebeAdjustableParameterWidget`** - Individual parameter controls with adjustable checkboxes
  - **`PhoebeParameterWidget`** - Basic parameter display/input widgets
  - **`DatasetModel`** - Data management for light curve and RV datasets

- **`dash_ui.py`** - Main UI admin class
- **`utils.py`** - Utility functions for data processing
  - `time_to_phase()` - Convert time values to orbital phases
  - `alias_data()` - Extend phase data for better visualization
  - `flux_to_magnitude()` - Convert flux measurements to magnitudes

**Key Features**:

- **Interactive Parameter Panel**: Real-time parameter adjustment with immediate validation
- **Dataset Management**: Add/remove/configure light curve and radial velocity datasets  
- **Model Computation**: Trigger PHOEBE model calculations with current parameters
- **Data Visualization**: Plotly-based plotting of light curves, RV curves, and model fits
- **Model Fitting**: Solver integration for automated parameter fitting with solution adoption
- **Session Dashboard**: Controlling sessions from the admin user interface

### `/api/` - Web API Layer

**Purpose**: FastAPI-based REST API serving as the web interface layer

- **`main.py`** - FastAPI application entry point
- **`routes/`** - API endpoint definitions
  - **`session.py`** - Session management endpoints (login, status, etc.)
  - **`dash.py`** - Administrative dashboard endpoints

- **`services/`** - Business logic services
  - **`server_proxy.py`** - Proxy for communicating with PHOEBE servers

**Architecture Role**: Provides HTTP endpoints for the frontend, handles session routing, and manages communication with the session manager layer.

### `/client/` - API Client Layer

**Purpose**: Python client libraries for interacting with the system APIs

- **`session_api.py`** - Session management client
  - Handles user login/logout
  - Manages session lifecycle
  - Routes requests to appropriate PHOEBE server instances

- **`phoebe_api.py`** - PHOEBE operations client  
  - Parameter get/set operations
  - Model computation requests
  - Dataset management
  - Solver operations

**Design Pattern**: These clients abstract the HTTP API calls and provide a clean Python interface for the UI layer to interact with backend services.

### `/manager/` - Session Management Layer

**Purpose**: Central coordinator managing user sessions and PHOEBE server instances

- **`session_manager.py`** - Core session management logic
  - **`SessionManager`** class - Manages user sessions and server allocation
  - **User Session Tracking** - Maps users to dedicated PHOEBE server instances
  - **Server Pool Management** - Maintains pool of available PHOEBE servers
  - **Load Balancing** - Assigns users to least-loaded servers

- **`config.toml`** - Configuration file for session manager settings

**Responsibilities**:

- **Session Lifecycle**: Create, maintain, and cleanup user sessions
- **Resource Allocation**: Assign dedicated PHOEBE servers to users
- **State Persistence**: Maintain session state across browser disconnections
- **Scalability**: Support multiple concurrent users with proper resource isolation

### `/server/` - PHOEBE Computation Layer

**Purpose**: ZeroMQ-based servers running actual PHOEBE computations

- **`server.py`** - Main PHOEBE server implementation
  - **`PhoebeServer`** class - ZeroMQ server handling PHOEBE operations
  - **Command Registry** - Maps API commands to PHOEBE bundle operations
  - **Bundle Management** - Maintains PHOEBE bundle state for each session

**PHOEBE Integration**:

- **Bundle Operations**: Direct interface to PHOEBE's bundle API
- **Parameter Management**: Set/get stellar and orbital parameters
- **Model Computation**: Execute PHOEBE's numerical models
- **Solver Integration**: Run parameter fitting algorithms
- **Dataset Handling**: Manage observational data and synthetic datasets

**Communication Protocol**: Uses ZeroMQ for high-performance, asynchronous communication with the session manager.

### `/common/` - Shared Utilities

**Purpose**: Common code shared across all layers

- **Serialization utilities** - JSON serialization for complex PHOEBE objects
- **Data structures** - Common data models used across components
- **Helper functions** - Utility functions used by multiple components

### `/tests/` - Test Suite

**Purpose**: Automated testing infrastructure

- **Unit tests** - Component-level testing
- **Integration tests** - Cross-component testing
- **Session lifecycle tests** - Full workflow testing

### `/docs/` - Documentation

**Purpose**: User guides, screenshots, and documentation assets

### `/examples/` - Example Configurations

**Purpose**: Sample configurations and usage examples

## Communication Flow

### 1. User Session Initialization

```text
Browser → NiceGUI UI → Session API → Session Manager → Allocate PHOEBE Server
```

### 2. Parameter Operations

```text
UI Widget Change → PHOEBE API Client → FastAPI → Session Manager → ZeroMQ → PHOEBE Server
```

### 3. Model Computation

```text
Compute Button → UI → PHOEBE API → Session Manager → PHOEBE Server → Model Results → UI Update
```

### 4. Data Flow for Plotting

```text
PHOEBE Server (Model Data) → Session Manager → API Layer → UI → Plotly Visualization
```

## Key Design Patterns

### 1. **Microservices Architecture**

- Each layer is independently deployable
- Clear API boundaries between components
- Horizontal scaling capability

### 2. **Session Isolation**

- Each user gets a dedicated PHOEBE server instance
- Complete parameter space isolation between users
- Independent model state management

### 3. **Asynchronous Communication**

- ZeroMQ for high-performance backend communication
- FastAPI async endpoints for web layer
- Non-blocking UI operations

### 4. **Widget-Based UI Architecture**

- Modular UI components (parameter widgets, plot panels)
- Event-driven parameter updates
- Real-time validation and feedback

### 5. **API Client Pattern**

- Clean abstraction over HTTP APIs
- Centralized error handling
- Automatic request serialization

## Deployment Architecture

### Development Mode

- Single machine deployment
- All components run as separate processes
- Local ZeroMQ communication
- In-memory session storage

### Production Mode

- Containerized deployment (Docker)
- Load balancer for web layer
- Distributed PHOEBE server pool
- Redis for session state
- Monitoring and logging integration

## Educational Features

### Parameter Exploration

- **Real-time parameter adjustment** with immediate visual feedback
- **Parameter constraints** showing valid ranges and dependencies
- **Interactive plots** responding to parameter changes

### Model Fitting Workflow

- **Parameter selection** via adjust checkboxes
- **Solver integration** for automated fitting
- **Solution adoption** to apply fitted parameters
- **Before/after comparison** in results table

### Data Integration

- **Synthetic dataset creation** for parameter exploration
- **Real observation upload** for actual data fitting
- **Model-data comparison** plots

## Technology Stack

- **Frontend**: NiceGUI (Python-based web UI framework)
- **API Layer**: FastAPI (Modern Python web framework)
- **Visualization**: Plotly (Interactive scientific plotting)
- **Communication**: ZeroMQ (High-performance messaging)
- **Scientific Computing**: PHOEBE (Stellar modeling library)
- **Session Management**: Redis (Distributed session storage)
- **Deployment**: Docker (Containerization)

## Security Considerations

- **Session isolation** prevents cross-user data access
- **Resource limits** prevent server overload
- **Input validation** at all API layers
- **Timeout management** for long-running computations

## Scalability Features

- **Horizontal server scaling** - Add more PHOEBE servers as needed
- **Load balancing** - Distribute users across available servers
- **Resource monitoring** - Track server utilization
- **Session persistence** - Survive server restarts
- **Stateless web layer** - Scale web servers independently

This architecture provides a robust, scalable platform for binary star modeling education while maintaining the full power and accuracy of the PHOEBE computational engine.