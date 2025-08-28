# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Overview

**Friture** is a real-time audio analysis and visualization application built with Python, PyQt5, QML, and Cython. It provides live audio spectrum analysis, pitch tracking, level meters, and other audio visualization widgets through a modular dock-based interface.

## Development Commands

### Environment Setup

**For Linux:**
```bash
# Install system dependencies
sudo apt-get install -y git libportaudio2 python3.11-dev

# Create and activate virtual environment  
virtualenv -p /usr/bin/python3.11 buildenv
source ./buildenv/bin/activate

# Install dependencies and build extensions
pip install .[dev]
python setup.py build_ext --inplace
```

**For Windows:**
```powershell
# Create and activate virtual environment
virtualenv buildenv
.\buildenv\Scripts\activate

# Install dependencies and build extensions
pip install .[dev]
python setup.py build_ext --inplace
```

### Common Commands

**Run the application:**
```bash
python main.py
# or
python -m friture.analyzer
```

**Build Cython extensions (required after modifying .pyx files):**
```bash
python setup.py build_ext --inplace
```

**Rebuild UI files (when .ui files change):**
```bash
pyuic5 ui/friture.ui --from-imports > friture/ui_friture.py
pyuic5 ui/settings.ui --from-imports > friture/ui_settings.py
pyrcc5 resources/friture.qrc -o friture/friture_rc.py
```

**Regenerate filter parameters:**
```bash
python friture/filter_design.py  # Creates generated_filters.py
```

**Package/Distribution:**
```bash
# Create source distribution
python setup.py sdist --formats=gztar

# Test PyPI upload  
twine upload --repository-url https://test.pypi.org/legacy/ dist/*

# Production PyPI upload
twine upload dist/*
```

**Development Tools:**
```bash
# Type checking
mypy friture/

# Code style checking
pycodestyle --show-source --show-pep8 --max-line-length=170 friture

# Auto-format code  
autopep8 --max-line-length=170 -i -r friture
```

## High-Level Architecture

### Core Application Structure

**Main Application (`analyzer.py`):**
- `Friture` class is the main QMainWindow that orchestrates all components
- Integrates PyQt5 GUI with QML-based visualization widgets
- Manages the QML engine and registers custom types for seamless Python-QML integration
- Sets up timers for smooth display updates and slower text refreshes

**Audio Pipeline:**
```
AudioBackend → AudioBuffer → [Multiple Docks/Widgets] → Display
     ↓              ↓              ↓
SoundDevice → RingBuffer → Signal Processing → QML Visualization
```

### Key Components

**1. Audio System (`audiobackend.py`, `audiobuffer.py`):**
- `AudioBackend`: Singleton that manages audio input via sounddevice/rtmixer
- `AudioBuffer`: Thread-safe ring buffer that receives audio data and emits signals
- Supports device selection, channel configuration, and real-time audio streaming
- Uses `RingBuffer` for efficient circular audio data storage

**2. Dock System (`dockmanager.py`, `dock.py`):**
- `DockManager`: Manages multiple analysis widgets in a tile layout
- Each `Dock` contains one analysis widget (spectrum, levels, pitch tracker, etc.)
- Supports dynamic creation/removal, reordering, and state persistence
- Uses `TileLayout` for responsive grid arrangement

**3. QML Integration (`qml_tools.py`, `*.qml`):**
- Hybrid Python/QML architecture for performant real-time visualization
- Python handles signal processing; QML handles UI and graphics rendering
- Custom QML components for plots, scales, meters, and controls
- Seamless data binding between Python data models and QML views

**4. Signal Processing (`audioproc.py`, `filter.py`, `generated_filters.py`):**
- Real-time FFT, windowing, and frequency analysis
- Precomputed filter banks for octave analysis
- Cython extensions for performance-critical operations
- IEC standard implementations for professional audio measurements

**5. Analysis Widgets:**
- **Spectrum Analyzer** (`spectrum*.py`): FFT-based frequency analysis
- **Pitch Tracker** (`pitch_tracker*.py`): Real-time pitch detection and note identification  
- **Level Meters** (`levels*.py`): Peak and RMS level monitoring with ballistics
- **Spectrogram** (`spectrogram*.py`): Time-frequency waterfall display
- **Scope** (`scope*.py`): Time-domain waveform display
- **Octave Analysis** (`octave*.py`): 1/3, 1/1 octave band analysis
- **Delay Estimator** (`delay_estimator*.py`): Cross-correlation delay measurement

### Data Flow Architecture

**Real-time Processing Chain:**
1. **Audio Input**: `AudioBackend` captures audio from selected device
2. **Buffering**: `AudioBuffer` stores audio in circular buffer, emits new data signals
3. **Distribution**: Multiple dock widgets receive the same audio data simultaneously  
4. **Processing**: Each widget performs its own signal processing (FFT, filtering, etc.)
5. **Visualization**: Processed data updates QML-based visual components
6. **Display**: Graphics are rendered at smooth 60+ FPS via Qt's graphics system

**Widget Communication:**
- Widgets are largely independent and don't communicate directly
- `DockManager` coordinates widget lifecycle and layout
- Settings are managed per-widget with persistence via QSettings
- Streaming API enables external access to analysis results

### Streaming API Architecture

**Purpose**: Provides zero-overhead external access to real-time analysis data

**Data Flow:**
`Widget Signal` → `DataProducer` → `StreamingAPI` → `BufferManager` → `Consumers` → `Protocols`

**Components:**
- **Producers** (`api/producers.py`): Extract data from analysis widgets upon signal triggers.
- **StreamingAPI** (`api/streaming_api.py`): Central coordinator that routes produced data into the `BufferManager`.
- **BufferManager** (`api/buffer_manager.py`): Manages a deque for each data type, decoupling producers from consumers.
- **Consumers** (`api/consumers.py`): Process data pulled from the `BufferManager` (e.g., send to network).
- **Protocols** (`api/protocols.py`): Handle the network transport (WebSocket, TCP, etc.).
- **Integration** (`api/integration.py`): Automatically registers producers for active widgets.

#### Streaming API Internals (for development)

This section documents the exact data path and key extension points for debugging and extending the API.

1) Data Extraction from Widgets (Producers)
- Location: `friture/api/producers.py`
- Base class: `DataProducer` (QObject + ABC)
  - Lifecycle: `start()` connects to a widget's data update signal (e.g., `new_data_available`); `stop()` disconnects.
  - Extraction: `extract_data()` is called by a handler (`_on_new_data`) and reads the latest processed values directly from widget attributes.
  - Emission: `_emit_data()` packages the extracted data and emits `data_ready`.
- Key concrete producers and where they read from:
  - `PitchTrackerProducer`: Reads from `widget.tracker`'s latest estimates (`get_latest_estimate`, `get_latest_confidence`, etc.).
  - `FFTSpectrumProducer`: Reads from `widget.spectrum_data.magnitudes_db` and `.frequencies`.
  - `OctaveSpectrumProducer`: Reads from `widget.dispbuffers` and applies weighting from `widget.filters`.
  - `LevelsProducer`: Reads from `widget.level_view_model` and its associated `level_data` and `level_data_ballistic` objects.
  - `SpectrogramProducer`: Reads from `widget.spectrogram_data` (timestamps, frequencies, magnitudes).
  - `ScopeProducer`: Reads from `widget.scope_data` (timestamps, samples).
  - `DelayEstimatorProducer`: Connects to `widget.new_result_available` and reads properties like `delay_ms`, `correlation`, etc.

2) API Intake, Buffering, and Distribution
- Location: `friture/api/streaming_api.py`
- **Intake**: `_handle_producer_data` is connected to every producer's `data_ready` signal. It performs rate-limiting and then calls `self._buffer_manager.add_data(data_type, streaming_data)`.
- **Buffering**: The `BufferManager` stores each `StreamingData` object in a separate `deque` based on its `DataType`.
- **Distribution**: `_process_buffers` is called on a 40ms `QTimer`. It pulls data from the `BufferManager` using `get_data()` and passes it to `_distribute_to_consumers`.
- **Consumption**: `_distribute_to_consumers` iterates through registered consumers, checks `consumer.can_accept_data()`, and calls `consumer.consume_data()`.

3) Known Failure Modes and How to Debug
- **No data is being streamed**:
  - Check logs for errors in `producers.py` `extract_data` methods. An exception here will halt the pipeline for that widget.
  - Confirm the widget is active and its internal data structures (e.g., `widget.spectrogram_data`) are being populated.
  - Verify that `_process_buffers` in `streaming_api.py` is being called and that `self._buffer_manager.get_data()` is returning items.
- **Data for only some widgets is streaming**:
  - The `widgetId` in `integration.py`'s `_producer_classes` map might be incorrect for the non-streaming widget.
  - The producer's `extract_data` method for the failing widget is likely returning `None` continuously. Add logging to check the state of the widget attributes it depends on.

### Performance-Critical Extensions

**Cython Extensions** (`friture_extensions/`):**
- `exp_smoothing_conv.pyx`: Exponential smoothing convolution for ballistic meters
- `linear_interp.pyx`: Linear interpolation for efficient resampling
- `lookup_table.pyx`: Fast lookup tables for frequency-to-note conversion  
- `lfilter.pyx`: Digital filtering operations

**Build Process:**
- Extensions are compiled during installation via `setup.py`
- `.pyx` files are converted to C and compiled to `.pyd` (Windows) or `.so` (Linux)
- NumPy integration for efficient array operations

### UI/UX Architecture

**Hybrid Approach:**
- Main application window and dialogs use PyQt5 widgets
- Analysis visualizations use QML for smooth graphics and animations
- Settings dialogs integrate Qt widgets with custom controls
- Responsive layout adapts to different screen sizes

**QML Components** (`.qml` files):
- Modular, reusable components for plots, scales, and controls
- Hardware-accelerated rendering via Qt Quick
- Declarative data binding and property animations
- Custom painting for specialized audio visualizations

### Configuration and Settings

**Settings Management:**
- Qt's QSettings for persistent configuration storage
- Per-widget settings with automatic save/restore  
- Device selection, analysis parameters, and UI preferences
- Export/import functionality for configuration backup

**Default Configuration** (`defaults.py`):
- Defines initial dock layout and widget types
- Fallback values for all configurable parameters
- Professional audio defaults (48 kHz, appropriate window sizes)

## Development Workflow

### Adding New Analysis Widgets

1. Create widget class inheriting from appropriate base
2. Implement signal processing in Python with optional Cython extensions
3. Create corresponding QML component for visualization
4. Register QML types in `analyzer.py`
5. Add to dock system via `DockManager`
6. Optionally add Streaming API producer for external access

### Modifying Signal Processing

1. Edit Python processing code or create/modify `.pyx` files
2. Rebuild Cython extensions with `python setup.py build_ext --inplace`
3. Test changes with live audio input
4. Update corresponding QML visualization if needed

### UI Changes

1. Modify `.ui` files with Qt Designer or edit directly
2. Regenerate Python UI files with `pyuic5`
3. For QML changes, edit `.qml` files directly
4. Test responsive behavior across different window sizes

### Performance Optimization

- Profile with Python's `cProfile` or Qt's built-in profilers
- Move critical loops to Cython extensions
- Optimize QML rendering by minimizing property bindings
- Use appropriate buffer sizes and processing block sizes
- Monitor real-time performance via built-in statistics

This architecture enables Friture to provide professional-grade audio analysis with excellent real-time performance while maintaining extensibility and a responsive user interface.
