# Friture Streaming Information Visualizer

A real-time GUI application for visualizing Friture's streaming API data with beautiful visualizations and raw message display.

## Features

- **Real-time Data Visualization**: Live visualization of all Friture data types
- **Raw Message Display**: View raw JSON messages in a dedicated panel
- **Multi-protocol Support**: WebSocket connectivity to Friture's streaming API
- **Statistics Dashboard**: Real-time connection and performance statistics
- **Professional UI**: Clean, resizable interface with professional styling
- **Error Handling**: Robust connection management and error reporting

## Installation

### Requirements

```bash
pip install PyQt5 websockets numpy
```

### Dependencies

- **PyQt5**: GUI framework for the application interface
- **websockets**: WebSocket client library for data streaming
- **numpy**: Numerical operations for data processing

## Usage

### Basic Usage

```bash
# Connect to default WebSocket server (localhost:8765)
python stream_information_visualiser.py

# Connect to specific server
python stream_information_visualiser.py --host 192.168.1.100 --port 8765
```

### Command Line Options

- `--host`: WebSocket server hostname (default: localhost)
- `--port`: WebSocket server port (default: 8765)

### Example

```bash
python stream_information_visualiser.py --host localhost --port 8765
```

## Interface Overview

### Main Window Layout

The application features a split-pane interface:

#### Left Panel (70%): Data Visualizations
- **Audio Levels**: Real-time level meters with peak, RMS, and peak hold
- **Frequency Spectrum**: Live spectrum display with logarithmic frequency axis
- **Pitch Tracker**: Note display with confidence meter
- **Additional Types**: Support for spectrogram, scope, octave, and delay data

#### Right Panel (30%): Information Display
- **Raw Messages**: JSON message viewer with syntax highlighting
- **Statistics**: Connection status, message rates, and performance metrics

### Menu Options

#### File Menu
- **Connect**: Establish WebSocket connection
- **Disconnect**: Close WebSocket connection
- **Exit**: Close the application

#### View Menu
- **Clear Raw Messages**: Clear the message history

## Data Types Supported

### Audio Levels (`levels`)
- **Visualization**: Multi-channel level bars with peak/RMS indicators
- **Features**: Peak hold display, channel-specific colors
- **Data**: `peak_levels_db`, `rms_levels_db`, `peak_hold_levels_db`

### Frequency Spectrum (`fft_spectrum`)
- **Visualization**: Real-time spectrum plot with logarithmic frequency scaling
- **Features**: Peak frequency highlighting, dB magnitude display
- **Data**: `frequencies`, `magnitudes_db`, `peak_frequency`, `peak_magnitude`

### Pitch Tracker (`pitch_tracker`)
- **Visualization**: Note name display with confidence meter
- **Features**: Musical note identification, confidence visualization
- **Data**: `frequency_hz`, `note_name`, `confidence`

### Additional Types
- **Spectrogram** (`spectrogram`): Time-frequency waterfall display
- **Scope** (`scope`): Time-domain waveform visualization
- **Octave Spectrum** (`octave_spectrum`): Octave band analysis
- **Delay Estimator** (`delay_estimator`): Inter-channel delay measurement

## Connection Management

### Automatic Connection
- Application attempts to connect on startup
- Automatic reconnection on connection loss
- Visual connection status indicators

### Manual Control
- Connect/Disconnect via File menu
- Connection status in status bar
- Error messages for connection issues

## Statistics and Monitoring

### Real-time Statistics
- **Connection Status**: Connected/Disconnected/Reconnecting
- **Message Count**: Total messages received
- **Data Rate**: Messages per second
- **Active Types**: Currently streaming data types
- **Sample Count**: Total samples processed
- **Error Count**: Parsing and connection errors

### Performance Metrics
- **Uptime**: Application runtime
- **Memory Usage**: Approximate memory consumption
- **Update Rate**: GUI refresh frequency

## Troubleshooting

### Connection Issues

#### Server Not Found
```
Error: WebSocket connection failed: [Errno 61] Connection refused
```
**Solution**: Ensure Friture is running and streaming API is enabled

#### Port Already in Use
```
Error: WebSocket server error: Port 8765 is already in use
```
**Solution**: Use a different port or stop the conflicting service

#### WebSocket Library Missing
```
Error: websockets library not available
```
**Solution**: Install websockets library: `pip install websockets`

### Data Display Issues

#### No Data Appearing
- Check that Friture has active analysis widgets
- Verify the correct WebSocket port is being used
- Ensure data types are being streamed

#### Incorrect Sample Counts
- Check raw message format in the right panel
- Verify JSON structure matches expected format
- Look for parsing errors in application logs

### Performance Issues

#### High CPU Usage
- Reduce GUI update frequency if needed
- Check for excessive message rates
- Monitor system resources

#### Memory Growth
- Clear raw message history periodically
- Monitor for memory leaks in data processing
- Restart application if memory usage becomes excessive

## Development

### Architecture

The application follows a modular architecture:

```
StreamVisualizerApp
├── StreamingWebSocketClient (WebSocket connection)
├── StreamVisualizerWindow (Main GUI)
│   ├── DataVisualizationArea (Left panel)
│   │   ├── LevelsVisualization
│   │   ├── SpectrumVisualization
│   │   └── PitchVisualization
│   └── InformationPanel (Right panel)
│       ├── RawMessageDisplay
│       └── StatisticsPanel
```

### Key Components

#### StreamingWebSocketClient
- Handles WebSocket connection and reconnection
- Parses JSON messages and extracts data types
- Emits Qt signals for UI updates
- Maintains connection statistics

#### Data Visualization Widgets
- Custom PyQt5 widgets for each data type
- Real-time painting and updates
- Responsive to window resizing
- Optimized for performance

#### Raw Message Display
- Syntax-highlighted JSON viewer
- Auto-scrolling message history
- Memory-efficient message storage
- Copy-to-clipboard functionality

### Signal/Slot Communication

The application uses Qt's signal/slot mechanism for thread-safe communication:

```python
# WebSocket client signals
dataReceived(dict)           # New parsed data available
rawMessageReceived(str)      # Raw JSON message received
connectionStatusChanged(str) # Connection status update
statisticsUpdated(dict)      # Statistics update
errorOccurred(str)           # Error notification
```

### Threading Model

- **Main Thread**: Qt GUI event loop
- **WebSocket Thread**: Async WebSocket communication
- **Communication**: Signal/slot mechanism for thread safety

## Integration with Friture

### Setup Requirements

1. **Start Friture** with streaming API enabled
2. **Open Analysis Widgets**: Spectrum, Levels, Pitch Tracker, etc.
3. **Start Streaming**: Enable data streaming in Friture
4. **Launch Visualizer**: Run this application to connect

### Data Flow

```
Friture → Streaming API → WebSocket Server → Visualizer Client → GUI Display
```

### Configuration

Ensure Friture's streaming configuration matches the visualizer:

- **WebSocket Port**: 8765 (default)
- **Data Types**: Enable desired analysis types
- **Sample Rates**: Configure appropriate update frequencies

## Examples

### Basic Visualization

```bash
# Start Friture with spectrum and levels widgets
# Then run the visualizer
python stream_information_visualiser.py
```

### Remote Server

```bash
# Connect to Friture running on another machine
python stream_information_visualiser.py --host 192.168.1.100 --port 8765
```

### Development Testing

```bash
# Use with test_stream.py for development
python test_stream.py --protocol websocket &
python stream_information_visualiser.py
```

## License

This application is part of the Friture project and follows the same licensing terms.

## Contributing

Contributions are welcome! Please ensure:

- Code follows Python and Qt best practices
- New data types include appropriate visualizations
- Error handling is comprehensive
- Documentation is updated for new features

## Support

For issues and questions:

1. Check the troubleshooting section above
2. Verify Friture streaming configuration
3. Check application logs for error details
4. Ensure all dependencies are properly installed