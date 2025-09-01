#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
FFT Stream Visualizer

A real-time FFT spectrum visualizer that connects to Friture's WebSocket streaming API
and displays the spectrum data in a style similar to the original Friture spectrum plot.

This visualizer replicates the key visual elements of Friture's spectrum analyzer:
- Logarithmic frequency axis (20 Hz to 20 kHz)
- dB magnitude scale (-100 dB to -20 dB typical range)
- Green spectrum curve with peak markers
- Dark theme with white grid lines
- Real-time peak frequency display
- Smooth exponential smoothing matching Friture's response time

Requirements:
- Friture running with spectrum analysis enabled and WebSocket streaming
- matplotlib
- numpy
- websockets

Usage:
    python fft_stream_visualiser.py --host localhost --port 8765

Make sure Friture is running with a spectrum analyzer dock active and WebSocket streaming enabled.
The visualizer will connect to the WebSocket server and display real-time spectrum data.

Features:
- Real-time spectrum display with logarithmic frequency axis
- dB magnitude scale
- Peak detection and display
- Frequency labels
- Smooth updates and animations
- Color scheme matching Friture's design
- Interactive controls (zoom, pan)
- WebSocket connectivity for remote operation
"""

import sys
import time
import json
import logging
import argparse
import asyncio
import threading
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.patches import Rectangle
from matplotlib.collections import LineCollection
import matplotlib.ticker as ticker

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class WebSocketSpectrumClient:
    """WebSocket client for receiving FFT spectrum data."""

    def __init__(self, host: str = 'localhost', port: int = 8765):
        self.host = host
        self.port = port
        self.websocket = None
        self.running = False
        self.connected = False
        self._client_thread = None

        # Data storage
        self.current_spectrum = None
        self.current_frequencies = None
        self.current_peak_freq = None
        self.current_peak_mag = None

    def start(self):
        """Start the WebSocket client in a separate thread."""
        if self.running:
            return

        self.running = True
        logger.info(f"Connecting to WebSocket: ws://{self.host}:{self.port}")

        # Start WebSocket thread
        self._client_thread = threading.Thread(target=self._run_client, daemon=True)
        self._client_thread.start()

    def stop(self):
        """Stop the WebSocket client."""
        if not self.running:
            return

        self.running = False
        if self.websocket:
            asyncio.run(self.websocket.close())

    def _run_client(self):
        """Run the WebSocket client (in separate thread)."""
        try:
            asyncio.run(self._connect_and_listen())
        except Exception as e:
            logger.error(f"WebSocket client error: {e}")

    async def _connect_and_listen(self):
        """Connect to WebSocket and listen for messages."""
        try:
            import websockets

            uri = f"ws://{self.host}:{self.port}"
            self.websocket = await websockets.connect(uri)
            self.connected = True
            logger.info("WebSocket connected successfully")

            while self.running:
                try:
                    message = await self.websocket.recv()
                    message_str = message.decode('utf-8') if isinstance(message, bytes) else str(message)
                    self._process_message(message_str)
                except websockets.exceptions.ConnectionClosed:
                    logger.warning("WebSocket connection closed")
                    break
                except Exception as e:
                    logger.error(f"Message processing error: {e}")
                    continue

        except Exception as e:
            logger.error(f"WebSocket connection error: {e}")
        finally:
            self.connected = False
            if self.websocket:
                await self.websocket.close()

    def _process_message(self, message: str):
        """Process a received message."""
        try:
            # Parse JSON
            data = json.loads(message)
            parsed_data = self._parse_streaming_data(data)

            # Update spectrum data if it's FFT spectrum data
            if parsed_data.get('data_type') == 'fft_spectrum':
                self._update_spectrum_data(parsed_data)

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
        except Exception as e:
            logger.error(f"Message processing error: {e}")

    def _parse_streaming_data(self, data: dict) -> dict:
        """Parse streaming data."""
        try:
            metadata = data.get('metadata', {})
            data_type = metadata.get('data_type', 'unknown')
            data_payload = data.get('data', {})

            return {
                'metadata': metadata,
                'data': data_payload,
                'data_type': data_type
            }

        except Exception as e:
            logger.warning(f"Data parsing error: {e}")
            return {
                'metadata': data.get('metadata', {}),
                'data': data.get('data', {}),
                'data_type': 'unknown'
            }

    def _update_spectrum_data(self, parsed_data: dict):
        """Update spectrum data from parsed message."""
        try:
            data = parsed_data['data']

            # Extract spectrum data
            frequencies = data.get('frequencies', [])
            magnitudes_db = data.get('magnitudes_db', [])
            peak_freq = data.get('peak_frequency')
            peak_mag = data.get('peak_magnitude')

            # Validate data
            if not frequencies or not magnitudes_db:
                logger.warning("Received empty frequency or magnitude data")
                return

            if len(frequencies) != len(magnitudes_db):
                logger.warning(f"Data length mismatch: frequencies={len(frequencies)}, magnitudes={len(magnitudes_db)}")
                return

            # Convert to numpy arrays
            freq_array = np.array(frequencies, dtype=np.float64)
            mag_array = np.array(magnitudes_db, dtype=np.float64)

            # Check if arrays are reversed (common issue in FFT processing)
            # If low frequencies are at the end and high frequencies at the beginning,
            # reverse both arrays to match the expected order (low to high frequency)
            if len(freq_array) > 1 and freq_array[0] > freq_array[-1]:
                logger.info("Detected reversed frequency array, correcting order")
                freq_array = freq_array[::-1]
                mag_array = mag_array[::-1]

            self.current_frequencies = freq_array
            self.current_spectrum = mag_array

            # Validate peak data
            if peak_freq is not None and peak_mag is not None:
                if np.isfinite(peak_freq) and np.isfinite(peak_mag):
                    self.current_peak_freq = float(peak_freq)
                    self.current_peak_mag = float(peak_mag)
                else:
                    logger.warning(f"Invalid peak data: freq={peak_freq}, mag={peak_mag}")
                    self.current_peak_freq = None
                    self.current_peak_mag = None
            else:
                self.current_peak_freq = None
                self.current_peak_mag = None

            # Log successful data update
            # logger.info(f"Updated spectrum data: {len(self.current_frequencies)} points, "
            #             f"freq range: {self.current_frequencies[0]:.1f}-{self.current_frequencies[-1]:.1f} Hz, "
            #             f"mag range: {np.min(self.current_spectrum):.1f}-{np.max(self.current_spectrum):.1f} dB"
            #             f"{' (corrected order)' if freq_array[0] > freq_array[-1] else ''}")

        except Exception as e:
            logger.error(f"Error updating spectrum data: {e}")
            # Reset data on error
            self.current_frequencies = None
            self.current_spectrum = None
            self.current_peak_freq = None
            self.current_peak_mag = None


class FFTStreamVisualizer:
    """Real-time FFT spectrum visualizer using WebSocket connection to Friture."""

    def __init__(self, host: str = 'localhost', port: int = 8765, figsize=(12, 8)):
        """Initialize the visualizer."""
        self.host = host
        self.port = port

        # Setup WebSocket client
        self.ws_client = WebSocketSpectrumClient(host, port)

        # Setup matplotlib figure
        plt.style.use('dark_background')
        self.fig, self.ax = plt.subplots(figsize=figsize, facecolor='#1a1a1a')
        self.fig.patch.set_facecolor('#1a1a1a')

        # Configure the plot to match Friture's appearance
        self.setup_plot()

        # Data storage (will be updated by WebSocket client)
        self.current_spectrum = None
        self.current_frequencies = None
        self.current_peak_freq = None
        self.current_peak_mag = None

        # Animation
        self.ani = None

    def setup_plot(self):
        """Setup the matplotlib plot to match Friture's spectrum appearance."""
        # Clear the axes
        self.ax.clear()

        # Set background colors
        self.ax.set_facecolor('#1a1a1a')
        self.ax.grid(True, alpha=0.3, color='#404040', linestyle='--')

        # Configure axes
        self.ax.set_xlabel('Frequency (Hz)', color='white', fontsize=12, fontweight='bold')
        self.ax.set_ylabel('PSD (dB)', color='white', fontsize=12, fontweight='bold')

        # Set axis colors
        self.ax.tick_params(colors='white', labelsize=10)
        self.ax.spines['bottom'].set_color('white')
        self.ax.spines['top'].set_color('white')
        self.ax.spines['left'].set_color('white')
        self.ax.spines['right'].set_color('white')

        # Set logarithmic x-axis
        self.ax.set_xscale('log')

        # Set initial axis ranges (will be updated with real data)
        self.ax.set_xlim(20, 20000)
        self.ax.set_ylim(-100, 0)  # Allow positive dB values for peaks

        # Configure tick formatters
        self.ax.xaxis.set_major_formatter(ticker.FuncFormatter(self.freq_formatter))
        self.ax.yaxis.set_major_formatter(ticker.FuncFormatter(self.db_formatter))

        # Title
        self.ax.set_title('Friture FFT Spectrum - Real-time', color='white',
                         fontsize=14, fontweight='bold', pad=20)

        # Initialize plot elements
        self.spectrum_line, = self.ax.plot([], [], color='#00ff88', linewidth=2, alpha=0.8)
        self.peak_line, = self.ax.plot([], [], color='#ff4444', linewidth=1, alpha=0.9)

        # Peak marker
        self.peak_marker = self.ax.scatter([], [], c='#ff4444', s=50, marker='o',
                                          edgecolors='white', linewidth=1, zorder=10)

        # Frequency label
        self.freq_label = self.ax.text(0.02, 0.98, '', transform=self.ax.transAxes,
                                      color='#00ff88', fontsize=10, fontweight='bold',
                                      verticalalignment='top', bbox=dict(boxstyle='round,pad=0.3',
                                      facecolor='#1a1a1a', edgecolor='#00ff88', alpha=0.8))

        # Pitch label
        self.pitch_label = self.ax.text(0.02, 0.90, '', transform=self.ax.transAxes,
                                       color='#ffaa00', fontsize=10, fontweight='bold',
                                       verticalalignment='top', bbox=dict(boxstyle='round,pad=0.3',
                                       facecolor='#1a1a1a', edgecolor='#ffaa00', alpha=0.8))

    def freq_formatter(self, x, pos):
        """Format frequency values for display."""
        if x >= 1000:
            return f'{x/1000:.0f}k'
        elif x >= 100:
            return f'{x:.0f}'
        elif x >= 10:
            return f'{x:.1f}'
        else:
            return f'{x:.2f}'

    def db_formatter(self, x, pos):
        """Format dB values for display."""
        return f'{x:.0f}'

    def setup_websocket_client(self):
        """Setup the WebSocket client."""
        # The WebSocket client is already initialized in __init__
        # Data will be updated automatically when messages are received
        pass

    def update_plot(self, frame):
        """Update the plot with new data from WebSocket client."""
        # Get latest data from WebSocket client
        self.current_spectrum = self.ws_client.current_spectrum
        self.current_frequencies = self.ws_client.current_frequencies
        self.current_peak_freq = self.ws_client.current_peak_freq
        self.current_peak_mag = self.ws_client.current_peak_mag

        if self.current_spectrum is not None and self.current_frequencies is not None:
            # Validate data lengths match
            if len(self.current_spectrum) == len(self.current_frequencies) and len(self.current_spectrum) > 0:
                # Filter out invalid values (NaN, inf)
                valid_indices = np.isfinite(self.current_spectrum) & np.isfinite(self.current_frequencies)
                if np.any(valid_indices):
                    valid_freqs = self.current_frequencies[valid_indices]
                    valid_mags = self.current_spectrum[valid_indices]

                    # Update spectrum line
                    self.spectrum_line.set_data(valid_freqs, valid_mags)

                    # Update peak display
                    if self.current_peak_freq is not None and self.current_peak_mag is not None:
                        # Ensure peak values are within valid range
                        if (self.current_peak_freq >= valid_freqs[0] and
                            self.current_peak_freq <= valid_freqs[-1] and
                            np.isfinite(self.current_peak_mag)):
                            peak_freqs = [self.current_peak_freq]
                            peak_mags = [self.current_peak_mag]
                            self.peak_line.set_data(peak_freqs, peak_mags)
                            self.peak_marker.set_offsets(np.column_stack([peak_freqs, peak_mags]))

                            # Update frequency label
                            if self.current_peak_freq < 1000:
                                freq_text = f'{self.current_peak_freq:.1f} Hz'
                            else:
                                freq_text = f'{self.current_peak_freq/1000:.1f} kHz'
                            self.freq_label.set_text(freq_text)
                        else:
                            # Hide peak markers if invalid
                            self.peak_line.set_data([], [])
                            self.peak_marker.set_offsets(np.empty((0, 2)))
                            self.freq_label.set_text('')

                    # Update axis ranges
                    freq_min = max(20, valid_freqs[0])
                    freq_max = min(20000, valid_freqs[-1])
                    self.ax.set_xlim(freq_min, freq_max)

                    # Calculate magnitude range with proper bounds
                    mag_min = float(np.min(valid_mags))
                    mag_max = float(np.max(valid_mags))

                    # Set reasonable dB range (typical audio spectrum range)
                    if mag_max > mag_min:
                        # Add padding and ensure reasonable range
                        y_min = max(-120.0, mag_min - 10.0)
                        y_max = min(20.0, mag_max + 10.0)  # Allow up to +20 dB for peaks
                        self.ax.set_ylim(y_min, y_max)
                    else:
                        # Default range if all values are the same
                        self.ax.set_ylim(-100.0, -20.0)
                else:
                    # No valid data, clear the plot
                    self.spectrum_line.set_data([], [])
                    self.peak_line.set_data([], [])
                    self.peak_marker.set_offsets(np.empty((0, 2)))
                    self.freq_label.set_text('')
            else:
                # Data length mismatch or empty, clear the plot
                self.spectrum_line.set_data([], [])
                self.peak_line.set_data([], [])
                self.peak_marker.set_offsets(np.empty((0, 2)))
                self.freq_label.set_text('')

        return self.spectrum_line, self.peak_line, self.peak_marker, self.freq_label

    def start_visualization(self):
        """Start the visualization."""
        print("Starting FFT Stream Visualizer...")
        print(f"Connecting to WebSocket: ws://{self.host}:{self.port}")
        print("Make sure Friture is running with spectrum analysis and WebSocket streaming enabled.")

        # Start the WebSocket client
        self.ws_client.start()

        # Setup animation
        self.ani = animation.FuncAnimation(
            self.fig, self.update_plot, interval=50,  # 20 FPS
            blit=True, cache_frame_data=False
        )

        # Show the plot
        plt.tight_layout()
        plt.show()

    def stop_visualization(self):
        """Stop the visualization."""
        if self.ani:
            self.ani.event_source.stop()
        self.ws_client.stop()
        plt.close(self.fig)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="FFT Stream Visualizer - Real-time spectrum display from Friture's WebSocket API")
    parser.add_argument('--host', default='localhost', help='WebSocket server host (default: localhost)')
    parser.add_argument('--port', type=int, default=8765, help='WebSocket server port (default: 8765)')

    args = parser.parse_args()

    visualizer = None
    try:
        visualizer = FFTStreamVisualizer(host=args.host, port=args.port)
        visualizer.start_visualization()
    except KeyboardInterrupt:
        print("\nStopping visualization...")
        if visualizer:
            visualizer.stop_visualization()
    except Exception as e:
        logger.error(f"Application error: {e}")
        if visualizer:
            visualizer.stop_visualization()
        sys.exit(1)


if __name__ == "__main__":
    main()