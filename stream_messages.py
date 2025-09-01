#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Friture Stream Messages Display

A simplified GUI application for displaying the last message received from different
specific data_types with copy functionality. Only displays the most recent message
for each data type without storing message history.

Usage:
    python stream_messages.py --host localhost --port 8765

Features:
- Real-time display of last message for each data type
- Copy-to-clipboard functionality for each message type
- Memory-efficient (only stores current messages)
- Connection status monitoring
- Improved grid layout with no scrolling required
"""

import sys
import json
import logging
import asyncio
import threading
import time
from typing import Dict, Any, Optional
import argparse

from PyQt5.QtCore import (
    Qt, QTimer, QObject, pyqtSignal, QThread
)
from PyQt5.QtGui import (
    QFont
)
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTextEdit, QLabel, QFrame, QGroupBox, QGridLayout,
    QPushButton, QMenuBar, QStatusBar, QAction, QScrollArea,
    QSizePolicy
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
    rawMessageReceived = pyqtSignal(str, str)  # Raw JSON message and data_type
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
        self.errors = 0

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
            # Parse JSON
            data = json.loads(message)
            parsed_data = self._parse_streaming_data(data)

            # Update statistics
            self.message_count += 1
            data_type = parsed_data['data_type']

            if data_type not in self.data_type_counts:
                self.data_type_counts[data_type] = 0

            self.data_type_counts[data_type] += 1

            # Emit parsed data
            self.dataReceived.emit(parsed_data)

            # Emit raw message with data type
            self.rawMessageReceived.emit(message, data_type)

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
            'errors': self.errors,
            'connected': self.connected
        }


class MessageDisplayWidget(QGroupBox):
    """Widget for displaying the last message for a specific data type."""

    def __init__(self, data_type: str, title: str, parent=None):
        super().__init__(f"{title}", parent)

        self.data_type = data_type
        self.display_title = title
        self.last_message = ""
        self.last_timestamp = ""

        # Layout
        layout = QVBoxLayout(self)
        layout.setSpacing(5)  # Reduce spacing

        # Header with timestamp and controls
        header_layout = QHBoxLayout()
        
        # Timestamp label
        self.timestamp_label = QLabel("No data")
        self.timestamp_label.setStyleSheet("color: #666; font-size: 10px; font-weight: bold;")
        header_layout.addWidget(self.timestamp_label)
        
        header_layout.addStretch()  # Push buttons to right
        
        # Copy button (smaller)
        self.copy_button = QPushButton("📋")
        self.copy_button.clicked.connect(self.copy_message)
        self.copy_button.setToolTip(f"Copy {data_type} message")
        self.copy_button.setEnabled(False)
        self.copy_button.setMaximumWidth(30)
        header_layout.addWidget(self.copy_button)

        # Clear button (smaller)
        clear_button = QPushButton("🗑️")
        clear_button.clicked.connect(self.clear_message)
        clear_button.setToolTip(f"Clear {data_type} message")
        clear_button.setMaximumWidth(30)
        header_layout.addWidget(clear_button)

        layout.addLayout(header_layout)

        # Text area for the message (fixed size)
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont("Consolas", 8))  # Smaller font
        
        # Fixed height to prevent expansion
        self.text_edit.setFixedHeight(200)
        self.text_edit.setMinimumWidth(200)

        # Set dark theme for JSON
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background-color: #2b2b2b;
                color: #f8f8f2;
                border: 1px solid #555;
                font-family: 'Consolas', 'Courier New', monospace;
            }
        """)

        layout.addWidget(self.text_edit)

        # Message count label
        self.count_label = QLabel("Count: 0")
        self.count_label.setStyleSheet("color: #888; font-size: 9px;")
        layout.addWidget(self.count_label)

        # Set fixed size policy
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setFixedSize(280, 280)  # Fixed widget size
        
        # Message counter
        self.message_count = 0

    def update_message(self, message: str):
        """Update with a new message."""
        try:
            # Store the raw message
            self.last_message = message
            self.last_timestamp = time.strftime("%H:%M:%S")
            self.message_count += 1

            # Format JSON for better readability (truncated if too long)
            try:
                parsed = json.loads(message)
                formatted = json.dumps(parsed, indent=2)
                
                # Truncate if too long to fit in display
                if len(formatted) > 2000:
                    lines = formatted.split('\n')
                    if len(lines) > 20:
                        truncated_lines = lines[:15] + ['    ...', '    [message truncated]', '}']
                        formatted = '\n'.join(truncated_lines)
                    else:
                        formatted = formatted[:1800] + '\n... [truncated]'
                        
            except json.JSONDecodeError:
                formatted = message[:1800] + ('...' if len(message) > 1800 else '')

            # Set the text
            self.text_edit.setPlainText(formatted)

            # Update timestamp
            self.timestamp_label.setText(f"Last: {self.last_timestamp}")
            self.timestamp_label.setStyleSheet("color: #006600; font-size: 10px; font-weight: bold;")
            
            # Update count
            self.count_label.setText(f"Count: {self.message_count}")

            # Enable copy button
            self.copy_button.setEnabled(True)

        except Exception as e:
            logger.error(f"Error displaying {self.data_type} message: {e}")
            error_text = f"Error: {str(e)}\n\nRaw: {message[:200]}..."
            self.text_edit.setPlainText(error_text)

    def copy_message(self):
        """Copy the current message to clipboard."""
        try:
            from PyQt5.QtWidgets import QApplication
            clipboard = QApplication.clipboard()

            # Copy the raw JSON message
            clipboard.setText(self.last_message)

            # Update timestamp temporarily
            original_text = self.timestamp_label.text()
            self.timestamp_label.setText("✅ Copied!")
            self.timestamp_label.setStyleSheet("color: #009900; font-size: 10px; font-weight: bold;")

            # Reset status after 1.5 seconds
            QTimer.singleShot(1500, lambda: self._reset_timestamp(original_text))

        except Exception as e:
            logger.error(f"Error copying {self.data_type} message: {e}")
            self.timestamp_label.setText("❌ Copy failed")
            self.timestamp_label.setStyleSheet("color: #990000; font-size: 10px; font-weight: bold;")

    def _reset_timestamp(self, original_text):
        """Reset timestamp label to original text."""
        self.timestamp_label.setText(original_text)
        self.timestamp_label.setStyleSheet("color: #006600; font-size: 10px; font-weight: bold;")

    def clear_message(self):
        """Clear the current message."""
        self.last_message = ""
        self.last_timestamp = ""
        self.message_count = 0
        self.text_edit.clear()
        self.timestamp_label.setText("Cleared")
        self.timestamp_label.setStyleSheet("color: #666; font-size: 10px; font-weight: bold;")
        self.count_label.setText("Count: 0")
        self.copy_button.setEnabled(False)


class StatisticsPanel(QGroupBox):
    """Widget for displaying basic streaming statistics."""

    def __init__(self, parent=None):
        super().__init__("Connection & Statistics", parent)

        # Layout
        layout = QVBoxLayout(self)

        # Connection status (larger and more prominent)
        self.connection_label = QLabel("Status: Disconnected")
        self.connection_label.setStyleSheet("font-weight: bold; color: red; font-size: 14px; padding: 5px;")
        self.connection_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.connection_label)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator)

        # Statistics in a grid
        stats_widget = QWidget()
        stats_layout = QGridLayout(stats_widget)
        
        self.stats_labels = {}
        stats_items = [
            ("uptime", "Uptime", 0, 0),
            ("messages", "Messages", 0, 1),
            ("rate", "Rate (msg/s)", 1, 0),
            ("errors", "Errors", 1, 1),
        ]

        for key, label, row, col in stats_items:
            label_widget = QLabel(f"{label}:")
            label_widget.setStyleSheet("font-weight: bold; color: #333;")
            stats_layout.addWidget(label_widget, row, col * 2)
            
            value_widget = QLabel("0")
            value_widget.setStyleSheet("color: #666;")
            stats_layout.addWidget(value_widget, row, col * 2 + 1)
            self.stats_labels[key] = value_widget

        layout.addWidget(stats_widget)

        # Active data types
        self.types_label = QLabel("Active Types: None")
        self.types_label.setStyleSheet("font-size: 10px; color: #666; padding: 5px;")
        self.types_label.setWordWrap(True)
        layout.addWidget(self.types_label)

        # Set size policy
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setFixedHeight(180)

    def update_statistics(self, stats: Dict[str, Any]):
        """Update statistics display."""
        # Connection status
        if stats.get('connected', False):
            self.connection_label.setText("🟢 Connected")
            self.connection_label.setStyleSheet("font-weight: bold; color: green; font-size: 14px; padding: 5px;")
        else:
            self.connection_label.setText("🔴 Disconnected")
            self.connection_label.setStyleSheet("font-weight: bold; color: red; font-size: 14px; padding: 5px;")

        # Update statistics
        uptime = stats.get('uptime_seconds', 0)
        self.stats_labels['uptime'].setText(f"{uptime:.1f}s")

        messages = stats.get('messages_received', 0)
        self.stats_labels['messages'].setText(f"{messages:,}")

        rate = stats.get('data_rate_msg_per_sec', 0)
        self.stats_labels['rate'].setText(f"{rate:.1f}")

        errors = stats.get('errors', 0)
        self.stats_labels['errors'].setText(f"{errors}")

        data_types = stats.get('data_types', [])
        if data_types:
            types_text = ", ".join(data_types)
            if len(types_text) > 50:
                types_text = types_text[:47] + "..."
            self.types_label.setText(f"Active Types: {types_text}")
        else:
            self.types_label.setText("Active Types: None")


class MessageDisplayArea(QWidget):
    """Main area for message displays using a grid layout."""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)

        # Title
        title_label = QLabel("Live Data Streams")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #333; padding: 5px;")
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)

        # Container for grid layout
        grid_container = QWidget()
        self.grid_layout = QGridLayout(grid_container)
        self.grid_layout.setSpacing(10)
        
        # Set consistent spacing and sizing
        self.grid_layout.setContentsMargins(10, 10, 10, 10)
        
        main_layout.addWidget(grid_container)

        # Active message display widgets
        self.active_widgets = {}

        # Create initial widgets for all data types
        self._create_message_widgets()

    def _create_message_widgets(self):
        """Create message display widgets for all data types in a grid."""
        data_types_info = [
            ('pitch_tracker', 'Pitch Tracker'),
            ('fft_spectrum', 'FFT Spectrum'),
            ('octave_spectrum', 'Octave Spectrum'),
            ('levels', 'Audio Levels'),
            ('delay_estimator', 'Delay Estimator'),
            ('scope', 'Audio Scope'),
            ('spectrogram', 'Spectrogram')
        ]

        # Arrange in a 3x3 grid (3 columns, multiple rows as needed)
        cols = 3
        for i, (data_type, title) in enumerate(data_types_info):
            row = i // cols
            col = i % cols
            
            widget = MessageDisplayWidget(data_type, title, self)
            self.grid_layout.addWidget(widget, row, col)
            self.active_widgets[data_type] = widget

        # If we have remaining space, add a spacer
        if len(data_types_info) % cols != 0:
            remaining_cols = cols - (len(data_types_info) % cols)
            last_row = (len(data_types_info) - 1) // cols
            for col in range(cols - remaining_cols, cols):
                spacer = QWidget()
                spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                self.grid_layout.addWidget(spacer, last_row, col)

    def update_message(self, message: str, data_type: str):
        """Update message display for specific data type."""
        if data_type in self.active_widgets:
            self.active_widgets[data_type].update_message(message)


class StreamMessagesWindow(QMainWindow):
    """Main application window."""

    def __init__(self, websocket_client):
        super().__init__()

        self.websocket_client = websocket_client

        # Setup UI
        self.setWindowTitle("Friture Stream Messages - Live Data Monitor")
        self.setGeometry(50, 50, 1400, 800)  # Optimized size for grid layout

        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(5)

        # Top panel: Statistics (horizontal)
        self.statistics_panel = StatisticsPanel()
        main_layout.addWidget(self.statistics_panel)

        # Main panel: Message displays
        self.message_area = MessageDisplayArea()
        main_layout.addWidget(self.message_area, stretch=1)

        # Setup menu bar
        self._setup_menu_bar()

        # Setup status bar
        self.status_bar = self.statusBar()
        self.status_label = QLabel("Ready - Click File > Connect to start")
        self.status_bar.addWidget(self.status_label)

        # Control buttons in status bar
        button_widget = QWidget()
        button_layout = QHBoxLayout(button_widget)
        button_layout.setContentsMargins(0, 0, 0, 0)

        self.connect_button = QPushButton("🔌 Connect")
        self.connect_button.clicked.connect(self.websocket_client.start)
        self.connect_button.setMaximumHeight(25)
        button_layout.addWidget(self.connect_button)

        self.disconnect_button = QPushButton("🔌 Disconnect")
        self.disconnect_button.clicked.connect(self.websocket_client.stop)
        self.disconnect_button.setMaximumHeight(25)
        self.disconnect_button.setEnabled(False)
        button_layout.addWidget(self.disconnect_button)

        clear_all_button = QPushButton("🗑️ Clear All")
        clear_all_button.clicked.connect(self._clear_all_messages)
        clear_all_button.setMaximumHeight(25)
        button_layout.addWidget(clear_all_button)

        self.status_bar.addPermanentWidget(button_widget)

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
        connect_action.setShortcut('Ctrl+O')
        file_menu.addAction(connect_action)

        # Disconnect action
        disconnect_action = QAction('Disconnect', self)
        disconnect_action.triggered.connect(self.websocket_client.stop)
        disconnect_action.setShortcut('Ctrl+D')
        file_menu.addAction(disconnect_action)

        file_menu.addSeparator()

        # Exit action
        exit_action = QAction('Exit', self)
        exit_action.triggered.connect(self.close)
        exit_action.setShortcut('Ctrl+Q')
        file_menu.addAction(exit_action)

        # View menu
        view_menu = menubar.addMenu('View')

        # Clear all messages action
        clear_all_action = QAction('Clear All Messages', self)
        clear_all_action.triggered.connect(self._clear_all_messages)
        clear_all_action.setShortcut('Ctrl+L')
        view_menu.addAction(clear_all_action)

        # Tools menu
        tools_menu = menubar.addMenu('Tools')
        
        copy_all_action = QAction('Copy All Messages', self)
        copy_all_action.triggered.connect(self._copy_all_messages)
        copy_all_action.setShortcut('Ctrl+Shift+C')
        tools_menu.addAction(copy_all_action)

    def _connect_signals(self):
        """Connect WebSocket client signals to UI slots."""
        self.websocket_client.rawMessageReceived.connect(self.message_area.update_message)
        self.websocket_client.connectionStatusChanged.connect(self._on_connection_status_changed)
        self.websocket_client.statisticsUpdated.connect(self.statistics_panel.update_statistics)
        self.websocket_client.errorOccurred.connect(self._on_error_occurred)

    def _on_connection_status_changed(self, status: str):
        """Handle connection status changes."""
        if status == "connected":
            self.status_label.setText("🟢 Connected - Receiving data")
            self.connect_button.setEnabled(False)
            self.disconnect_button.setEnabled(True)
        elif status == "connecting":
            self.status_label.setText("🟡 Connecting...")
            self.connect_button.setEnabled(False)
            self.disconnect_button.setEnabled(False)
        else:
            self.status_label.setText("🔴 Disconnected")
            self.connect_button.setEnabled(True)
            self.disconnect_button.setEnabled(False)

    def _on_error_occurred(self, error: str):
        """Handle errors."""
        self.status_label.setText(f"❌ Error: {error}")
        QTimer.singleShot(5000, lambda: self.status_label.setText("🔴 Disconnected"))

    def _clear_all_messages(self):
        """Clear all message displays."""
        for widget in self.message_area.active_widgets.values():
            widget.clear_message()
        self.status_label.setText("🗑️ All messages cleared")
        QTimer.singleShot(2000, lambda: self.status_label.setText("🔴 Disconnected" if not self.websocket_client.connected else "🟢 Connected - Receiving data"))

    def _copy_all_messages(self):
        """Copy all current messages to clipboard as a combined JSON."""
        try:
            from PyQt5.QtWidgets import QApplication
            
            all_messages = {}
            for data_type, widget in self.message_area.active_widgets.items():
                if widget.last_message:
                    try:
                        parsed = json.loads(widget.last_message)
                        all_messages[data_type] = {
                            'timestamp': widget.last_timestamp,
                            'count': widget.message_count,
                            'data': parsed
                        }
                    except json.JSONDecodeError:
                        all_messages[data_type] = {
                            'timestamp': widget.last_timestamp,
                            'count': widget.message_count,
                            'raw_data': widget.last_message
                        }

            if all_messages:
                combined_json = json.dumps(all_messages, indent=2)
                clipboard = QApplication.clipboard()
                clipboard.setText(combined_json)
                
                self.status_label.setText("✅ All messages copied to clipboard")
                QTimer.singleShot(3000, lambda: self.status_label.setText("🟢 Connected - Receiving data" if self.websocket_client.connected else "🔴 Disconnected"))
            else:
                self.status_label.setText("ℹ️ No messages to copy")
                QTimer.singleShot(2000, lambda: self.status_label.setText("🟢 Connected - Receiving data" if self.websocket_client.connected else "🔴 Disconnected"))

        except Exception as e:
            logger.error(f"Error copying all messages: {e}")
            self.status_label.setText("❌ Copy all failed")

    def closeEvent(self, event):
        """Handle window close event."""
        self.websocket_client.stop()
        event.accept()


class StreamMessagesApp:
    """Main application class."""

    def __init__(self, host: str = 'localhost', port: int = 8765):
        self.qt_app = QApplication(sys.argv)
        self.qt_app.setApplicationName("Friture Stream Messages")
        self.qt_app.setApplicationVersion("2.0")
        
        # Set application style
        self.qt_app.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #cccccc;
                border-radius: 5px;
                margin-top: 1ex;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QPushButton {
                background-color: #e7e7e7;
                border: 1px solid #999;
                border-radius: 3px;
                padding: 5px;
                min-width: 50px;
            }
            QPushButton:hover {
                background-color: #d4edda;
            }
            QPushButton:pressed {
                background-color: #c3e6cb;
            }
            QPushButton:disabled {
                background-color: #f8f9fa;
                color: #999;
            }
        """)

        # Create WebSocket client
        self.websocket_client = StreamingWebSocketClient(host, port)

        # Create main window
        self.main_window = StreamMessagesWindow(self.websocket_client)

    def run(self):
        """Run the application."""
        # Show main window
        self.main_window.show()

        # Run Qt event loop
        return self.qt_app.exec_()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Friture Stream Messages - Display last message for each data type")
    parser.add_argument('--host', default='localhost', help='WebSocket server host')
    parser.add_argument('--port', type=int, default=8765, help='WebSocket server port')

    args = parser.parse_args()

    try:
        app = StreamMessagesApp(args.host, args.port)
        sys.exit(app.run())
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
    except Exception as e:
        logger.error(f"Application error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()