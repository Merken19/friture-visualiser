#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Friture Streaming Information Visualizer

A real-time GUI application for visualizing Friture's streaming API data.
Displays beautiful visualizations for all available data types alongside the latest raw message.
Features crash-resistant design with memory-efficient message handling and copy functionality.

Usage:
    python stream_information_visualiser.py --host localhost --port 8765

Features:
- Real-time visualizations for all Friture data types (levels, spectrum, pitch, octave, scope, delay)
- Memory-efficient raw message display (shows only the latest message)
- Copy-to-clipboard functionality for raw messages
- Comprehensive statistics and connection monitoring
- Crash-resistant design with proper error handling
- Octave-scaled frequency spectrum display with lower frequency visibility

Configuration Notes:
- For 25ms response time: Set response_time=0.025 in the source spectrum widget
- Spectrum uses octave scaling (log2) for better musical frequency representation
- Lower frequencies (down to 20Hz) are now visible in the display
"""

import sys
import json
import logging
import asyncio
import threading
import time
from collections import deque
from typing import Dict, Any, Optional, List
import argparse

import numpy as np
from PyQt5.QtCore import (
    Qt, QTimer, QObject, pyqtSignal, QThread, QRectF, QPointF
)
from PyQt5.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QFontMetrics, QPainterPath
)
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTextEdit, QLabel, QFrame, QGroupBox, QGridLayout,
    QProgressBar, QPushButton, QMenuBar, QStatusBar, QAction,
    QSizePolicy, QScrollArea
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class StreamingWebSocketClient(QObject):
    """WebSocket client for receiving streaming data."""

    # Signals
    dataReceived = pyqtSignal(dict)  # Parsed streaming data
    rawMessageReceived = pyqtSignal(str)  # Raw JSON message
    connectionStatusChanged = pyqtSignal(str)  # "connected", "disconnected", "connecting"
    errorOccurred = pyqtSignal(str)  # Error message
    statisticsUpdated = pyqtSignal(dict)  # Statistics data

    def __init__(self, host: str = 'localhost', port: int = 8765, parent=None):
        super().__init__(parent)
        self.host = host
        self.port = port
        self.websocket = None
        self.running = False
        self.connected = False
        self._client_thread = None

        # Statistics
        self.message_count = 0
        self.start_time = time.time()
        self.data_type_counts = {}
        self.data_type_samples = {}
        self.errors = 0

        # Message history for raw display
        self.raw_message_history = deque(maxlen=100)

    def start(self):
        """Start the WebSocket client in a separate thread."""
        if self.running:
            return

        self.running = True
        self.connectionStatusChanged.emit("connecting")

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
            self.errorOccurred.emit(str(e))

    async def _connect_and_listen(self):
        """Connect to WebSocket and listen for messages."""
        try:
            import websockets

            uri = f"ws://{self.host}:{self.port}"
            logger.info(f"Connecting to WebSocket: {uri}")

            self.websocket = await websockets.connect(uri)
            self.connected = True
            self.connectionStatusChanged.emit("connected")
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
                    self.errors += 1
                    continue

        except Exception as e:
            logger.error(f"WebSocket connection error: {e}")
            self.errorOccurred.emit(str(e))
        finally:
            self.connected = False
            self.connectionStatusChanged.emit("disconnected")
            if self.websocket:
                await self.websocket.close()

    def _process_message(self, message: str):
        """Process a received message."""
        try:
            # Store raw message
            self.raw_message_history.append(message)
            self.rawMessageReceived.emit(message)

            # Parse JSON
            data = json.loads(message)
            parsed_data = self._parse_streaming_data(data)

            # Update statistics
            self.message_count += 1
            data_type = parsed_data['metadata']['data_type']

            if data_type not in self.data_type_counts:
                self.data_type_counts[data_type] = 0
                self.data_type_samples[data_type] = 0

            self.data_type_counts[data_type] += 1
            self.data_type_samples[data_type] += parsed_data.get('sample_count', 1)

            # Emit parsed data
            self.dataReceived.emit(parsed_data)

            # Emit statistics update
            stats = self._get_statistics()
            self.statisticsUpdated.emit(stats)

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            self.errors += 1
        except Exception as e:
            logger.error(f"Message processing error: {e}")
            self.errors += 1

    def _parse_streaming_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse streaming data and add sample count."""
        try:
            metadata = data.get('metadata', {})
            data_type = metadata.get('data_type', 'unknown')
            data_payload = data.get('data', {})

            # Count samples based on data type
            sample_count = self._count_samples(data_type, data_payload)

            return {
                'metadata': metadata,
                'data': data_payload,
                'sample_count': sample_count,
                'data_type': data_type
            }

        except Exception as e:
            logger.warning(f"Data parsing error: {e}")
            return {
                'metadata': data.get('metadata', {}),
                'data': data.get('data', {}),
                'sample_count': 1,
                'data_type': 'unknown'
            }

    def _count_samples(self, data_type: str, data_payload: Dict[str, Any]) -> int:
        """Count samples in the data payload."""
        try:
            if data_type == 'levels':
                if 'peak_levels_db' in data_payload:
                    return len(data_payload['peak_levels_db'])
                return 1

            elif data_type == 'fft_spectrum':
                if 'magnitudes_linear' in data_payload:
                    return len(data_payload['magnitudes_linear'])
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

            elif data_type in ['pitch_tracker', 'delay_estimator']:
                return 1

            else:
                return 1

        except Exception as e:
            logger.warning(f"Error counting samples for {data_type}: {e}")
            return 1

    def _get_statistics(self) -> Dict[str, Any]:
        """Get current statistics."""
        elapsed = time.time() - self.start_time
        rate = self.message_count / elapsed if elapsed > 0 else 0

        return {
            'uptime_seconds': elapsed,
            'messages_received': self.message_count,
            'data_rate_msg_per_sec': rate,
            'data_types': list(self.data_type_counts.keys()),
            'data_type_counts': self.data_type_counts.copy(),
            'data_type_samples': self.data_type_samples.copy(),
            'total_samples': sum(self.data_type_samples.values()),
            'errors': self.errors,
            'connected': self.connected
        }


class BaseVisualizationWidget(QFrame):
    """Base class for data visualization widgets."""

    def __init__(self, data_type: str, title: str, parent=None):
        super().__init__(parent)
        self.data_type = data_type
        self.title = title
        self.latest_data = None

        self.setFrameStyle(QFrame.Box)
        self.setLineWidth(2)

        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # Title
        self.title_label = QLabel(f"<b>{title}</b>")
        self.title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.title_label)

        # Status
        self.status_label = QLabel("Waiting for data...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #666;")
        layout.addWidget(self.status_label)

        # Set minimum size
        self.setMinimumSize(300, 200)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def update_data(self, data: Dict[str, Any]):
        """Update with new data."""
        self.latest_data = data
        self.status_label.setText("Receiving data...")
        self.status_label.setStyleSheet("color: #006600;")
        self.update_display()

    def update_display(self):
        """Update the visualization display. Override in subclasses."""
        pass


class LevelsVisualization(BaseVisualizationWidget):
    """Visualization for audio levels data."""

    def __init__(self, parent=None):
        super().__init__("levels", "Audio Levels", parent)
        self.peak_levels = []
        self.rms_levels = []
        self.peak_hold_levels = []

    def update_display(self):
        """Update the levels display."""
        if not self.latest_data or 'data' not in self.latest_data:
            return

        data = self.latest_data['data']

        # Extract level data
        self.peak_levels = data.get('peak_levels_db', [])
        self.rms_levels = data.get('rms_levels_db', [])
        self.peak_hold_levels = data.get('peak_hold_levels_db', [])

        # Trigger repaint
        self.update()

    def paintEvent(self, a0):
        """Paint the levels visualization."""
        super().paintEvent(a0)

        if not self.peak_levels:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Get widget dimensions
        width = self.width() - 20
        height = self.height() - 80  # Leave space for title
        x_offset = 10
        y_offset = 60

        # Draw level bars
        bar_width = width // len(self.peak_levels)
        max_level = 0  # 0 dB is maximum
        min_level = -60  # -60 dB is minimum

        for i, (peak, rms, peak_hold) in enumerate(zip(
            self.peak_levels, self.rms_levels, self.peak_hold_levels
        )):
            # Calculate bar height (0 dB = full height, -60 dB = 0 height)
            peak_height = int((max(min_level, min(max_level, peak)) - min_level) / (max_level - min_level) * height)
            rms_height = int((max(min_level, min(max_level, rms)) - min_level) / (max_level - min_level) * height)

            x = x_offset + i * bar_width

            # Draw RMS level (background)
            painter.setPen(QPen(QColor(100, 100, 255), 2))
            painter.setBrush(QBrush(QColor(100, 100, 255, 128)))
            painter.drawRect(x, y_offset + height - rms_height, bar_width - 2, rms_height)

            # Draw peak level (outline)
            painter.setPen(QPen(QColor(255, 100, 100), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(x, y_offset + height - peak_height, bar_width - 2, peak_height)

            # Draw peak hold (red line)
            if peak_hold > min_level:
                peak_hold_height = int((peak_hold - min_level) / (max_level - min_level) * height)
                painter.setPen(QPen(QColor(255, 0, 0), 3))
                painter.drawLine(x, y_offset + height - peak_hold_height,
                               x + bar_width - 2, y_offset + height - peak_hold_height)

            # Draw channel label
            painter.setPen(QPen(Qt.black))
            painter.drawText(x, y_offset + height + 15, f"Ch{i+1}")


class SpectrumVisualization(BaseVisualizationWidget):
    """Visualization for FFT spectrum data with octave scaling."""

    def __init__(self, parent=None):
        super().__init__("fft_spectrum", "Frequency Spectrum (Octave Scale)", parent)
        self.frequencies = np.array([])
        self.magnitudes = np.array([])

    def update_display(self):
        """Update the spectrum display."""
        if not self.latest_data or 'data' not in self.latest_data:
            return

        data = self.latest_data['data']

        # Extract spectrum data
        # magnitudes_linear contains power spectrum values in linear scale (not dB)
        # These are exponentially smoothed and include frequency weighting
        # NOTE: For 25ms response time, ensure the source spectrum widget has
        # response_time set to 0.025 seconds
        self.frequencies = np.array(data.get('frequencies', []))
        self.magnitudes = np.array(data.get('magnitudes_linear', []))

        # Update status to show octave scaling
        self.status_label.setText("Receiving data (Octave Scale)")

        # Trigger repaint
        self.update()

    def paintEvent(self, a0):
        """Paint the spectrum visualization."""
        super().paintEvent(a0)

        if not self.latest_data or len(self.frequencies) == 0 or len(self.magnitudes) == 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Get widget dimensions
        width = self.width() - 20
        height = self.height() - 80
        x_offset = 10
        y_offset = 60


        # Convert linear magnitude to dB for visualization
        # First, let's see what the raw linear values look like
        print(f"Raw linear values: min={np.min(self.magnitudes):.2e}, max={np.max(self.magnitudes):.2e}")

        # The linear values are power spectrum (already squared), so use 10*log10 for dB conversion
        # Add a reference level to get meaningful dB values
        epsilon = 1e-30
        reference_level = 1e-6  # More reasonable reference for audio power spectrum
        magnitudes_db = 10 * np.log10(np.maximum(self.magnitudes, epsilon) / reference_level)

        # Debug: Check the conversion
        print(f"dB conversion: {np.min(magnitudes_db):.1f} to {np.max(magnitudes_db):.1f} dB")

        # Calculate scaling for dB display
        # Use dynamic range based on actual data for better visualization
        if len(magnitudes_db) > 0:
            # Use 90th percentile as max, 10th percentile as min
            mag_max = float(np.percentile(magnitudes_db, 90))
            mag_min = float(np.percentile(magnitudes_db, 10))
            # Ensure reasonable range
            mag_min = max(mag_min, mag_max - 80)  # At least 80dB range
            mag_max = min(mag_max, 0)  # Don't go above 0 dB
            mag_min = max(mag_min, -120)  # Don't go below -120 dB
        else:
            mag_min = -100
            mag_max = -20

        print(f"Display range: {mag_min:.1f} to {mag_max:.1f} dB")

        # Ensure min/max frequencies are valid
        valid_freqs = self.frequencies[self.frequencies > 0]
        if len(valid_freqs) == 0:
            return  # Can't draw if no valid frequencies

        # Use octave scaling (log2) instead of log10 for better musical frequency representation
        freq_min = np.log2(max(20, np.min(valid_freqs)))
        freq_max = np.log2(max(20000, np.max(valid_freqs)))

        # Extend the range to show lower octaves (down to 20Hz and below if needed)
        freq_min = min(freq_min, np.log2(20))  # Ensure we show down to 20Hz
        freq_max = max(freq_max, np.log2(20000))  # Ensure we show up to 20kHz

        if freq_min >= freq_max:
            return # Avoid division by zero

        # Draw spectrum
        painter.setPen(QPen(QColor(0, 100, 200), 2))

        path = QPainterPath()
        path.moveTo(x_offset, y_offset + height)

        for i, (freq, mag) in enumerate(zip(self.frequencies, magnitudes_db)):
            if freq <= 0:
                continue

            # Octave frequency scaling (log2)
            x = x_offset + ((np.log2(freq) - freq_min) / (freq_max - freq_min)) * width

            # Magnitude scaling (invert Y axis)
            y = y_offset + (1 - (max(mag_min, min(mag_max, mag)) - mag_min) / (mag_max - mag_min)) * height

            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)

        painter.drawPath(path)

        # Draw octave boundary lines
        painter.setPen(QPen(QColor(200, 200, 200), 1, Qt.DotLine))
        octave_freqs = [31.25, 62.5, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
        for octave_freq in octave_freqs:
            if octave_freq >= 20 and octave_freq <= 20000:
                x_pos = x_offset + ((np.log2(octave_freq) - freq_min) / (freq_max - freq_min)) * width
                painter.drawLine(int(x_pos), y_offset, int(x_pos), y_offset + height)

        # Draw axes labels with octave notation
        painter.setPen(QPen(Qt.black))
        painter.setFont(QFont("Arial", 8))

        # Draw frequency labels at octave boundaries
        for octave_freq in octave_freqs:
            if octave_freq >= 20 and octave_freq <= 20000:
                x_pos = x_offset + ((np.log2(octave_freq) - freq_min) / (freq_max - freq_min)) * width
                if octave_freq >= 1000:
                    label = f"{octave_freq/1000:.1f}k"
                else:
                    label = f"{octave_freq:.0f}"
                painter.drawText(int(x_pos) - 15, y_offset + height + 15, label)

        painter.drawText(5, y_offset + 10, f"{mag_max:.0f}dB")
        painter.drawText(5, y_offset + height, f"{mag_min:.0f}dB")


class PitchVisualization(BaseVisualizationWidget):
    """Visualization for pitch tracking data."""

    def __init__(self, parent=None):
        super().__init__("pitch_tracker", "Pitch Tracker", parent)
        self.frequency = None
        self.confidence = 0.0
        self.note_name = None

    def update_display(self):
        """Update the pitch display."""
        if not self.latest_data or 'data' not in self.latest_data:
            return

        data = self.latest_data['data']

        # Extract pitch data
        self.frequency = data.get('frequency_hz')
        self.confidence = data.get('confidence', 0.0)
        self.note_name = data.get('note_name')

        # Trigger repaint
        self.update()

    def paintEvent(self, a0):
        """Paint the pitch visualization."""
        super().paintEvent(a0)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Get widget dimensions
        width = self.width() - 20
        height = self.height() - 80
        x_offset = 10
        y_offset = 60

        # Draw note name
        painter.setPen(QPen(Qt.black))
        font = QFont("Arial", 24, QFont.Bold)
        painter.setFont(font)

        if self.note_name:
            note_text = f"{self.note_name}"
            if self.frequency:
                note_text += f" ({self.frequency:.0f} Hz)"
            painter.drawText(x_offset, y_offset + 40, note_text)
        elif self.frequency:
            freq_text = f"{self.frequency:.0f} Hz"
            painter.drawText(x_offset, y_offset + 40, freq_text)
        else:
            painter.drawText(x_offset, y_offset + 40, "No pitch detected")

        # Draw confidence meter
        if self.confidence > 0:
            # Confidence bar
            bar_width = width - 20
            bar_height = 20
            confidence_width = int(self.confidence * bar_width)

            # Background
            painter.setPen(QPen(QColor(200, 200, 200), 1))
            painter.setBrush(QBrush(QColor(240, 240, 240)))
            painter.drawRect(x_offset, y_offset + 60, bar_width, bar_height)

            # Fill
            color = QColor(100, 200, 100) if self.confidence > 0.5 else QColor(200, 200, 100)
            painter.setBrush(QBrush(color))
            painter.drawRect(x_offset, y_offset + 60, confidence_width, bar_height)

            # Label
            painter.setPen(QPen(Qt.black))
            small_font = QFont("Arial", 10)
            painter.setFont(small_font)
            painter.drawText(x_offset, y_offset + 55, f"Confidence: {self.confidence:.2f}")


class OctaveSpectrumVisualization(BaseVisualizationWidget):
    """Visualization for octave spectrum data."""

    def __init__(self, parent=None):
        super().__init__("octave_spectrum", "Octave Spectrum", parent)
        self.center_frequencies = np.array([])
        self.band_energies = np.array([])
        self.band_labels = []

    def update_display(self):
        """Update the octave spectrum display."""
        if not self.latest_data or 'data' not in self.latest_data:
            return

        data = self.latest_data['data']

        # Extract octave spectrum data
        self.center_frequencies = np.array(data.get('center_frequencies', []))
        self.band_energies = np.array(data.get('band_energies_db', []))
        self.band_labels = data.get('band_labels', [])

        # Trigger repaint
        self.update()

    def paintEvent(self, a0):
        """Paint the octave spectrum visualization."""
        super().paintEvent(a0)

        if len(self.center_frequencies) == 0 or len(self.band_energies) == 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Get widget dimensions
        width = self.width() - 20
        height = self.height() - 80
        x_offset = 10
        y_offset = 60

        # Draw bars
        bar_width = width // len(self.band_energies)
        max_energy = 0  # 0 dB is maximum
        min_energy = -60  # -60 dB is minimum

        for i, (freq, energy) in enumerate(zip(self.center_frequencies, self.band_energies)):
            # Calculate bar height (0 dB = full height, -60 dB = 0 height)
            bar_height = int((max(min_energy, min(max_energy, energy)) - min_energy) / (max_energy - min_energy) * height)

            x = x_offset + i * bar_width

            # Draw bar
            painter.setPen(QPen(QColor(150, 100, 200), 2))
            painter.setBrush(QBrush(QColor(150, 100, 200, 128)))
            painter.drawRect(x, y_offset + height - bar_height, bar_width - 2, bar_height)

            # Draw frequency label
            painter.setPen(QPen(Qt.black))
            painter.setFont(QFont("Arial", 8))
            if i < len(self.band_labels):
                painter.drawText(x, y_offset + height + 12, self.band_labels[i])
            else:
                painter.drawText(x, y_offset + height + 12, f"{freq:.0f}Hz")


class ScopeVisualization(BaseVisualizationWidget):
    """Visualization for scope (time-domain) data."""

    def __init__(self, parent=None):
        super().__init__("scope", "Audio Scope", parent)
        self.timestamps = np.array([])
        self.samples = np.array([])

    def update_display(self):
        """Update the scope display."""
        if not self.latest_data or 'data' not in self.latest_data:
            return

        data = self.latest_data['data']

        # Extract scope data
        self.timestamps = np.array(data.get('timestamps', []))
        samples_data = data.get('samples', [])
        if samples_data:
            self.samples = np.array(samples_data)

        # Trigger repaint
        self.update()

    def paintEvent(self, a0):
        """Paint the scope visualization."""
        super().paintEvent(a0)

        if len(self.timestamps) == 0 or len(self.samples) == 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Get widget dimensions
        width = self.width() - 20
        height = self.height() - 80
        x_offset = 10
        y_offset = 60

        # Draw waveform
        painter.setPen(QPen(QColor(0, 150, 200), 2))

        path = QPainterPath()
        path.moveTo(x_offset, y_offset + height // 2)

        # Use first channel if multi-channel
        if len(self.samples.shape) > 1:
            waveform = self.samples[0]
        else:
            waveform = self.samples

        # Normalize and scale
        if len(waveform) > 0:
            max_val = np.max(np.abs(waveform))
            if max_val > 0:
                waveform = waveform / max_val

            # Draw waveform
            step = max(1, len(waveform) // width)
            for i in range(0, len(waveform), step):
                if i < len(waveform):
                    x = x_offset + (i * width) // len(waveform)
                    y = y_offset + int((1 - waveform[i]) * height // 2)
                    if i == 0:
                        path.moveTo(x, y)
                    else:
                        path.lineTo(x, y)

            painter.drawPath(path)

            # Draw center line
            painter.setPen(QPen(QColor(200, 200, 200), 1, Qt.DashLine))
            painter.drawLine(x_offset, y_offset + height // 2, x_offset + width, y_offset + height // 2)


class DelayEstimatorVisualization(BaseVisualizationWidget):
    """Visualization for delay estimation data."""

    def __init__(self, parent=None):
        super().__init__("delay_estimator", "Delay Estimator", parent)
        self.delay_ms = 0.0
        self.confidence = 0.0
        self.distance_m = 0.0

    def update_display(self):
        """Update the delay estimator display."""
        if not self.latest_data or 'data' not in self.latest_data:
            return

        data = self.latest_data['data']

        # Extract delay data
        self.delay_ms = data.get('delay_ms', 0.0)
        self.confidence = data.get('confidence', 0.0)
        self.distance_m = data.get('distance_m', 0.0)

        # Trigger repaint
        self.update()

    def paintEvent(self, a0):
        """Paint the delay estimator visualization."""
        super().paintEvent(a0)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Get widget dimensions
        width = self.width() - 20
        height = self.height() - 80
        x_offset = 10
        y_offset = 60

        # Draw delay information
        painter.setPen(QPen(Qt.black))
        font = QFont("Arial", 16, QFont.Bold)
        painter.setFont(font)

        delay_text = f"Delay: {self.delay_ms:.2f} ms"
        painter.drawText(x_offset, y_offset + 30, delay_text)

        if self.distance_m > 0:
            distance_text = f"Distance: {self.distance_m:.2f} m"
            painter.drawText(x_offset, y_offset + 60, distance_text)

        # Draw confidence meter
        if self.confidence > 0:
            # Confidence bar
            bar_width = width - 20
            bar_height = 20
            confidence_width = int(self.confidence * bar_width)

            # Background
            painter.setPen(QPen(QColor(200, 200, 200), 1))
            painter.setBrush(QBrush(QColor(240, 240, 240)))
            painter.drawRect(x_offset, y_offset + 80, bar_width, bar_height)

            # Fill
            color = QColor(100, 200, 100) if self.confidence > 0.7 else QColor(200, 200, 100)
            painter.setBrush(QBrush(color))
            painter.drawRect(x_offset, y_offset + 80, confidence_width, bar_height)

            # Label
            painter.setPen(QPen(Qt.black))
            small_font = QFont("Arial", 10)
            painter.setFont(small_font)
            painter.drawText(x_offset, y_offset + 75, f"Confidence: {self.confidence:.2f}")


class SpectrogramVisualization(BaseVisualizationWidget):
    """Visualization for spectrogram data (placeholder - currently not working)."""

    def __init__(self, parent=None):
        super().__init__("spectrogram", "Spectrogram (Not Available)", parent)

    def update_display(self):
        """Update the spectrogram display."""
        if not self.latest_data or 'data' not in self.latest_data:
            return

        # Mark as having received data but can't display it
        self.status_label.setText("Data received but visualization not available")
        self.status_label.setStyleSheet("color: #ff6600;")

    def paintEvent(self, a0):
        """Paint the spectrogram placeholder."""
        super().paintEvent(a0)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Get widget dimensions
        width = self.width() - 20
        height = self.height() - 80
        x_offset = 10
        y_offset = 60

        # Draw placeholder message
        painter.setPen(QPen(QColor(255, 102, 0), 2))
        painter.setFont(QFont("Arial", 12, QFont.Bold))
        painter.drawText(x_offset, y_offset + 40, "Spectrogram visualization not available")
        painter.drawText(x_offset, y_offset + 60, "due to streaming API issue")


class RawMessageDisplay(QGroupBox):
    """Widget for displaying the last raw JSON message with copy functionality."""

    def __init__(self, parent=None):
        super().__init__("Last Raw Message", parent)

        # Store the last message
        self.last_message = ""
        self.last_timestamp = ""

        # Layout
        layout = QVBoxLayout(self)

        # Info label
        info_label = QLabel("Only the most recent message is shown below:")
        info_label.setStyleSheet("color: #666; font-size: 10px;")
        layout.addWidget(info_label)

        # Text area for the last message only
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont("Courier New", 9))
        self.text_edit.setMaximumHeight(250)

        # Set dark theme for JSON
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background-color: #2b2b2b;
                color: #f8f8f2;
                border: 1px solid #555;
                font-family: 'Courier New';
            }
        """)

        layout.addWidget(self.text_edit)

        # Button layout
        button_layout = QHBoxLayout()

        # Copy button
        self.copy_button = QPushButton("📋 Copy Message")
        self.copy_button.clicked.connect(self.copy_message)
        self.copy_button.setToolTip("Copy the current message to clipboard")
        button_layout.addWidget(self.copy_button)

        # Clear button
        clear_button = QPushButton("🗑️ Clear")
        clear_button.clicked.connect(self.clear_messages)
        clear_button.setToolTip("Clear the current message")
        button_layout.addWidget(clear_button)

        layout.addLayout(button_layout)

        # Status label
        self.status_label = QLabel("No messages received yet")
        self.status_label.setStyleSheet("color: #666; font-size: 10px;")
        layout.addWidget(self.status_label)

    def add_message(self, message: str):
        """Update with the latest raw message (replaces previous)."""
        try:
            # Store the raw message
            self.last_message = message
            self.last_timestamp = time.strftime("%H:%M:%S.%f")[:-3]  # Include milliseconds

            # Format JSON for better readability
            try:
                parsed = json.loads(message)
                formatted = json.dumps(parsed, indent=2)
            except json.JSONDecodeError:
                formatted = message

            # Create display text
            display_text = f"[{self.last_timestamp}]\n{formatted}"

            # Set the text (replace entirely)
            self.text_edit.setPlainText(display_text)

            # Update status
            self.status_label.setText(f"Last message received at {self.last_timestamp}")
            self.status_label.setStyleSheet("color: #006600; font-size: 10px;")

            # Enable copy button
            self.copy_button.setEnabled(True)

        except Exception as e:
            logger.error(f"Error displaying message: {e}")
            error_text = f"[{time.strftime('%H:%M:%S')}]\nError displaying message: {str(e)}\n\nRaw: {message[:200]}..."
            self.text_edit.setPlainText(error_text)

    def copy_message(self):
        """Copy the current message to clipboard."""
        try:
            from PyQt5.QtWidgets import QApplication
            clipboard = QApplication.clipboard()

            # Copy the raw JSON message
            clipboard.setText(self.last_message)

            # Update status temporarily
            original_text = self.status_label.text()
            self.status_label.setText("✅ Message copied to clipboard!")
            self.status_label.setStyleSheet("color: #009900; font-size: 10px; font-weight: bold;")

            # Reset status after 2 seconds
            QTimer.singleShot(2000, lambda: self._reset_status(original_text))

        except Exception as e:
            logger.error(f"Error copying message: {e}")
            self.status_label.setText("❌ Failed to copy message")
            self.status_label.setStyleSheet("color: #990000; font-size: 10px;")

    def _reset_status(self, original_text):
        """Reset status label to original text."""
        self.status_label.setText(original_text)
        self.status_label.setStyleSheet("color: #666; font-size: 10px;")

    def clear_messages(self):
        """Clear the current message."""
        self.last_message = ""
        self.last_timestamp = ""
        self.text_edit.clear()
        self.status_label.setText("Message cleared")
        self.status_label.setStyleSheet("color: #666; font-size: 10px;")
        self.copy_button.setEnabled(False)


class StatisticsPanel(QGroupBox):
    """Widget for displaying streaming statistics."""

    def __init__(self, parent=None):
        super().__init__("Statistics", parent)

        # Layout
        layout = QVBoxLayout(self)

        # Connection status
        self.connection_label = QLabel("Status: Disconnected")
        self.connection_label.setStyleSheet("font-weight: bold; color: red;")
        layout.addWidget(self.connection_label)

        # Statistics labels
        self.stats_labels = {}

        stats_items = [
            ("uptime", "Uptime"),
            ("messages", "Messages Received"),
            ("rate", "Message Rate"),
            ("samples", "Total Samples"),
            ("errors", "Errors"),
            ("types", "Active Types")
        ]

        for key, label in stats_items:
            self.stats_labels[key] = QLabel(f"{label}: 0")
            layout.addWidget(self.stats_labels[key])

        # Set size policy
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.setMaximumHeight(200)

    def update_statistics(self, stats: Dict[str, Any]):
        """Update statistics display."""
        # Connection status
        if stats.get('connected', False):
            self.connection_label.setText("Status: Connected")
            self.connection_label.setStyleSheet("font-weight: bold; color: green;")
        else:
            self.connection_label.setText("Status: Disconnected")
            self.connection_label.setStyleSheet("font-weight: bold; color: red;")

        # Update statistics
        uptime = stats.get('uptime_seconds', 0)
        self.stats_labels['uptime'].setText(f"Uptime: {uptime:.1f}s")

        messages = stats.get('messages_received', 0)
        self.stats_labels['messages'].setText(f"Messages: {messages:,}")

        rate = stats.get('data_rate_msg_per_sec', 0)
        self.stats_labels['rate'].setText(f"Rate: {rate:.1f} msg/s")

        samples = stats.get('total_samples', 0)
        self.stats_labels['samples'].setText(f"Samples: {samples:,}")

        errors = stats.get('errors', 0)
        self.stats_labels['errors'].setText(f"Errors: {errors}")

        data_types = stats.get('data_types', [])
        types_text = ", ".join(data_types) if data_types else "None"
        self.stats_labels['types'].setText(f"Types: {types_text}")


class DataVisualizationArea(QWidget):
    """Main area for data visualizations."""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Layout
        layout = QVBoxLayout(self)

        # Scroll area for visualizations
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # Container for visualization widgets
        self.visualization_container = QWidget()
        self.visualization_layout = QVBoxLayout(self.visualization_container)

        self.scroll_area.setWidget(self.visualization_container)
        layout.addWidget(self.scroll_area)

        # Active visualization widgets
        self.active_widgets = {}

        # Create initial widgets for all data types
        self._create_visualization_widgets()

    def _create_visualization_widgets(self):
        """Create visualization widgets for all data types."""
        widget_classes = {
            'levels': LevelsVisualization,
            'fft_spectrum': SpectrumVisualization,
            'octave_spectrum': OctaveSpectrumVisualization,
            'pitch_tracker': PitchVisualization,
            'scope': ScopeVisualization,
            'delay_estimator': DelayEstimatorVisualization,
            'spectrogram': SpectrogramVisualization,  # Placeholder for now
        }

        for data_type, widget_class in widget_classes.items():
            widget = widget_class(self)
            self.visualization_layout.addWidget(widget)
            self.active_widgets[data_type] = widget

    def update_data(self, data: Dict[str, Any]):
        """Update visualization with new data."""
        data_type = data.get('data_type', 'unknown')

        if data_type in self.active_widgets:
            self.active_widgets[data_type].update_data(data)


class StreamVisualizerWindow(QMainWindow):
    """Main application window."""

    def __init__(self, websocket_client):
        super().__init__()

        self.websocket_client = websocket_client

        # Setup UI
        self.setWindowTitle("Friture Streaming Visualizer - All Data Types")
        self.setGeometry(100, 100, 1400, 900)

        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout
        main_layout = QHBoxLayout(central_widget)

        # Create splitter for resizable panels
        splitter = QSplitter(Qt.Horizontal)

        # Left panel: Data visualizations
        self.visualization_area = DataVisualizationArea()
        splitter.addWidget(self.visualization_area)

        # Right panel: Raw messages and statistics
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        # Raw message display
        self.raw_message_display = RawMessageDisplay()
        right_layout.addWidget(self.raw_message_display)

        # Statistics panel
        self.statistics_panel = StatisticsPanel()
        right_layout.addWidget(self.statistics_panel)

        # Add stretch to push widgets to top
        right_layout.addStretch()

        splitter.addWidget(right_panel)

        # Set splitter proportions (70% left, 30% right)
        splitter.setSizes([700, 300])

        main_layout.addWidget(splitter)

        # Setup menu bar
        self._setup_menu_bar()

        # Setup status bar
        self.status_bar = self.statusBar()
        self.status_label = QLabel("Disconnected")
        self.status_bar.addWidget(self.status_label)

        # Connect signals
        self._connect_signals()

    def _setup_menu_bar(self):
        """Setup the menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu('File')

        # Connect action
        connect_action = QAction('Connect', self)
        connect_action.triggered.connect(self.websocket_client.start)
        file_menu.addAction(connect_action)

        # Disconnect action
        disconnect_action = QAction('Disconnect', self)
        disconnect_action.triggered.connect(self.websocket_client.stop)
        file_menu.addAction(disconnect_action)

        file_menu.addSeparator()

        # Exit action
        exit_action = QAction('Exit', self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # View menu
        view_menu = menubar.addMenu('View')

        # Clear messages action
        clear_action = QAction('Clear Last Message', self)
        clear_action.triggered.connect(self.raw_message_display.clear_messages)
        clear_action.setShortcut('Ctrl+L')
        view_menu.addAction(clear_action)

        # Separator
        view_menu.addSeparator()

        # Auto-scroll toggle (placeholder for future enhancement)
        autoscroll_action = QAction('Auto-scroll Visualizations', self)
        autoscroll_action.setCheckable(True)
        autoscroll_action.setChecked(True)
        view_menu.addAction(autoscroll_action)

    def _connect_signals(self):
        """Connect WebSocket client signals to UI slots."""
        self.websocket_client.dataReceived.connect(self.visualization_area.update_data)
        self.websocket_client.rawMessageReceived.connect(self.raw_message_display.add_message)
        self.websocket_client.connectionStatusChanged.connect(self._on_connection_status_changed)
        self.websocket_client.statisticsUpdated.connect(self.statistics_panel.update_statistics)
        self.websocket_client.errorOccurred.connect(self._on_error_occurred)

    def _on_connection_status_changed(self, status: str):
        """Handle connection status changes."""
        if status == "connected":
            self.status_label.setText("Connected")
            self.status_label.setStyleSheet("color: green;")
        elif status == "connecting":
            self.status_label.setText("Connecting...")
            self.status_label.setStyleSheet("color: orange;")
        else:
            self.status_label.setText("Disconnected")
            self.status_label.setStyleSheet("color: red;")

    def _on_error_occurred(self, error: str):
        """Handle errors."""
        self.statusBar().showMessage(f"Error: {error}", 5000)


class StreamVisualizerApp:
    """Main application class."""

    def __init__(self, host: str = 'localhost', port: int = 8765):
        self.qt_app = QApplication(sys.argv)
        self.qt_app.setApplicationName("Friture Streaming Visualizer - All Data Types")
        self.qt_app.setApplicationVersion("1.1")

        # Create WebSocket client
        self.websocket_client = StreamingWebSocketClient(host, port)

        # Create main window
        self.main_window = StreamVisualizerWindow(self.websocket_client)

    def run(self):
        """Run the application."""
        # Show main window
        self.main_window.show()

        # Start WebSocket client
        self.websocket_client.start()

        # Run Qt event loop
        return self.qt_app.exec_()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Friture Streaming Information Visualizer - Real-time visualization of all Friture data types")
    parser.add_argument('--host', default='localhost', help='WebSocket server host')
    parser.add_argument('--port', type=int, default=8765, help='WebSocket server port')

    args = parser.parse_args()

    try:
        app = StreamVisualizerApp(args.host, args.port)
        sys.exit(app.run())
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
    except Exception as e:
        logger.error(f"Application error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()