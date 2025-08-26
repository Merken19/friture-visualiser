#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Direct WebSocket bridge that hooks into existing Friture widgets
"""

import json
import logging
from PyQt5.QtCore import QObject, pyqtSignal, QTimer
from friture.api.protocols import WebSocketProtocol

class FritureWebSocketBridge(QObject):
    """Bridge that connects Friture widgets directly to WebSocket clients"""
    
    def __init__(self, parent=None, port=8765):
        super().__init__(parent)
        
        self.logger = logging.getLogger(__name__)
        self.websocket_protocol = WebSocketProtocol(port=port)
        
        # Track connected widgets
        self.pitch_tracker = None
        self.spectrum_widget = None
        
        # Data caching for new clients
        self.latest_pitch_data = None
        self.latest_spectrum_data = None
        
        # Setup WebSocket handlers
        self.websocket_protocol.client_connected.connect(self.on_client_connected)
        self.websocket_protocol.client_disconnected.connect(self.on_client_disconnected)
    
    def start(self):
        """Start the WebSocket bridge"""
        self.websocket_protocol.start()
        self.logger.info(f"WebSocket bridge started on port {self.websocket_protocol.port}")
        
    def stop(self):
        """Stop the WebSocket bridge"""
        self.websocket_protocol.stop()
        self.logger.info("WebSocket bridge stopped")
    
    def connect_pitch_tracker(self, pitch_tracker_widget):
        """Connect to a PitchTrackerWidget"""
        self.pitch_tracker = pitch_tracker_widget
        
        # Connect to the pitch_changed signal
        pitch_data = pitch_tracker_widget._pitch_tracker_data
        pitch_data.pitch_changed.connect(self.on_pitch_changed)
        
        self.logger.info("Connected to pitch tracker widget")
    
    def connect_spectrum_widget(self, spectrum_widget):
        """Connect to a spectrum analyzer widget (you'll need to identify the correct one)"""
        self.spectrum_widget = spectrum_widget
        # This will depend on your spectrum widget implementation
        self.logger.info("Connected to spectrum widget")
    
    def on_pitch_changed(self, frequency_hz):
        """Handle pitch changes from the pitch tracker"""
        if self.pitch_tracker is None:
            return
            
        # Get additional pitch data
        pitch_data_obj = self.pitch_tracker._pitch_tracker_data
        note_name = pitch_data_obj.note
        
        # Calculate confidence based on the tracker's detection
        # This is a simplified confidence measure
        confidence = 1.0 if frequency_hz > 0 and not str(frequency_hz) == 'nan' else 0.0
        
        # Create the message
        message = {
            "type": "pitch_update",
            "data": {
                "frequency_hz": float(frequency_hz) if frequency_hz and str(frequency_hz) != 'nan' else 0.0,
                "note_name": note_name,
                "confidence": confidence
            }
        }
        
        # Cache for new clients
        self.latest_pitch_data = message
        
        # Send to all connected clients
        self.websocket_protocol.send_data(json.dumps(message))
        
        self.logger.debug(f"Sent pitch update: {frequency_hz} Hz ({note_name})")
    
    def on_spectrum_data_ready(self, frequencies, magnitudes):
        """Handle spectrum data (you'll need to connect this to your spectrum widget)"""
        if len(frequencies) == 0 or len(magnitudes) == 0:
            return
            
        # Find peak
        peak_idx = magnitudes.argmax()
        peak_frequency = frequencies[peak_idx]
        peak_magnitude = magnitudes[peak_idx]
        
        message = {
            "type": "spectrum_update",
            "data": {
                "frequencies": frequencies.tolist() if hasattr(frequencies, 'tolist') else list(frequencies),
                "magnitudes": magnitudes.tolist() if hasattr(magnitudes, 'tolist') else list(magnitudes),
                "peak_frequency": float(peak_frequency),
                "peak_magnitude": float(peak_magnitude)
            }
        }
        
        # Cache for new clients
        self.latest_spectrum_data = message
        
        # Send to all connected clients
        self.websocket_protocol.send_data(json.dumps(message))
        
        self.logger.debug(f"Sent spectrum update: peak at {peak_frequency} Hz")
    
    def on_client_connected(self, client_id):
        """Handle new client connections"""
        self.logger.info(f"WebSocket client connected: {client_id}")
        
        # Send latest data to new client
        if self.latest_pitch_data:
            self.websocket_protocol.send_data(json.dumps(self.latest_pitch_data), client_id)
        
        if self.latest_spectrum_data:
            self.websocket_protocol.send_data(json.dumps(self.latest_spectrum_data), client_id)
    
    def on_client_disconnected(self, client_id):
        """Handle client disconnections"""
        self.logger.info(f"WebSocket client disconnected: {client_id}")


# Helper function to inject the bridge into Friture
def inject_websocket_bridge_into_friture():
    """
    This function should be called from within Friture's main application
    to inject the WebSocket bridge into existing widgets.
    """
    
    # You'll need to adapt this to your specific Friture setup
    # This is a template showing how to connect the bridge
    
    bridge = FritureWebSocketBridge()
    bridge.start()
    
    # Example of how you might find and connect to widgets
    # You'll need to adapt this to your actual widget management system
    
    def find_and_connect_widgets():
        """Find pitch tracker and spectrum widgets and connect them to the bridge"""
        import friture  # Adjust import as needed
        
        # This is pseudo-code - you'll need to adapt to your widget management
        # Look for pitch tracker widgets in your application
        for widget in get_active_widgets():  # You need to implement this
            if isinstance(widget, PitchTrackerWidget):
                bridge.connect_pitch_tracker(widget)
                print(f"Connected WebSocket bridge to pitch tracker widget")
            # Add similar logic for spectrum widgets
    
    # Try to connect to widgets
    find_and_connect_widgets()
    
    return bridge


# Alternative: Manual integration script
if __name__ == "__main__":
    """
    Manual test script - you can use this to test the WebSocket server
    and manually send test data.
    """
    import time
    import numpy as np
    
    bridge = FritureWebSocketBridge()
    bridge.start()
    
    print("WebSocket bridge started on ws://localhost:8765")
    print("Connect your React app, then this will send test data...")
    
    # Wait for client to connect
    input("Press Enter after connecting your React app...")
    
    # Send test data
    for i in range(20):
        # Simulate pitch detection
        frequency = 440.0 + np.sin(i * 0.3) * 100  # Varying around A4
        note_name = f"A{4 + int(frequency/440)}"  # Simplified note calculation
        
        # Manually trigger the pitch update
        bridge.on_pitch_changed(frequency)
        
        # Simulate spectrum data
        frequencies = np.linspace(0, 2000, 100)
        magnitudes = -60 + 40 * np.exp(-((frequencies - frequency) / 50) ** 2) + np.random.normal(0, 2, 100)
        
        bridge.on_spectrum_data_ready(frequencies, magnitudes)
        
        print(f"Sent test data {i+1}/20: {frequency:.1f} Hz")
        time.sleep(0.5)
    
    print("Test complete. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        bridge.stop()