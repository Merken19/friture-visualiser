# Friture Streaming API Test Client

This test client provides comprehensive testing and debugging capabilities for the Friture Streaming API. It properly parses all data types and provides detailed statistics.

## Features

- **Multi-protocol support**: WebSocket, TCP, UDP, and HTTP Server-Sent Events
- **Complete data type parsing**: Handles all Friture analysis data types
- **Real-time statistics**: Message counts, data rates, sample counts per data type
- **Error tracking**: Comprehensive error reporting and debugging
- **Cross-platform**: Works on Windows, Linux, and macOS

## Installation

Ensure you have the required dependencies:

```bash
pip install websockets  # For WebSocket support
```

## Usage

### Basic Usage

```bash
# Test WebSocket connection (default)
python test_stream.py

# Test specific protocol
python test_stream.py --protocol websocket --host localhost --port 8765
python test_stream.py --protocol tcp --host localhost --port 8766
python test_stream.py --protocol udp --host localhost --port 8767
python test_stream.py --protocol http_sse --host localhost --port 8768
```

### Command Line Options

- `--protocol`: Protocol to use (websocket, tcp, udp, http_sse)
- `--host`: Server hostname (default: localhost)
- `--port`: Server port (defaults based on protocol)
- `--stats-interval`: How often to print statistics (default: 5.0 seconds)

### Example Output

```
2025-08-28 16:01:40,640 INFO WebSocket connected successfully
2025-08-28 16:01:45,123 INFO Received levels message #50
2025-08-28 16:01:50,456 INFO Received fft_spectrum message #100

============================================================
STREAMING STATISTICS
============================================================
Uptime: 15.2s
Messages received: 201
Data rate: 13.2 msg/s
Total samples: 1247
Errors: 0

Data types in history:
  levels: 120 messages, 720 samples
  fft_spectrum: 45 messages, 23040 samples
  pitch_tracker: 36 messages, 36 samples
============================================================
```

## Data Types Supported

The client properly parses and counts samples for all Friture data types:

- **levels**: Audio level measurements (peak, RMS, peak hold)
- **fft_spectrum**: Frequency domain analysis with magnitude and phase
- **octave_spectrum**: Octave band analysis results
- **spectrogram**: Time-frequency waterfall data
- **scope**: Time-domain waveform data
- **pitch_tracker**: Fundamental frequency detection
- **delay_estimator**: Inter-channel delay measurements

## Troubleshooting

### Client Shows 0 Samples for All Types

This indicates the client is receiving messages but not parsing them correctly. Check:

1. **Server message format**: Ensure server sends JSON with proper structure
2. **Data type field**: Verify `metadata.data_type` field is present and correct
3. **Protocol mismatch**: Make sure client and server use the same protocol

### Connection Issues

- **WebSocket**: Install `websockets` library: `pip install websockets`
- **Port conflicts**: Check if ports are already in use
- **Firewall**: Ensure ports are open for the chosen protocol

### High Error Counts

- Check server logs for transmission errors
- Verify network connectivity
- Ensure server and client use compatible protocol versions

## Message Format

The client expects JSON messages with this structure:

```json
{
  "metadata": {
    "timestamp": 1756386100.595106,
    "stream_time": 123.456,
    "sample_rate": 44100,
    "channels": 2,
    "data_type": "levels",
    "sequence_number": 42,
    "widget_id": "levels_widget_1",
    "custom_metadata": {}
  },
  "data": {
    // Data payload varies by data_type
    "peak_levels_db": [-20.5, -18.2],
    "rms_levels_db": [-25.1, -22.8],
    "peak_hold_levels_db": [-15.2, -12.9]
  }
}
```

## Development

The client is designed to be:

- **Extensible**: Easy to add new data types or protocols
- **Robust**: Comprehensive error handling and recovery
- **Debuggable**: Detailed logging and statistics
- **Performant**: Efficient parsing and minimal resource usage

## Integration with Friture

This client works with Friture's streaming API. To enable streaming in Friture:

1. Start Friture with streaming enabled
2. Open analysis widgets (Spectrum, Levels, etc.)
3. Run this test client to verify data flow

The client will automatically detect and parse all active data streams.