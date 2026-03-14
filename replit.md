# Inventory Forecast Simulator

## Overview

This is a Streamlit-based inventory forecasting application that simulates daily inventory levels based on sales velocity, scheduled deliveries, and reorder logic. The application allows users to input weighted sales data from different time periods, apply seasonality factors, and generate forecasts with interactive visualizations.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Frontend Architecture
- **Framework**: Streamlit for web interface
- **Visualization**: Plotly for interactive charts and graphs
- **Data Display**: Pandas DataFrames for tabular data presentation
- **Layout**: Wide layout with sidebar controls and main content area

### Backend Architecture
- **Core Logic**: Python modules handling forecasting, data processing, and database operations
- **Database**: SQLAlchemy ORM with PostgreSQL backend
- **Session Management**: Streamlit session state for temporary data storage
- **File Processing**: Support for CSV and Excel file uploads

### Data Storage Solutions
- **Primary Database**: PostgreSQL with SQLAlchemy ORM
- **Table Structure**: Single `forecast_simulations` table storing forecast parameters and results
- **Data Serialization**: JSON format for complex data structures with NumPy compatibility
- **Session Storage**: Streamlit session state for temporary forecast data

## Key Components

### 1. Data Handler (`data_handler.py`)
- **Purpose**: File parsing and data extraction
- **Functions**: 
  - Parse uploaded CSV/Excel files
  - Extract sales velocity from data
  - Handle initial inventory and delivery schedules
  - Generate sample data for testing

### 2. Forecast Logic (`forecast_logic.py`)
- **Purpose**: Core forecasting algorithms with professional inventory management
- **Features**:
  - Daily inventory simulation with proper inventory position tracking
  - Inventory Position = On-Hand + On-Order (industry standard)
  - Reorder Point (ROP) = Lead Time Demand + Safety Stock
  - Order-Up-To policy for replenishment quantity determination
  - Multiple pipeline PO support for long lead times
  - Seasonality factor application
  - Realistic stockout prevention for any lead time duration

### 3. Weighted Velocity Calculator (`weighted_velocity.py`)
- **Purpose**: Calculate blended daily velocity from multiple time periods
- **Features**:
  - Support for 7-day, 30-day, 60-day, 90-day periods
  - Weighted average calculations
  - Flexible weight normalization
  - Period-specific velocity calculations

### 4. Database Handler (`db_handler.py`)
- **Purpose**: Database operations and data persistence
- **Features**:
  - SQLAlchemy ORM models
  - CRUD operations for forecast simulations
  - JSON serialization with NumPy support
  - Custom encoder for complex data types

### 5. Main Application (`app.py`)
- **Purpose**: Streamlit UI and application orchestration
- **Features**:
  - Interactive parameter controls
  - Real-time forecast visualization
  - File upload handling
  - Session state management

## Data Flow

1. **Input Phase**: User provides sales data through manual entry or file upload
2. **Processing Phase**: Weighted velocity calculation from multiple time periods
3. **Simulation Phase**: Daily inventory simulation with deliveries and reorders
4. **Analysis Phase**: Forecast analysis and visualization generation
5. **Storage Phase**: Optional saving of forecast scenarios to database
6. **Visualization Phase**: Interactive charts and data tables display

## External Dependencies

### Core Libraries
- **Streamlit**: Web application framework
- **Pandas**: Data manipulation and analysis
- **NumPy**: Numerical computations
- **Plotly**: Interactive visualization
- **SQLAlchemy**: Database ORM

### Database
- **PostgreSQL**: Primary data storage
- **Environment Variables**: `DATABASE_URL` for connection configuration

### File Processing
- **CSV/Excel Support**: Via pandas read_csv and read_excel
- **Base64 Encoding**: For file handling in Streamlit

## Deployment Strategy

### Environment Configuration
- Database URL configuration through environment variables
- Streamlit configuration for wide page layout
- SQLAlchemy engine setup with automatic table creation

### Database Management
- **Migration Support**: `db_migration.py` for schema updates
- **Reset Functionality**: `reset_database.py` for clean deployments
- **Automatic Schema Creation**: SQLAlchemy metadata handles table creation

### Key Features
- **Persistence**: Forecast scenarios saved to database
- **Seasonality Support**: Optional seasonal adjustments
- **Weighted Velocity**: Multiple time period blending
- **Interactive Visualization**: Real-time chart updates
- **File Upload**: CSV/Excel data import capability

### Technical Considerations
- Uses JSON serialization for complex forecast data storage
- Implements custom NumPy JSON encoder for database compatibility
- Handles database connection through environment variables
- Supports both manual data entry and file upload workflows