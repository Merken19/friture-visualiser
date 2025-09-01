# FFT Stream Visualizer

A real-time FFT spectrum visualizer that connects to Friture's streaming API and displays spectrum data in the same style as the original Friture spectrum analyzer.

## Features

- **Real-time spectrum display** with logarithmic frequency axis (20 Hz - 20 kHz)
- **dB magnitude scale** (-100 dB to -20 dB typical range)
- **Peak detection and display** with frequency markers
- **Dark theme** matching Friture's visual design
- **Smooth animations** and real-time updates
- **Interactive controls** (zoom, pan, save)
- **Frequency labels** showing peak frequencies
- **Exponential smoothing** matching Friture's response characteristics

## Requirements

- Python 3.7+
- matplotlib
- numpy
- websockets
- Friture running with spectrum analysis and WebSocket streaming enabled

## Installation

1. Ensure Friture is properly installed and the streaming API is working
2. Install required Python packages:
   ```bash
   pip install matplotlib numpy
   ```

## Usage

1. **Start Friture** with spectrum analysis and WebSocket streaming enabled
2. **Run the visualizer**:
   ```bash
   # Connect to default WebSocket server (localhost:8765)
   python fft_stream_visualiser.py

   # Connect to specific server
   python fft_stream_visualiser.py --host 192.168.1.100 --port 8765
   ```

3. The visualizer will connect to Friture's WebSocket server and display real-time spectrum data

## How It Works

The visualizer connects to Friture's streaming API and receives FFT spectrum data that has been processed to match the original Friture spectrum computation:

- **Data Format**: dB scale (10 * log10 of power spectrum)
- **Weighting**: A/B/C weighting applied in dB domain
- **Smoothing**: Exponential smoothing matching Friture's response time
- **Peak Detection**: Automatic peak frequency identification

## Visual Features

- **Green spectrum curve**: Main frequency response
- **Red peak markers**: Maximum magnitude points
- **White grid lines**: Logarithmic frequency divisions
- **Frequency labels**: Peak frequency display
- **Dark background**: Matches Friture's theme

## Controls

- **Mouse**: Zoom and pan
- **Right-click**: Reset view
- **Save**: Export current plot
- **Close**: Exit visualizer

## Troubleshooting

### No Data Appears
- Ensure Friture is running with a spectrum analyzer dock active
- Check that WebSocket streaming is enabled in Friture
- Verify the spectrum analyzer is processing audio (green indicators in Friture)
- Check WebSocket connection: `python fft_stream_visualiser.py --host localhost --port 8765`

### Connection Issues
- Verify Friture's WebSocket server is running on the correct host/port
- Check firewall settings if connecting to a remote machine
- Ensure websockets package is installed: `pip install websockets`

### Import Errors
- Install required packages: `pip install matplotlib numpy websockets`
- Ensure you're running from the correct directory

### Performance Issues
- Reduce the animation interval if experiencing lag
- Close other applications using audio
- Check your audio buffer settings in Friture

## WebSocket Integration

The visualizer demonstrates how to connect to Friture's WebSocket streaming API:

```python
import asyncio
import websockets
import json

async def receive_spectrum():
    uri = "ws://localhost:8765"
    async with websockets.connect(uri) as websocket:
        while True:
            message = await websocket.recv()
            data = json.loads(message)

            if data['metadata']['data_type'] == 'fft_spectrum':
                spectrum = data['data']
                # Process spectrum['magnitudes_db'], spectrum['frequencies'], etc.
                print(f"Peak: {spectrum['peak_frequency']:.1f} Hz @ {spectrum['peak_magnitude']:.1f} dB")

# Run the client
asyncio.run(receive_spectrum())
```

## Data Format

The visualizer receives data in the corrected format matching Friture's original implementation:

- `magnitudes_db`: dB values (10 * log10 of power spectrum)
- `frequencies`: Frequency bins in Hz
- `peak_frequency`: Frequency of maximum magnitude
- `peak_magnitude`: Maximum magnitude in dB
- `fft_size`: FFT size used
- `weighting`: Frequency weighting applied

## Comparison with Original Friture

This visualizer replicates the key visual elements of Friture's spectrum analyzer:

| Feature | Friture Original | This Visualizer |
|---------|------------------|-----------------|
| Frequency Scale | Logarithmic | Logarithmic |
| Magnitude Scale | dB | dB |
| Peak Display | Red markers | Red markers |
| Color Scheme | Dark theme | Dark theme |
| Smoothing | Exponential | Exponential |
| Weighting | A/B/C | A/B/C |
| Real-time | Yes | Yes |

## Extending the Visualizer

You can extend this visualizer by:

1. **Adding more data types**: Pitch tracking, levels, spectrograms
2. **Custom visualizations**: 3D plots, waterfall displays
3. **Audio features**: Spectral centroid, rolloff, flux
4. **Multiple displays**: Subplots for different analyses
5. **Recording**: Save spectrum data to files
6. **Network features**: Stream to web interfaces

## License

This visualizer is part of the Friture project and follows the same GPL-3.0 license.