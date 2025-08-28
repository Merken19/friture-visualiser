#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Friture Streaming API Test Client

This client tests the Friture streaming API by connecting to various protocols
and properly parsing all data types. It provides comprehensive statistics and
debugging information.

Usage:
    python test_stream.py --protocol websocket --host localhost --port 8765
    python test_stream.py --protocol tcp --host localhost --port 8766
    python test_stream.py --protocol udp --host localhost --port 8767
    python test_stream.py --protocol http_sse --host localhost --port 8768
"""

import asyncio
import json
import logging
import socket
import sys
import threading
import time
from collections import defaultdict, deque
from typing import Dict, Any, Optional, List
import argparse

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class StreamingStatistics:
    """Tracks streaming statistics for all data types."""

    def __init__(self):
        self.start_time = time.time()
        self.message_count = 0
        self.data_type_counts = defaultdict(int)
        self.data_type_samples = defaultdict(int)
        self.errors = 0
        self.last_message_time = None
        self.data_rate_history = deque(maxlen=100)  # Track data rates

    def record_message(self, data_type: str, sample_count: int = 1):
        """Record a received message."""
        self.message_count += 1
        self.data_type_counts[data_type] += 1
        self.data_type_samples[data_type] += sample_count
        self.last_message_time = time.time()

        # Calculate data rate
        elapsed = self.last_message_time - self.start_time
        if elapsed > 0:
            rate = self.message_count / elapsed
            self.data_rate_history.append(rate)

    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive statistics."""
        elapsed = time.time() - self.start_time
        avg_rate = sum(self.data_rate_history) / len(self.data_rate_history) if self.data_rate_history else 0

        return {
            'uptime_seconds': elapsed,
            'messages_received': self.message_count,
            'data_rate_msg_per_sec': avg_rate,
            'data_types_in_history': dict(self.data_type_counts),
            'samples_by_type': dict(self.data_type_samples),
            'total_samples': sum(self.data_type_samples.values()),
            'errors': self.errors,
            'last_message_seconds_ago': time.time() - (self.last_message_time or self.start_time)
        }


class WebSocketClient:
    """WebSocket client for testing streaming API."""

    def __init__(self, host: str, port: int, stats: StreamingStatistics):
        self.host = host
        self.port = port
        self.stats = stats
        self.websocket = None
        self.running = False

    async def connect(self):
        """Connect to WebSocket server."""
        try:
            import websockets
            uri = f"ws://{self.host}:{self.port}"
            logger.info(f"Connecting to WebSocket: {uri}")
            self.websocket = await websockets.connect(uri)
            logger.info("WebSocket connected successfully")
            return True
        except ImportError:
            logger.error("websockets library not installed. Install with: pip install websockets")
            return False
        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}")
            return False

    async def receive_messages(self):
        """Receive and process messages."""
        try:
            while self.running and self.websocket:
                data = await self.websocket.recv()
                message = data.decode('utf-8') if isinstance(data, bytes) else str(data)
                self._process_message(message)
        except Exception as e:
            logger.error(f"WebSocket receive error: {e}")
            self.stats.errors += 1

    def _process_message(self, message: str):
        """Process a received message."""
        try:
            data = json.loads(message)
            self._parse_streaming_data(data)
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            self.stats.errors += 1
        except Exception as e:
            logger.error(f"Message processing error: {e}")
            self.stats.errors += 1

    def _parse_streaming_data(self, data: Dict[str, Any]):
        """Parse streaming data and update statistics."""
        try:
            metadata = data.get('metadata', {})
            data_type = metadata.get('data_type', 'unknown')
            data_payload = data.get('data', {})

            # Count samples based on data type
            sample_count = self._count_samples(data_type, data_payload)

            self.stats.record_message(data_type, sample_count)

            # Log occasional messages for debugging
            if self.stats.message_count % 50 == 0:
                logger.info(f"Received {data_type} message #{self.stats.message_count}")

        except Exception as e:
            logger.error(f"Data parsing error: {e}")
            self.stats.errors += 1

    def _count_samples(self, data_type: str, data_payload: Dict[str, Any]) -> int:
        """Count samples in the data payload based on data type."""
        try:
            if data_type == 'levels':
                # Levels data has arrays for each channel
                if 'peak_levels_db' in data_payload:
                    return len(data_payload['peak_levels_db'])
                return 1

            elif data_type == 'fft_spectrum':
                # FFT spectrum has frequency and magnitude arrays
                if 'magnitudes_db' in data_payload:
                    return len(data_payload['magnitudes_db'])
                return 1

            elif data_type == 'octave_spectrum':
                # Octave spectrum has band energies
                if 'band_energies_db' in data_payload:
                    return len(data_payload['band_energies_db'])
                return 1

            elif data_type == 'spectrogram':
                # Spectrogram has 2D magnitude array
                if 'magnitudes_db' in data_payload:
                    mags = data_payload['magnitudes_db']
                    if isinstance(mags, list) and len(mags) > 0:
                        # If 2D array, count total elements
                        if isinstance(mags[0], list):
                            return sum(len(row) for row in mags)
                        else:
                            return len(mags)
                return 1

            elif data_type == 'scope':
                # Scope has sample arrays
                if 'samples' in data_payload:
                    samples = data_payload['samples']
                    if isinstance(samples, list) and len(samples) > 0:
                        if isinstance(samples[0], list):
                            # Multi-channel: count total samples
                            return sum(len(channel) for channel in samples)
                        else:
                            return len(samples)
                return 1

            elif data_type == 'pitch_tracker':
                # Pitch tracker has single values
                return 1

            elif data_type == 'delay_estimator':
                # Delay estimator has single values
                return 1

            else:
                # Unknown data type
                return 1

        except Exception as e:
            logger.warning(f"Error counting samples for {data_type}: {e}")
            return 1

    async def run(self) -> None:
        """Run the WebSocket client."""
        self.running = True

        if not await self.connect():
            return

        try:
            await self.receive_messages()
        except KeyboardInterrupt:
            logger.info("WebSocket client interrupted")
        finally:
            if self.websocket:
                await self.websocket.close()
            self.running = False


class TCPClient:
    """TCP client for testing streaming API."""

    def __init__(self, host: str, port: int, stats: StreamingStatistics):
        self.host = host
        self.port = port
        self.stats = stats
        self.socket = None
        self.running = False

    def connect(self) -> bool:
        """Connect to TCP server."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            logger.info(f"TCP connected to {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"TCP connection failed: {e}")
            return False

    def receive_messages(self):
        """Receive and process TCP messages."""
        buffer = ""

        try:
            while self.running and self.socket:
                data = self.socket.recv(4096).decode('utf-8')
                if not data:
                    break

                buffer += data

                # Process complete messages (framed by length prefix)
                while '\n' in buffer:
                    line_end = buffer.find('\n')
                    line = buffer[:line_end]
                    buffer = buffer[line_end + 1:]

                    if line.strip():
                        self._process_message(line)

        except Exception as e:
            logger.error(f"TCP receive error: {e}")
            self.stats.errors += 1

    def _process_message(self, message: str):
        """Process a received TCP message."""
        try:
            # TCP messages have format: "length\njson_data"
            if '\n' in message:
                length_str, json_data = message.split('\n', 1)
                data = json.loads(json_data)
                self._parse_streaming_data(data)
            else:
                # Try parsing as direct JSON
                data = json.loads(message)
                self._parse_streaming_data(data)
        except json.JSONDecodeError as e:
            logger.error(f"TCP JSON decode error: {e}")
            self.stats.errors += 1
        except Exception as e:
            logger.error(f"TCP message processing error: {e}")
            self.stats.errors += 1

    def _parse_streaming_data(self, data: Dict[str, Any]):
        """Parse streaming data and update statistics."""
        try:
            metadata = data.get('metadata', {})
            data_type = metadata.get('data_type', 'unknown')
            data_payload = data.get('data', {})

            # Count samples based on data type
            sample_count = self._count_samples(data_type, data_payload)

            self.stats.record_message(data_type, sample_count)

            # Log occasional messages for debugging
            if self.stats.message_count % 50 == 0:
                logger.info(f"TCP: Received {data_type} message #{self.stats.message_count}")

        except Exception as e:
            logger.error(f"TCP data parsing error: {e}")
            self.stats.errors += 1

    def _count_samples(self, data_type: str, data_payload: Dict[str, Any]) -> int:
        """Count samples in the data payload based on data type."""
        # Same logic as WebSocket client
        try:
            if data_type == 'levels':
                if 'peak_levels_db' in data_payload:
                    return len(data_payload['peak_levels_db'])
                return 1

            elif data_type == 'fft_spectrum':
                if 'magnitudes_db' in data_payload:
                    return len(data_payload['magnitudes_db'])
                return 1

            elif data_type == 'octave_spectrum':
                if 'band_energies_db' in data_payload:
                    return len(data_payload['band_energies_db'])
                return 1

            elif data_type == 'spectrogram':
                if 'magnitudes_db' in data_payload:
                    mags = data_payload['magnitudes_db']
                    if isinstance(mags, list) and len(mags) > 0:
                        if isinstance(mags[0], list):
                            return sum(len(row) for row in mags)
                        else:
                            return len(mags)
                return 1

            elif data_type == 'scope':
                if 'samples' in data_payload:
                    samples = data_payload['samples']
                    if isinstance(samples, list) and len(samples) > 0:
                        if isinstance(samples[0], list):
                            return sum(len(channel) for channel in samples)
                        else:
                            return len(samples)
                return 1

            elif data_type == 'pitch_tracker':
                return 1

            elif data_type == 'delay_estimator':
                return 1

            else:
                return 1

        except Exception as e:
            logger.warning(f"Error counting samples for {data_type}: {e}")
            return 1

    def run(self):
        """Run the TCP client."""
        self.running = True

        if not self.connect():
            return

        try:
            self.receive_messages()
        except KeyboardInterrupt:
            logger.info("TCP client interrupted")
        finally:
            if self.socket:
                self.socket.close()
            self.running = False


class UDPClient:
    """UDP client for testing streaming API."""

    def __init__(self, host: str, port: int, stats: StreamingStatistics):
        self.host = host
        self.port = port
        self.stats = stats
        self.socket = None
        self.running = False

    def connect(self) -> bool:
        """Setup UDP socket."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.bind(('0.0.0.0', 0))  # Bind to any available port
            logger.info(f"UDP client bound to any port, expecting data from {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"UDP setup failed: {e}")
            return False

    def receive_messages(self):
        """Receive and process UDP messages."""
        try:
            while self.running and self.socket:
                data, addr = self.socket.recvfrom(65536)  # Max UDP payload
                message = data.decode('utf-8')
                self._process_message(message)
        except Exception as e:
            logger.error(f"UDP receive error: {e}")
            self.stats.errors += 1

    def _process_message(self, message: str):
        """Process a received UDP message."""
        try:
            data = json.loads(message)
            self._parse_streaming_data(data)
        except json.JSONDecodeError as e:
            logger.error(f"UDP JSON decode error: {e}")
            self.stats.errors += 1
        except Exception as e:
            logger.error(f"UDP message processing error: {e}")
            self.stats.errors += 1

    def _parse_streaming_data(self, data: Dict[str, Any]):
        """Parse streaming data and update statistics."""
        try:
            metadata = data.get('metadata', {})
            data_type = metadata.get('data_type', 'unknown')
            data_payload = data.get('data', {})

            sample_count = self._count_samples(data_type, data_payload)
            self.stats.record_message(data_type, sample_count)

            if self.stats.message_count % 50 == 0:
                logger.info(f"UDP: Received {data_type} message #{self.stats.message_count}")

        except Exception as e:
            logger.error(f"UDP data parsing error: {e}")
            self.stats.errors += 1

    def _count_samples(self, data_type: str, data_payload: Dict[str, Any]) -> int:
        """Count samples - same logic as other clients."""
        try:
            if data_type == 'levels':
                if 'peak_levels_db' in data_payload:
                    return len(data_payload['peak_levels_db'])
                return 1

            elif data_type == 'fft_spectrum':
                if 'magnitudes_db' in data_payload:
                    return len(data_payload['magnitudes_db'])
                return 1

            elif data_type == 'octave_spectrum':
                if 'band_energies_db' in data_payload:
                    return len(data_payload['band_energies_db'])
                return 1

            elif data_type == 'spectrogram':
                if 'magnitudes_db' in data_payload:
                    mags = data_payload['magnitudes_db']
                    if isinstance(mags, list) and len(mags) > 0:
                        if isinstance(mags[0], list):
                            return sum(len(row) for row in mags)
                        else:
                            return len(mags)
                return 1

            elif data_type == 'scope':
                if 'samples' in data_payload:
                    samples = data_payload['samples']
                    if isinstance(samples, list) and len(samples) > 0:
                        if isinstance(samples[0], list):
                            return sum(len(channel) for channel in samples)
                        else:
                            return len(samples)
                return 1

            elif data_type == 'pitch_tracker':
                return 1

            elif data_type == 'delay_estimator':
                return 1

            else:
                return 1

        except Exception as e:
            logger.warning(f"Error counting samples for {data_type}: {e}")
            return 1

    def run(self):
        """Run the UDP client."""
        self.running = True

        if not self.connect():
            return

        try:
            self.receive_messages()
        except KeyboardInterrupt:
            logger.info("UDP client interrupted")
        finally:
            if self.socket:
                self.socket.close()
            self.running = False


class HTTPSSEClient:
    """HTTP Server-Sent Events client for testing streaming API."""

    def __init__(self, host: str, port: int, stats: StreamingStatistics):
        self.host = host
        self.port = port
        self.stats = stats
        self.socket = None
        self.running = False

    def connect(self) -> bool:
        """Connect to HTTP SSE server."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))

            # Send HTTP request for SSE
            request = (
                "GET / HTTP/1.1\r\n"
                f"Host: {self.host}:{self.port}\r\n"
                "Accept: text/event-stream\r\n"
                "Cache-Control: no-cache\r\n"
                "Connection: keep-alive\r\n"
                "\r\n"
            )
            self.socket.send(request.encode('utf-8'))
            logger.info(f"HTTP SSE connected to {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"HTTP SSE connection failed: {e}")
            return False

    def receive_messages(self):
        """Receive and process SSE messages."""
        buffer = ""

        try:
            while self.running and self.socket:
                data = self.socket.recv(4096).decode('utf-8')
                if not data:
                    break

                buffer += data

                # Process SSE messages
                while '\n\n' in buffer:
                    message_end = buffer.find('\n\n')
                    message = buffer[:message_end]
                    buffer = buffer[message_end + 2:]

                    if message.strip():
                        self._process_sse_message(message)

        except Exception as e:
            logger.error(f"HTTP SSE receive error: {e}")
            self.stats.errors += 1

    def _process_sse_message(self, message: str):
        """Process an SSE message."""
        try:
            # Parse SSE format: "data: json_string\n\n"
            lines = message.split('\n')
            json_data = None

            for line in lines:
                if line.startswith('data: '):
                    json_data = line[6:]  # Remove 'data: ' prefix
                    break

            if json_data:
                data = json.loads(json_data)
                self._parse_streaming_data(data)
            else:
                logger.warning(f"No data found in SSE message: {message}")

        except json.JSONDecodeError as e:
            logger.error(f"HTTP SSE JSON decode error: {e}")
            self.stats.errors += 1
        except Exception as e:
            logger.error(f"HTTP SSE message processing error: {e}")
            self.stats.errors += 1

    def _parse_streaming_data(self, data: Dict[str, Any]):
        """Parse streaming data and update statistics."""
        try:
            metadata = data.get('metadata', {})
            data_type = metadata.get('data_type', 'unknown')
            data_payload = data.get('data', {})

            sample_count = self._count_samples(data_type, data_payload)
            self.stats.record_message(data_type, sample_count)

            if self.stats.message_count % 50 == 0:
                logger.info(f"HTTP SSE: Received {data_type} message #{self.stats.message_count}")

        except Exception as e:
            logger.error(f"HTTP SSE data parsing error: {e}")
            self.stats.errors += 1

    def _count_samples(self, data_type: str, data_payload: Dict[str, Any]) -> int:
        """Count samples - same logic as other clients."""
        try:
            if data_type == 'levels':
                if 'peak_levels_db' in data_payload:
                    return len(data_payload['peak_levels_db'])
                return 1

            elif data_type == 'fft_spectrum':
                if 'magnitudes_db' in data_payload:
                    return len(data_payload['magnitudes_db'])
                return 1

            elif data_type == 'octave_spectrum':
                if 'band_energies_db' in data_payload:
                    return len(data_payload['band_energies_db'])
                return 1

            elif data_type == 'spectrogram':
                if 'magnitudes_db' in data_payload:
                    mags = data_payload['magnitudes_db']
                    if isinstance(mags, list) and len(mags) > 0:
                        if isinstance(mags[0], list):
                            return sum(len(row) for row in mags)
                        else:
                            return len(mags)
                return 1

            elif data_type == 'scope':
                if 'samples' in data_payload:
                    samples = data_payload['samples']
                    if isinstance(samples, list) and len(samples) > 0:
                        if isinstance(samples[0], list):
                            return sum(len(channel) for channel in samples)
                        else:
                            return len(samples)
                return 1

            elif data_type == 'pitch_tracker':
                return 1

            elif data_type == 'delay_estimator':
                return 1

            else:
                return 1

        except Exception as e:
            logger.warning(f"Error counting samples for {data_type}: {e}")
            return 1

    def run(self):
        """Run the HTTP SSE client."""
        self.running = True

        if not self.connect():
            return

        try:
            self.receive_messages()
        except KeyboardInterrupt:
            logger.info("HTTP SSE client interrupted")
        finally:
            if self.socket:
                self.socket.close()
            self.running = False


def print_statistics(stats: StreamingStatistics):
    """Print formatted statistics."""
    print("\n" + "="*60)
    print("STREAMING STATISTICS")
    print("="*60)

    stat_data = stats.get_statistics()

    print(f"Uptime: {stat_data['uptime_seconds']:.1f}s")
    print(f"Messages received: {stat_data['messages_received']}")
    print(f"Data rate: {stat_data['data_rate_msg_per_sec']:.1f} msg/s")
    print(f"Total samples: {stat_data['total_samples']}")
    print(f"Errors: {stat_data['errors']}")

    print("\nData types in history:")
    for data_type, count in stat_data['data_types_in_history'].items():
        samples = stat_data['samples_by_type'].get(data_type, 0)
        print(f"  {data_type}: {count} messages, {samples} samples")

    print("="*60)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Friture Streaming API Test Client")
    parser.add_argument('--protocol', choices=['websocket', 'tcp', 'udp', 'http_sse'],
                       default='websocket', help='Protocol to use (default: websocket)')
    parser.add_argument('--host', default='localhost', help='Server host (default: localhost)')
    parser.add_argument('--port', type=int, help='Server port')
    parser.add_argument('--stats-interval', type=float, default=5.0,
                       help='Statistics print interval in seconds (default: 5.0)')

    args = parser.parse_args()

    # Set default ports based on protocol
    if args.port is None:
        port_map = {
            'websocket': 8765,
            'tcp': 8766,
            'udp': 8767,
            'http_sse': 8768
        }
        args.port = port_map[args.protocol]

    logger.info(f"Starting {args.protocol.upper()} client connecting to {args.host}:{args.port}")

    # Create statistics tracker
    stats = StreamingStatistics()

    # Create appropriate client
    client = None
    if args.protocol == 'websocket':
        client = WebSocketClient(args.host, args.port, stats)
    elif args.protocol == 'tcp':
        client = TCPClient(args.host, args.port, stats)
    elif args.protocol == 'udp':
        client = UDPClient(args.host, args.port, stats)
    elif args.protocol == 'http_sse':
        client = HTTPSSEClient(args.host, args.port, stats)

    if client is None:
        logger.error(f"Unknown protocol: {args.protocol}")
        return

    # Start statistics printing thread
    def stats_printer():
        while True:
            time.sleep(args.stats_interval)
            print_statistics(stats)

    stats_thread = threading.Thread(target=stats_printer, daemon=True)
    stats_thread.start()

    try:
        if args.protocol == 'websocket':
            # WebSocket needs asyncio
            if client:
                asyncio.run(client.run())
        else:
            # Other protocols use synchronous sockets
            if client:
                client.run()
    except KeyboardInterrupt:
        logger.info("Client interrupted by user")
    finally:
        print_statistics(stats)
        logger.info("Client stopped")


if __name__ == "__main__":
    main()