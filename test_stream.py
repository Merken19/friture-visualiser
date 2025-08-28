#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Friture Streaming API Client

A comprehensive Python client for receiving and displaying real-time
audio analysis data from the Friture Streaming API.

Supports multiple connection types:
- WebSocket (default)
- TCP
- UDP
- HTTP Server-Sent Events

Features:
- Real-time data visualization
- Multiple data type support
- Connection management
- Performance monitoring
- Configurable display options
"""

import asyncio
import json
import socket
import threading
import time
import argparse
import sys
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
from collections import deque
import numpy as np

try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    print("Warning: websockets not available. Install with: pip install websockets")

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("Warning: requests not available. Install with: pip install requests")

try:
    import matplotlib.pyplot as plt
    import matplotlib.animation as animation
    from matplotlib.collections import LineCollection
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("Warning: matplotlib not available. Install with: pip install matplotlib")


@dataclass
class ClientConfig:
    """Client configuration options."""
    host: str = 'localhost'
    port: int = 8765
    protocol: str = 'websocket'  # websocket, tcp, udp, sse
    display_mode: str = 'console'  # console, plot, both
    max_history: int = 100
    update_interval: float = 0.1
    show_statistics: bool = True
    filter_data_types: list = None  # None means show all


class DataDisplay:
    """Handles display of streaming data."""
    
    def __init__(self, config: ClientConfig):
        self.config = config
        self.data_history = {
            'pitch': deque(maxlen=config.max_history),
            'spectrum': deque(maxlen=config.max_history),
            'levels': deque(maxlen=config.max_history),
            'octave': deque(maxlen=config.max_history)
        }
        self.statistics = {
            'messages_received': 0,
            'data_rate': 0.0,
            'last_update': time.time(),
            'connection_time': time.time()
        }
        
        # Setup plotting if available and requested
        self.plot_enabled = (MATPLOTLIB_AVAILABLE and 
                           self.config.display_mode in ['plot', 'both'])
        if self.plot_enabled:
            self.setup_plotting()
    
    def setup_plotting(self):
        """Setup matplotlib plotting."""
        plt.ion()  # Interactive mode
        self.fig, self.axes = plt.subplots(2, 2, figsize=(12, 8))
        self.fig.suptitle('Friture Streaming Data')
        
        # Pitch plot
        self.pitch_ax = self.axes[0, 0]
        self.pitch_ax.set_title('Pitch Tracking')
        self.pitch_ax.set_xlabel('Time')
        self.pitch_ax.set_ylabel('Frequency (Hz)')
        self.pitch_line, = self.pitch_ax.plot([], [], 'b-', label='Frequency')
        self.pitch_ax.legend()
        
        # Spectrum plot
        self.spectrum_ax = self.axes[0, 1]
        self.spectrum_ax.set_title('FFT Spectrum')
        self.spectrum_ax.set_xlabel('Frequency (Hz)')
        self.spectrum_ax.set_ylabel('Magnitude (dB)')
        self.spectrum_line, = self.spectrum_ax.plot([], [], 'g-')
        
        # Levels plot
        self.levels_ax = self.axes[1, 0]
        self.levels_ax.set_title('Audio Levels')
        self.levels_ax.set_xlabel('Channel')
        self.levels_ax.set_ylabel('Level (dB)')
        self.levels_bars = None
        
        # Octave plot
        self.octave_ax = self.axes[1, 1]
        self.octave_ax.set_title('Octave Analysis')
        self.octave_ax.set_xlabel('Frequency Band')
        self.octave_ax.set_ylabel('Energy (dB)')
        self.octave_bars = None
        
        plt.tight_layout()
        plt.show()
    
    def update_statistics(self):
        """Update statistics."""
        current_time = time.time()
        self.statistics['messages_received'] += 1
        
        # Calculate data rate (messages per second)
        time_diff = current_time - self.statistics['last_update']
        if time_diff >= 1.0:  # Update rate every second
            self.statistics['data_rate'] = 1.0 / time_diff if time_diff > 0 else 0
            self.statistics['last_update'] = current_time
    
    def display_data(self, data: Dict[str, Any]):
        """Display received data."""
        self.update_statistics()
        
        data_type = data.get('type', 'unknown')
        timestamp = data.get('timestamp', time.time())
        
        # Filter data types if specified
        if (self.config.filter_data_types and 
            data_type not in self.config.filter_data_types):
            return
        
        # Store data in history
        if data_type in self.data_history:
            self.data_history[data_type].append({
                'timestamp': timestamp,
                'data': data.get('data', {})
            })
        
        # Console display
        if self.config.display_mode in ['console', 'both']:
            self.display_console(data_type, data.get('data', {}), timestamp)
        
        # Plot display
        if self.plot_enabled:
            self.update_plots()
    
    def display_console(self, data_type: str, data: Dict[str, Any], timestamp: float):
        """Display data in console."""
        if data_type == 'pitch':
            freq = data.get('frequency')
            note = data.get('note')
            confidence = data.get('confidence', 0)
            
            if freq and confidence > 0.5:
                print(f"[PITCH] {note} ({freq:.1f} Hz) - "
                      f"Confidence: {confidence:.2f}")
            else:
                print("[PITCH] No pitch detected")
        
        elif data_type == 'spectrum':
            peak_freq = data.get('peak_frequency', 0)
            frequencies = data.get('frequencies', [])
            magnitudes = data.get('magnitudes', [])
            
            if frequencies and magnitudes:
                print(f"[SPECTRUM] Peak: {peak_freq:.1f} Hz - "
                      f"Bins: {len(frequencies)}")
            
        elif data_type == 'levels':
            peak_levels = data.get('peak_levels', [])
            rms_levels = data.get('rms_levels', [])
            
            if peak_levels:
                avg_peak = np.mean(peak_levels)
                avg_rms = np.mean(rms_levels) if rms_levels else 0
                print(f"[LEVELS] Peak: {avg_peak:.1f} dB - "
                      f"RMS: {avg_rms:.1f} dB")
        
        elif data_type == 'octave':
            bands = data.get('band_energies_db', [])
            labels = data.get('band_labels', [])
            
            if bands:
                max_energy = max(bands)
                max_idx = bands.index(max_energy)
                band_name = labels[max_idx] if max_idx < len(labels) else f"Band {max_idx}"
                print(f"[OCTAVE] Peak: {band_name} ({max_energy:.1f} dB)")
        
        # Show statistics periodically
        if (self.config.show_statistics and 
            self.statistics['messages_received'] % 50 == 0):
            self.show_statistics()
    
    def update_plots(self):
        """Update matplotlib plots."""
        if not self.plot_enabled:
            return
        
        try:
            # Update pitch plot
            if self.data_history['pitch']:
                pitch_data = list(self.data_history['pitch'])
                times = [d['timestamp'] for d in pitch_data]
                frequencies = [d['data'].get('frequency', 0) for d in pitch_data]
                
                # Normalize times
                if times:
                    start_time = times[0]
                    times = [(t - start_time) for t in times]
                
                self.pitch_line.set_data(times, frequencies)
                if frequencies:
                    self.pitch_ax.set_xlim(0, max(times) if times else 1)
                    self.pitch_ax.set_ylim(0, max(frequencies) * 1.1 if max(frequencies) > 0 else 1000)
            
            # Update spectrum plot
            if self.data_history['spectrum']:
                spectrum_data = list(self.data_history['spectrum'])[-1]  # Latest
                frequencies = spectrum_data['data'].get('frequencies', [])
                magnitudes = spectrum_data['data'].get('magnitudes', [])
                
                if frequencies and magnitudes:
                    self.spectrum_line.set_data(frequencies, magnitudes)
                    self.spectrum_ax.set_xlim(min(frequencies), max(frequencies))
                    self.spectrum_ax.set_ylim(min(magnitudes), max(magnitudes))
            
            # Update levels plot
            if self.data_history['levels']:
                levels_data = list(self.data_history['levels'])[-1]  # Latest
                peak_levels = levels_data['data'].get('peak_levels', [])
                
                if peak_levels:
                    channels = list(range(len(peak_levels)))
                    
                    if self.levels_bars:
                        for bar, level in zip(self.levels_bars, peak_levels):
                            bar.set_height(level)
                    else:
                        self.levels_bars = self.levels_ax.bar(channels, peak_levels)
                    
                    self.levels_ax.set_ylim(-60, 0)  # Typical dB FS range
            
            # Update octave plot
            if self.data_history['octave']:
                octave_data = list(self.data_history['octave'])[-1]  # Latest
                band_energies = octave_data['data'].get('band_energies_db', [])
                band_labels = octave_data['data'].get('band_labels', [])
                
                if band_energies:
                    positions = list(range(len(band_energies)))
                    
                    if self.octave_bars:
                        for bar, energy in zip(self.octave_bars, band_energies):
                            bar.set_height(energy)
                    else:
                        self.octave_bars = self.octave_ax.bar(positions, band_energies)
                        if band_labels:
                            self.octave_ax.set_xticks(positions)
                            self.octave_ax.set_xticklabels(band_labels, rotation=45)
            
            plt.draw()
            plt.pause(0.001)  # Small pause to allow GUI update
            
        except Exception as e:
            print(f"Error updating plots: {e}")
    
    def show_statistics(self):
        """Show connection and data statistics."""
        uptime = time.time() - self.statistics['connection_time']
        print(f"\n=== STATISTICS ===")
        print(f"Uptime: {uptime:.1f}s")
        print(f"Messages received: {self.statistics['messages_received']}")
        print(f"Data rate: {self.statistics['data_rate']:.1f} msg/s")
        print(f"Data types in history:")
        for data_type, history in self.data_history.items():
            print(f"  {data_type}: {len(history)} samples")
        print("==================\n")


class WebSocketClient:
    """WebSocket client implementation."""
    
    def __init__(self, config: ClientConfig, display: DataDisplay):
        self.config = config
        self.display = display
        self.websocket = None
        self.running = False
    
    async def connect(self):
        """Connect to WebSocket server."""
        if not WEBSOCKETS_AVAILABLE:
            raise Exception("websockets library not available")
        
        uri = f"ws://{self.config.host}:{self.config.port}"
        print(f"Connecting to WebSocket: {uri}")
        
        try:
            self.websocket = await websockets.connect(uri)
            self.running = True
            print("WebSocket connected successfully")
            
            # Listen for messages
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    self.display.display_data(data)
                except json.JSONDecodeError as e:
                    print(f"Error decoding JSON: {e}")
                except Exception as e:
                    print(f"Error processing message: {e}")
                    
        except Exception as e:
            print(f"WebSocket connection error: {e}")
            self.running = False
    
    async def disconnect(self):
        """Disconnect from WebSocket server."""
        self.running = False
        if self.websocket:
            await self.websocket.close()
            print("WebSocket disconnected")


class TCPClient:
    """TCP client implementation."""
    
    def __init__(self, config: ClientConfig, display: DataDisplay):
        self.config = config
        self.display = display
        self.socket = None
        self.running = False
    
    def connect(self):
        """Connect to TCP server."""
        print(f"Connecting to TCP: {self.config.host}:{self.config.port}")
        
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.config.host, self.config.port))
            self.running = True
            print("TCP connected successfully")
            
            # Start receiving thread
            receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
            receive_thread.start()
            
        except Exception as e:
            print(f"TCP connection error: {e}")
            self.running = False
    
    def _receive_loop(self):
        """Receive data loop."""
        buffer = b''
        
        while self.running:
            try:
                # Read data
                data = self.socket.recv(4096)
                if not data:
                    break
                
                buffer += data
                
                # Process complete messages
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    
                    try:
                        # Check if line contains length prefix
                        if line.startswith(b'{'):
                            # Direct JSON message
                            message_data = json.loads(line.decode('utf-8'))
                        else:
                            # Length-prefixed message
                            length = int(line.decode('utf-8'))
                            
                            # Read the actual message
                            while len(buffer) < length:
                                more_data = self.socket.recv(length - len(buffer))
                                if not more_data:
                                    break
                                buffer += more_data
                            
                            message_bytes = buffer[:length]
                            buffer = buffer[length:]
                            message_data = json.loads(message_bytes.decode('utf-8'))
                        
                        self.display.display_data(message_data)
                        
                    except (json.JSONDecodeError, ValueError) as e:
                        print(f"Error decoding message: {e}")
                    except Exception as e:
                        print(f"Error processing message: {e}")
                        
            except Exception as e:
                if self.running:
                    print(f"TCP receive error: {e}")
                break
    
    def disconnect(self):
        """Disconnect from TCP server."""
        self.running = False
        if self.socket:
            self.socket.close()
            print("TCP disconnected")


class UDPClient:
    """UDP client implementation."""
    
    def __init__(self, config: ClientConfig, display: DataDisplay):
        self.config = config
        self.display = display
        self.socket = None
        self.running = False
    
    def connect(self):
        """Setup UDP client."""
        print(f"Setting up UDP client on port {self.config.port}")
        
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.bind(('', self.config.port))  # Bind to receive data
            self.running = True
            print("UDP client ready")
            
            # Start receiving thread
            receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
            receive_thread.start()
            
        except Exception as e:
            print(f"UDP setup error: {e}")
            self.running = False
    
    def _receive_loop(self):
        """Receive data loop."""
        while self.running:
            try:
                data, addr = self.socket.recvfrom(65536)
                message_data = json.loads(data.decode('utf-8'))
                self.display.display_data(message_data)
                
            except json.JSONDecodeError as e:
                print(f"Error decoding UDP message: {e}")
            except Exception as e:
                if self.running:
                    print(f"UDP receive error: {e}")
    
    def disconnect(self):
        """Disconnect UDP client."""
        self.running = False
        if self.socket:
            self.socket.close()
            print("UDP client stopped")


class SSEClient:
    """Server-Sent Events client implementation."""
    
    def __init__(self, config: ClientConfig, display: DataDisplay):
        self.config = config
        self.display = display
        self.running = False
    
    def connect(self):
        """Connect to SSE server."""
        if not REQUESTS_AVAILABLE:
            raise Exception("requests library not available")
        
        url = f"http://{self.config.host}:{self.config.port}"
        print(f"Connecting to SSE: {url}")
        
        try:
            self.running = True
            
            # Start receiving thread
            receive_thread = threading.Thread(target=self._receive_loop, args=(url,), daemon=True)
            receive_thread.start()
            
        except Exception as e:
            print(f"SSE connection error: {e}")
            self.running = False
    
    def _receive_loop(self, url):
        """Receive SSE data loop."""
        try:
            response = requests.get(url, stream=True, headers={'Accept': 'text/event-stream'})
            response.raise_for_status()
            print("SSE connected successfully")
            
            for line in response.iter_lines(decode_unicode=True):
                if not self.running:
                    break
                
                if line.startswith('data: '):
                    try:
                        json_data = line[6:]  # Remove 'data: ' prefix
                        message_data = json.loads(json_data)
                        self.display.display_data(message_data)
                    except json.JSONDecodeError as e:
                        print(f"Error decoding SSE message: {e}")
                    except Exception as e:
                        print(f"Error processing SSE message: {e}")
                        
        except Exception as e:
            if self.running:
                print(f"SSE receive error: {e}")
    
    def disconnect(self):
        """Disconnect SSE client."""
        self.running = False
        print("SSE client stopped")


class FritureStreamingClient:
    """Main client class."""
    
    def __init__(self, config: ClientConfig):
        self.config = config
        self.display = DataDisplay(config)
        self.client = None
        self.running = False
        
        # Create appropriate client
        if config.protocol == 'websocket':
            self.client = WebSocketClient(config, self.display)
        elif config.protocol == 'tcp':
            self.client = TCPClient(config, self.display)
        elif config.protocol == 'udp':
            self.client = UDPClient(config, self.display)
        elif config.protocol == 'sse':
            self.client = SSEClient(config, self.display)
        else:
            raise ValueError(f"Unsupported protocol: {config.protocol}")
    
    async def start(self):
        """Start the client."""
        print(f"Starting Friture Streaming Client")
        print(f"Protocol: {self.config.protocol}")
        print(f"Host: {self.config.host}:{self.config.port}")
        print(f"Display mode: {self.config.display_mode}")
        print("Press Ctrl+C to stop\n")
        
        self.running = True
        
        try:
            if isinstance(self.client, WebSocketClient):
                await self.client.connect()
            else:
                self.client.connect()
                
                # Keep the main thread alive for non-async clients
                while self.running:
                    await asyncio.sleep(0.1)
                    
        except KeyboardInterrupt:
            print("\nShutting down...")
        except Exception as e:
            print(f"Client error: {e}")
        finally:
            await self.stop()
    
    async def stop(self):
        """Stop the client."""
        self.running = False
        
        try:
            if isinstance(self.client, WebSocketClient):
                await self.client.disconnect()
            else:
                self.client.disconnect()
        except Exception as e:
            print(f"Error during shutdown: {e}")
        
        # Show final statistics
        if self.config.show_statistics:
            self.display.show_statistics()


def create_parser():
    """Create command line argument parser."""
    parser = argparse.ArgumentParser(description='Friture Streaming API Client')
    
    parser.add_argument('--host', default='localhost',
                        help='Server host (default: localhost)')
    parser.add_argument('--port', type=int, default=8765,
                        help='Server port (default: 8765)')
    parser.add_argument('--protocol', choices=['websocket', 'tcp', 'udp', 'sse'],
                        default='websocket', help='Protocol to use (default: websocket)')
    parser.add_argument('--display', choices=['console', 'plot', 'both'],
                        default='console', help='Display mode (default: console)')
    parser.add_argument('--max-history', type=int, default=100,
                        help='Maximum history size (default: 100)')
    parser.add_argument('--filter', nargs='+',
                        choices=['pitch', 'spectrum', 'levels', 'octave'],
                        help='Filter specific data types')
    parser.add_argument('--no-stats', action='store_true',
                        help='Disable statistics display')
    
    return parser


async def main():
    """Main function."""
    parser = create_parser()
    args = parser.parse_args()
    
    # Create configuration
    config = ClientConfig(
        host=args.host,
        port=args.port,
        protocol=args.protocol,
        display_mode=args.display,
        max_history=args.max_history,
        filter_data_types=args.filter,
        show_statistics=not args.no_stats
    )
    
    # Check dependencies
    if config.protocol == 'websocket' and not WEBSOCKETS_AVAILABLE:
        print("Error: websockets library required for WebSocket protocol")
        print("Install with: pip install websockets")
        sys.exit(1)
    
    if config.protocol == 'sse' and not REQUESTS_AVAILABLE:
        print("Error: requests library required for SSE protocol")
        print("Install with: pip install requests")
        sys.exit(1)
    
    if config.display_mode in ['plot', 'both'] and not MATPLOTLIB_AVAILABLE:
        print("Warning: matplotlib not available, falling back to console mode")
        config.display_mode = 'console'
    
    # Create and start client
    client = FritureStreamingClient(config)
    await client.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)