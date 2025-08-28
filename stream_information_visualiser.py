#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Friture Streaming Information Visualizer

A real-time GUI application for visualizing Friture's streaming API data.
Displays beautiful visualizations for all data types alongside raw message data.

Usage:
    python stream_information_visualiser.py --host localhost --port 8765
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
    """Visualization for FFT spectrum data."""

    def __init__(self, parent=None):
        super().__init__("fft_spectrum", "Frequency Spectrum", parent)
        self.frequencies = np.array([])
        self.magnitudes = np.array([])

    def update_display(self):
        """Update the spectrum display."""
        if not self.latest_data or 'data' not in self.latest_data:
            return

        data = self.latest_data['data']

        # Extract spectrum data
        self.frequencies = np.array(data.get('frequencies', []))
        self.magnitudes = np.array(data.get('magnitudes_db', []))

        # Trigger repaint
        self.update()

    def paintEvent(self, a0):
        """Paint the spectrum visualization."""
        super().paintEvent(a0)

        if len(self.frequencies) == 0 or len(self.magnitudes) == 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Get widget dimensions
        width = self.width() - 20
        height = self.height() - 80
        x_offset = 10
        y_offset = 60

        # Calculate scaling
        freq_min = np.log10(max(20, np.min(self.frequencies)))  # Min 20 Hz
        freq_max = np.log10(max(20000, np.max(self.frequencies)))  # Max 20 kHz
        mag_min = -80  # -80 dB
        mag_max = 0    # 0 dB

        # Draw spectrum
        painter.setPen(QPen(QColor(0, 100, 200), 2))

        path = QPainterPath()
        path.moveTo(x_offset, y_offset + height)

        for i, (freq, mag) in enumerate(zip(self.frequencies, self.magnitudes)):
            if freq <= 0:
                continue

            # Logarithmic frequency scaling
            x = x_offset + (np.log10(freq) - freq_min) / (freq_max - freq_min) * width

            # Magnitude scaling (invert Y axis)
            y = y_offset + (1 - (max(mag_min, min(mag_max, mag)) - mag_min) / (mag_max - mag_min)) * height

            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)

        painter.drawPath(path)

        # Draw axes labels
        painter.setPen(QPen(Qt.black))
        painter.drawText(x_offset, y_offset + height + 15, "20Hz")
        painter.drawText(x_offset + width - 30, y_offset + height + 15, "20kHz")
        painter.drawText(5, y_offset + 10, "0dB")
        painter.drawText(5, y_offset + height, "-80dB")


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


class RawMessageDisplay(QGroupBox):
    """Widget for displaying raw JSON messages."""

    def __init__(self, parent=None):
        super().__init__("Raw Messages", parent)

        # Layout
        layout = QVBoxLayout(self)

        # Text area for raw messages
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont("Courier New", 9))
        self.text_edit.setMaximumHeight(300)

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

        # Clear button
        clear_button = QPushButton("Clear")
        clear_button.clicked.connect(self.clear_messages)
        layout.addWidget(clear_button)

    def add_message(self, message: str):
        """Add a new raw message."""
        # Format JSON for better readability
        try:
            parsed = json.loads(message)
            formatted = json.dumps(parsed, indent=2)
        except:
            formatted = message

        # Add timestamp
        timestamp = time.strftime("%H:%M:%S")
        display_text = f"[{timestamp}]\n{formatted}\n\n"

        # Append to text area
        self.text_edit.append(display_text)

        # Auto-scroll to bottom
        scrollbar = self.text_edit.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def clear_messages(self):
        """Clear all messages."""
        self.text_edit.clear()


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
            'pitch_tracker': PitchVisualization,
            # Add more as needed
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
        self.setWindowTitle("Friture Streaming Visualizer")
        self.setGeometry(100, 100, 1200, 800)

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
        clear_action = QAction('Clear Raw Messages', self)
        clear_action.triggered.connect(self.raw_message_display.clear_messages)
        view_menu.addAction(clear_action)

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
        self.qt_app.setApplicationName("Friture Streaming Visualizer")
        self.qt_app.setApplicationVersion("1.0")

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
    parser = argparse.ArgumentParser(description="Friture Streaming Information Visualizer")
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