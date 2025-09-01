# Friture Streaming API Documentation

## Overview

The Friture Streaming API provides real-time access to audio analysis data from any Friture dock with zero performance overhead to the main application. This API enables external applications to consume live audio analysis results for custom processing, visualization, monitoring, and integration with other systems.

## Key Features

- **Zero-Overhead Design**: No performance impact when no consumers are active
- **Multiple Data Types**: Support for pitch tracking, FFT spectrum, octave analysis, levels, spectrogram, and more
- **Flexible Protocols**: WebSocket, TCP, UDP, and HTTP Server-Sent Events
- **Rate Limiting**: Configurable rate limiting to prevent overwhelming consumers
- **Backpressure Handling**: Intelligent buffering and overflow management
- **Thread-Safe**: Safe for use in multi-threaded environments
- **Comprehensive Monitoring**: Built-in performance statistics and logging

## Architecture

The streaming API follows a producer-consumer architecture:

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐    ┌──────────────┐
│   Friture   │    │   Producer   │    │   Buffer    │    │   Consumer   │
│   Widgets   │───▶│              │───▶│   Manager   │───▶│              │
│             │    │              │    │             │    │              │
└─────────────┘    └──────────────┘    └─────────────┘    └──────────────┘
                                                                    │
                                                                    ▼
                                                           ┌──────────────┐
                                                           │   Protocol   │
                                                           │   (Network)  │
                                                           └──────────────┘
```

### Components

1. **Producers**: Extract data from Friture widgets
2. **Buffer Manager**: Handles temporary storage and backpressure
3. **Rate Limiter**: Controls data flow rates
4. **Consumers**: Process and forward data
5. **Protocols**: Handle network communication

## Quick Start

### Basic Setup

```python
from friture.api import StreamingAPI, DataType, CallbackConsumer

# Get the streaming API instance
api = StreamingAPI()

# Define a callback function
def pitch_callback(data):
    if data.data.frequency_hz:
        print(f"Pitch: {data.data.frequency_hz:.1f} Hz ({data.data.note_name})")

# Register a consumer
consumer = CallbackConsumer(pitch_callback)
api.register_consumer(DataType.PITCH_TRACKER, consumer)

# Start streaming
api.start_streaming()
```

### WebSocket Integration

```python
from friture.api import WebSocketProtocol, NetworkConsumer

# Setup WebSocket protocol
websocket = WebSocketProtocol(host='localhost', port=8765)
api.add_protocol(websocket)

# Create network consumer
network_consumer = NetworkConsumer(websocket, serialization_format='json')
api.register_consumer(DataType.FFT_SPECTRUM, network_consumer)

# Start streaming
api.start_streaming()
```

## Data Types

### Pitch Tracker Data

```python
@dataclass
class PitchData:
    frequency_hz: Optional[float]      # Detected frequency in Hz
    confidence: float                  # Confidence [0.0, 1.0]
    note_name: Optional[str]          # Musical note (e.g., "A4")
    amplitude_db: float               # Signal amplitude in dB
    harmonic_clarity: float           # Harmonic structure clarity [0.0, 1.0]
```

**Example Usage:**
```python
def pitch_handler(data):
    pitch = data.data
    if pitch.frequency_hz and pitch.confidence > 0.8:
        print(f"Strong pitch: {pitch.note_name} ({pitch.frequency_hz:.1f} Hz)")
```

### FFT Spectrum Data

```python
@dataclass
class FFTSpectrumData:
    frequencies: np.ndarray           # Frequency bins in Hz
    magnitudes_linear: np.ndarray    # Magnitude spectrum in linear scale
    phases: Optional[np.ndarray]     # Phase spectrum in radians
    fft_size: int                    # FFT size used
    window_type: str                 # Window function ("hann", etc.)
    overlap_factor: float            # Overlap factor [0.0, 1.0)
    weighting: str                   # Frequency weighting ("A", "B", "C", "none")
    peak_frequency: float            # Frequency of peak magnitude
    peak_magnitude: float            # Peak magnitude in dB
```

**Example Usage:**
```python
def spectrum_handler(data):
    spectrum = data.data
    
    # Find frequencies above threshold
    threshold_db = -40
    loud_bins = spectrum.magnitudes_linear > threshold_db
    loud_frequencies = spectrum.frequencies[loud_bins]
    
    if len(loud_frequencies) > 0:
        print(f"Active frequencies: {loud_frequencies}")
```

### Octave Spectrum Data

```python
@dataclass
class OctaveSpectrumData:
    center_frequencies: np.ndarray   # Center frequencies in Hz
    band_energies_db: np.ndarray    # Energy per band in dB
    band_labels: List[str]          # Human-readable band labels
    bands_per_octave: int           # Bands per octave (1, 3, 6, 12, 24)
    weighting: str                  # Frequency weighting
    response_time: float            # Integration time in seconds
    overall_level: float            # Overall level in dB
```

### Levels Data

```python
@dataclass
class LevelsData:
    peak_levels_db: np.ndarray      # Peak levels per channel in dB FS
    rms_levels_db: np.ndarray       # RMS levels per channel in dB FS
    peak_hold_levels_db: np.ndarray # Peak hold levels in dB FS
    channel_labels: List[str]       # Channel labels
    integration_time: float         # RMS integration time
    peak_hold_time: float          # Peak hold time
```

## Protocols

### WebSocket Protocol

Best for web applications and real-time dashboards.

```python
from friture.api import WebSocketProtocol

# Create WebSocket server
websocket = WebSocketProtocol(host='localhost', port=8765)
api.add_protocol(websocket)

# Client connection (JavaScript example)
const ws = new WebSocket('ws://localhost:8765');
ws.onmessage = function(event) {
    const data = JSON.parse(event.data);
    console.log('Received:', data);
};
```

### TCP Protocol

Best for reliable delivery and custom applications.

```python
from friture.api import TCPProtocol

# Create TCP server
tcp = TCPProtocol(host='localhost', port=8766)
api.add_protocol(tcp)

# Client connection (Python example)
import socket
import json

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(('localhost', 8766))

while True:
    # Read length prefix
    length_line = sock.recv(1024).decode().split('\n')[0]
    length = int(length_line)
    
    # Read data
    data = sock.recv(length).decode()
    parsed_data = json.loads(data)
    print('Received:', parsed_data)
```

### UDP Protocol

Best for low-latency applications where occasional data loss is acceptable.

```python
from friture.api import UDPProtocol

# Create UDP server
udp = UDPProtocol(host='localhost', port=8767)
udp.add_client('localhost', 9000)  # Add client address
api.add_protocol(udp)

# Client connection (Python example)
import socket
import json

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('localhost', 9000))

while True:
    data, addr = sock.recvfrom(65536)
    parsed_data = json.loads(data.decode())
    print('Received:', parsed_data)
```

### HTTP Server-Sent Events

Best for web dashboards and monitoring applications.

```python
from friture.api import HTTPSSEProtocol

# Create SSE server
sse = HTTPSSEProtocol(host='localhost', port=8768)
api.add_protocol(sse)

# Client connection (JavaScript example)
const eventSource = new EventSource('http://localhost:8768');
eventSource.onmessage = function(event) {
    const data = JSON.parse(event.data);
    console.log('Received:', data);
};
```

## Consumer Types

### Callback Consumer

Invokes a function for each data point:

```python
from friture.api import CallbackConsumer

def my_callback(data):
    print(f"Received {data.metadata.data_type}: {data.data}")

consumer = CallbackConsumer(my_callback, max_callback_time_ms=10.0)
api.register_consumer(DataType.PITCH_TRACKER, consumer)
```

### Queue Consumer

Stores data in a thread-safe queue:

```python
from friture.api import QueueConsumer
import threading

# Create queue consumer
queue_consumer = QueueConsumer(max_queue_size=1000, overflow_strategy='drop_oldest')
api.register_consumer(DataType.FFT_SPECTRUM, queue_consumer)

# Process in separate thread
def process_queue():
    while True:
        data = queue_consumer.get_data(timeout=1.0)
        if data:
            print(f"Processing: {data.metadata.data_type}")

thread = threading.Thread(target=process_queue, daemon=True)
thread.start()
```

### File Consumer

Writes data to files for logging:

```python
from friture.api import FileConsumer

# Create file consumer
file_consumer = FileConsumer(
    file_path='friture_data.jsonl',
    file_format='jsonl',
    max_file_size_mb=100
)
api.register_consumer(DataType.OCTAVE_SPECTRUM, file_consumer)
```

## Rate Limiting

Configure rate limits to control data flow:

```python
# Set rate limits (Hz)
api.set_rate_limit(DataType.PITCH_TRACKER, 20.0)    # 20 Hz
api.set_rate_limit(DataType.FFT_SPECTRUM, 15.0)     # 15 Hz
api.set_rate_limit(DataType.LEVELS, 50.0)           # 50 Hz

# Disable rate limiting
api.set_rate_limit(DataType.SCOPE, 0)  # No limit
```

## Performance Monitoring

Monitor API performance and system impact:

```python
# Get comprehensive statistics
stats = api.get_statistics()
print(f"Data rate: {stats.get('data_rate_hz', 0):.1f} Hz")
print(f"Active consumers: {stats.get('active_consumers', {})}")

# Get rate limiter statistics
rate_stats = api._rate_limiter.get_statistics()
print(f"Rate limiting stats: {rate_stats}")

# Get buffer statistics
buffer_stats = api._buffer_manager.get_statistics()
print(f"Buffer usage: {buffer_stats}")
```

## Integration with Friture

### Automatic Integration

The API integrates automatically with Friture's dock system:

```python
# In analyzer.py, add this to the Friture class __init__ method:
from friture.api.integration import setup_streaming_integration, create_default_streaming_setup

# Setup streaming integration
self.streaming_integration = setup_streaming_integration(
    self.dockmanager, 
    self.level_widget
)

# Create default streaming setup (optional)
create_default_streaming_setup(
    self.streaming_integration,
    enable_websocket=True,
    enable_tcp=False,
    enable_udp=False,
    enable_http_sse=True
)
```

### Manual Integration

For custom setups, manually register producers:

```python
from friture.api import get_streaming_api, PitchTrackerProducer

api = get_streaming_api()

# Register producer for a specific widget
if hasattr(dock.audiowidget, 'tracker'):  # Pitch tracker widget
    producer = PitchTrackerProducer(dock.audiowidget, dock.objectName())
    api.register_producer(DataType.PITCH_TRACKER, producer)
```

## Advanced Usage

### Custom Data Processing Pipeline

```python
class CustomProcessor:
    def __init__(self):
        self.api = get_streaming_api()
        self.pitch_history = []
        
    def setup(self):
        # Multi-type consumer
        consumer = CallbackConsumer(self.process_data)
        self.api.register_consumer(DataType.PITCH_TRACKER, consumer)
        self.api.register_consumer(DataType.FFT_SPECTRUM, consumer)
        
    def process_data(self, data):
        if data.metadata.data_type == DataType.PITCH_TRACKER:
            self.process_pitch(data.data)
        elif data.metadata.data_type == DataType.FFT_SPECTRUM:
            self.process_spectrum(data.data)
    
    def process_pitch(self, pitch_data):
        # Custom pitch analysis
        self.pitch_history.append(pitch_data.frequency_hz)
        if len(self.pitch_history) > 100:
            self.pitch_history.pop(0)
        
        # Detect pitch trends
        if len(self.pitch_history) >= 10:
            recent_pitches = self.pitch_history[-10:]
            trend = np.polyfit(range(10), recent_pitches, 1)[0]
            if abs(trend) > 5:  # Hz per sample
                print(f"Pitch trend detected: {trend:.2f} Hz/sample")
```

### Real-time Audio Analysis Dashboard

```python
class AudioDashboard:
    def __init__(self):
        self.api = get_streaming_api()
        self.websocket = WebSocketProtocol(port=8765)
        self.api.add_protocol(self.websocket)
        
        # Setup consumers for dashboard data
        self.setup_dashboard_consumers()
        
    def setup_dashboard_consumers(self):
        # Pitch tracking for tuner display
        pitch_consumer = CallbackConsumer(self.send_pitch_update)
        self.api.register_consumer(DataType.PITCH_TRACKER, pitch_consumer)
        
        # Spectrum for frequency analysis
        spectrum_consumer = CallbackConsumer(self.send_spectrum_update)
        self.api.register_consumer(DataType.FFT_SPECTRUM, spectrum_consumer)
        
        # Levels for VU meters
        levels_consumer = CallbackConsumer(self.send_levels_update)
        self.api.register_consumer(DataType.LEVELS, levels_consumer)
    
    def send_pitch_update(self, data):
        message = {
            'type': 'pitch_update',
            'frequency': data.data.frequency_hz,
            'note': data.data.note_name,
            'confidence': data.data.confidence
        }
        self.websocket.send_data(json.dumps(message))
    
    def send_spectrum_update(self, data):
        # Downsample for web transmission
        spectrum = data.data
        step = max(1, len(spectrum.frequencies) // 200)  # Max 200 points
        
        message = {
            'type': 'spectrum_update',
            'frequencies': spectrum.frequencies[::step].tolist(),
            'magnitudes': spectrum.magnitudes_linear[::step].tolist(),
            'peak_freq': spectrum.peak_frequency
        }
        self.websocket.send_data(json.dumps(message))
    
    def send_levels_update(self, data):
        message = {
            'type': 'levels_update',
            'peak_levels': data.data.peak_levels_db.tolist(),
            'rms_levels': data.data.rms_levels_db.tolist()
        }
        self.websocket.send_data(json.dumps(message))
```

## Performance Considerations

### Memory Usage

The API is designed to minimize memory usage:

- **Zero-copy**: Data is referenced, not copied, where possible
- **Configurable buffers**: Buffer sizes can be tuned per data type
- **Automatic cleanup**: Expired data is automatically removed
- **Memory monitoring**: Built-in memory usage tracking

### CPU Impact

Performance impact is minimized through:

- **Lazy evaluation**: Producers only activate when consumers are present
- **Rate limiting**: Prevents overwhelming the system with high-frequency updates
- **Efficient serialization**: Optimized JSON serialization for network protocols
- **Thread separation**: Network I/O happens in separate threads

### Network Optimization

For network protocols:

- **Compression**: Optional compression for large data sets
- **Batching**: Multiple data points can be batched for efficiency
- **Adaptive rates**: Rate limiting adapts to network conditions
- **Connection pooling**: Efficient connection management

## Configuration

### Settings Integration

The API integrates with Friture's settings system:

```python
# Save settings
from friture.api.integration import save_streaming_settings
save_streaming_settings(settings, streaming_integration)

# Load settings
from friture.api.integration import load_streaming_settings
load_streaming_settings(settings, streaming_integration)
```

### Runtime Configuration

```python
# Configure rate limits
api.set_rate_limit(DataType.PITCH_TRACKER, 30.0)  # 30 Hz

# Configure buffer sizes
api._buffer_manager.configure_buffer(
    DataType.FFT_SPECTRUM,
    max_size=500,
    strategy='lifo',
    ttl_seconds=30.0
)

# Configure protocol parameters
websocket.host = '0.0.0.0'  # Listen on all interfaces
websocket.port = 8765
```

## Error Handling

The API provides comprehensive error handling:

```python
# Connect to error signals
api.error_occurred.connect(lambda error_type, message: 
    print(f"API Error ({error_type}): {message}"))

# Consumer error handling
consumer.error_occurred.connect(lambda consumer_id, error:
    print(f"Consumer {consumer_id} error: {error}"))

# Protocol error handling
protocol.error_occurred.connect(lambda error:
    print(f"Protocol error: {error}"))
```

## Security Considerations

### Network Security

- **Bind to localhost**: Default configuration only accepts local connections
- **Authentication**: Can be added at the protocol level
- **Rate limiting**: Prevents DoS attacks
- **Input validation**: All incoming data is validated

### Data Privacy

- **No persistent storage**: Data is not stored unless explicitly configured
- **Configurable retention**: TTL settings control data lifetime
- **Access control**: Consumer registration can be restricted

## Troubleshooting

### Common Issues

1. **No data received**:
   - Check if streaming is started: `api.start_streaming()`
   - Verify producer is registered for the data type
   - Check rate limiting settings

2. **Spectrogram data not streaming**:
   - **Issue**: SpectrogramProducer fails to start due to missing `_on_new_audio_data` method
   - **Symptoms**: Server logs show `AttributeError: 'SpectrogramProducer' object has no attribute '_on_new_audio_data'`
   - **Status**: Known issue, producer creation succeeds but fails at runtime
   - **Workaround**: None currently available, requires code fix in `friture/api/producers.py`

3. **High CPU usage**:
   - Reduce rate limits: `api.set_rate_limit(data_type, lower_rate)`
   - Check consumer callback performance
   - Monitor buffer sizes

4. **Memory leaks**:
   - Check buffer TTL settings
   - Monitor consumer queue sizes
   - Verify proper cleanup in custom consumers

5. **Network connection issues**:
   - Check firewall settings
   - Verify port availability
   - Monitor protocol error signals

### Debugging

Enable debug logging:

```python
import logging
logging.getLogger('friture.api').setLevel(logging.DEBUG)
```

Monitor performance:

```python
# Print statistics every 10 seconds
import threading
import time

def stats_monitor():
    while True:
        time.sleep(10.0)
        stats = api.get_statistics()
        print(f"API Stats: {stats}")

threading.Thread(target=stats_monitor, daemon=True).start()
```

## Examples

See `friture/api/examples.py` for comprehensive examples including:

- Basic pitch tracking consumer
- Real-time spectrum analysis dashboard
- Multi-protocol data logging
- Custom analysis pipelines
- External system integration
- Performance monitoring

## API Reference

### StreamingAPI Class

#### Methods

- `register_producer(data_type, producer)`: Register a data producer
- `register_consumer(data_type, consumer)`: Register a data consumer
- `unregister_consumer(data_type, consumer_id)`: Remove a consumer
- `add_protocol(protocol)`: Add a network protocol
- `start_streaming()`: Start the streaming API
- `stop_streaming()`: Stop the streaming API
- `set_rate_limit(data_type, max_rate_hz)`: Configure rate limiting
- `get_statistics()`: Get performance statistics

#### Signals

- `data_available(DataType, StreamingData)`: New data available
- `consumer_registered(DataType, str)`: Consumer registered
- `consumer_unregistered(DataType, str)`: Consumer unregistered
- `error_occurred(str, str)`: Error occurred

### Data Types

- `DataType.PITCH_TRACKER`: Pitch tracking data
- `DataType.FFT_SPECTRUM`: FFT spectrum data
- `DataType.OCTAVE_SPECTRUM`: Octave band spectrum data
- `DataType.LEVELS`: Audio level measurements
- `DataType.DELAY_ESTIMATOR`: Delay estimation data
- `DataType.SPECTROGRAM`: Time-frequency analysis data
- `DataType.SCOPE`: Time-domain waveform data

## Future Extensions

The API is designed to be extensible for future enhancements:

### Additional Data Types

- **Harmonic analysis**: Harmonic content analysis
- **Psychoacoustic metrics**: Loudness, sharpness, roughness
- **Audio features**: MFCCs, spectral features, onset detection
- **Custom analysis**: User-defined analysis modules

### Protocol Extensions

- **MQTT**: For IoT integration
- **gRPC**: For high-performance RPC
- **REST API**: For HTTP-based access
- **Message queues**: RabbitMQ, Apache Kafka integration

### Advanced Features

- **Data compression**: Adaptive compression based on network conditions
- **Encryption**: TLS/SSL support for secure transmission
- **Authentication**: Token-based authentication system
- **Load balancing**: Multiple consumer support with load distribution
- **Caching**: Intelligent caching for frequently requested data

## Contributing

To add new data types or protocols:

1. **Data Types**: Add to `DataType` enum and create corresponding dataclass
2. **Producers**: Inherit from `DataProducer` and implement required methods
3. **Consumers**: Inherit from `DataConsumer` for custom processing
4. **Protocols**: Inherit from `StreamingProtocol` for new network protocols

Example new data type:

```python
# In data_types.py
class DataType(Enum):
    # ... existing types ...
    CUSTOM_ANALYSIS = "custom_analysis"

@dataclass(frozen=True)
class CustomAnalysisData:
    result: float
    confidence: float
    metadata: Dict[str, Any]

# In producers.py
class CustomAnalysisProducer(DataProducer):
    def get_data_type(self) -> DataType:
        return DataType.CUSTOM_ANALYSIS
    
    def extract_data(self) -> Optional[CustomAnalysisData]:
        # Extract custom data from widget
        return CustomAnalysisData(...)
```

This extensible design ensures the API can grow with Friture's capabilities while maintaining backward compatibility and performance.