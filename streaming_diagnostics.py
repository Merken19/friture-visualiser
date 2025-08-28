#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Friture Streaming Diagnostics Program

This program helps diagnose issues with Friture's streaming API setup.
Run this while Friture is running to check which widgets are being streamed.

Usage:
    python streaming_diagnostics.py --host localhost --port 8765
"""

import sys
import json
import asyncio
import websockets
import time
import argparse
from collections import defaultdict, Counter
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class StreamingDiagnostics:
    """Diagnostics tool for Friture streaming API."""

    def __init__(self, host='localhost', port=8765):
        self.host = host
        self.port = port
        self.websocket = None
        self.connected = False

        # Statistics
        self.messages_received = 0
        self.data_types_seen = set()
        self.data_type_counts = Counter()
        self.sample_counts = Counter()
        self.errors = 0
        self.start_time = time.time()

        # Store recent messages for analysis
        self.recent_messages = []
        self.max_recent_messages = 50

    async def connect_and_diagnose(self, duration_seconds=30):
        """Connect to WebSocket and collect diagnostics for specified duration."""
        uri = f"ws://{self.host}:{self.port}"

        try:
            logger.info(f"Connecting to {uri}...")
            self.websocket = await websockets.connect(uri)
            self.connected = True
            logger.info("Connected successfully!")

            logger.info(f"Collecting data for {duration_seconds} seconds...")

            # Set a timeout for the collection
            end_time = time.time() + duration_seconds

            while time.time() < end_time:
                try:
                    # Set a short timeout for receiving messages
                    message = await asyncio.wait_for(
                        self.websocket.recv(),
                        timeout=1.0
                    )

                    message_str = message.decode('utf-8') if isinstance(message, bytes) else str(message)
                    self._process_message(message_str)

                except asyncio.TimeoutError:
                    # No message received within timeout, continue
                    continue
                except websockets.exceptions.ConnectionClosed:
                    logger.warning("WebSocket connection closed")
                    break
                except Exception as e:
                    logger.error(f"Error receiving message: {e}")
                    self.errors += 1

        except Exception as e:
            logger.error(f"Connection error: {e}")
            self.errors += 1
        finally:
            if self.websocket:
                await self.websocket.close()
            self.connected = False

    def _process_message(self, message):
        """Process a received message."""
        try:
            self.messages_received += 1

            # Parse JSON
            data = json.loads(message)

            # Store recent message
            self.recent_messages.append({
                'timestamp': time.time(),
                'data': data
            })
            if len(self.recent_messages) > self.max_recent_messages:
                self.recent_messages.pop(0)

            # Extract metadata
            metadata = data.get('metadata', {})
            data_type = metadata.get('data_type', 'unknown')
            data_payload = data.get('data', {})

            # Update statistics
            self.data_types_seen.add(data_type)
            self.data_type_counts[data_type] += 1

            # Count samples (simplified)
            if data_type == 'levels' and 'peak_levels_db' in data_payload:
                self.sample_counts[data_type] += len(data_payload['peak_levels_db'])
            elif data_type in ['fft_spectrum', 'octave_spectrum'] and 'magnitudes_db' in data_payload:
                self.sample_counts[data_type] += len(data_payload['magnitudes_db'])
            elif data_type == 'spectrogram' and 'magnitudes_db' in data_payload:
                mags = data_payload['magnitudes_db']
                if isinstance(mags, list) and len(mags) > 0:
                    if isinstance(mags[0], list):
                        self.sample_counts[data_type] += sum(len(row) for row in mags)
                    else:
                        self.sample_counts[data_type] += len(mags)
            elif data_type == 'scope' and 'samples' in data_payload:
                samples = data_payload['samples']
                if isinstance(samples, list) and len(samples) > 0:
                    if isinstance(samples[0], list):
                        self.sample_counts[data_type] += sum(len(channel) for channel in samples)
                    else:
                        self.sample_counts[data_type] += len(samples)
            else:
                self.sample_counts[data_type] += 1

        except json.JSONDecodeError:
            logger.error("Invalid JSON received")
            self.errors += 1
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            self.errors += 1

    def print_diagnostics_report(self):
        """Print a comprehensive diagnostics report."""
        print("\n" + "="*60)
        print("Friture Streaming Diagnostics Report")
        print("="*60)

        # Connection status
        print(f"Connection Status: {'Connected' if self.connected else 'Disconnected'}")
        print(f"WebSocket URI: ws://{self.host}:{self.port}")

        # Timing
        elapsed = time.time() - self.start_time
        print(f"Duration: {elapsed:.1f}s")

        # Message statistics
        print("Message Statistics:")
        print(f"  Total Messages Received: {self.messages_received}")
        print(f"  Message Rate: {self.messages_received / elapsed:.2f} msg/s")
        print(f"  Errors: {self.errors}")

        # Data types
        print("Data Types Detected:")
        if self.data_types_seen:
            for data_type in sorted(self.data_types_seen):
                count = self.data_type_counts[data_type]
                samples = self.sample_counts[data_type]
                print(f"  {data_type}: {count} messages, {samples} samples")
        else:
            print("  No data types detected!")

        # Analysis
        print("Analysis:")
        expected_types = ['levels', 'fft_spectrum', 'octave_spectrum', 'spectrogram', 'scope', 'pitch_tracker', 'delay_estimator']

        missing_types = set(expected_types) - self.data_types_seen
        if missing_types:
            print(f"  Missing data types: {', '.join(sorted(missing_types))}")
            print("  These widgets may not be created or their producers may not be set up correctly.")
        else:
            print("  All expected data types are being streamed!")

        if self.messages_received == 0:
            print("  No messages received. Check if Friture is running and streaming is enabled.")
        elif len(self.data_types_seen) == 1 and 'levels' in self.data_types_seen:
            print("  Only levels data detected. This confirms the reported issue.")
            print("  Other widget producers may not be registered with the streaming API.")

        # Recent messages summary
        if self.recent_messages:
            print("Recent Messages (last 5):")
            for i, msg in enumerate(self.recent_messages[-5:]):
                data_type = msg['data'].get('metadata', {}).get('data_type', 'unknown')
                timestamp = time.strftime('%H:%M:%S', time.localtime(msg['timestamp']))
                print(f"  {i+1}. [{timestamp}] {data_type}")

        print("\n" + "="*60)


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Friture Streaming Diagnostics")
    parser.add_argument('--host', default='localhost', help='WebSocket server host')
    parser.add_argument('--port', type=int, default=8765, help='WebSocket server port')
    parser.add_argument('--duration', type=int, default=30, help='Duration to collect data (seconds)')

    args = parser.parse_args()

    print("Friture Streaming Diagnostics Tool")
    print("Make sure Friture is running with streaming enabled before running this tool.")
    print()

    diagnostics = StreamingDiagnostics(args.host, args.port)

    try:
        await diagnostics.connect_and_diagnose(args.duration)
    except KeyboardInterrupt:
        print("\nDiagnostics interrupted by user")

    diagnostics.print_diagnostics_report()


if __name__ == "__main__":
    asyncio.run(main())