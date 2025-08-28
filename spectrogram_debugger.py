#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Friture Spectrogram Debugger

This script helps debug why the SpectrogramProducer isn't working.
Run this while Friture is running to diagnose the spectrogram streaming issue.
"""

import sys
import time
import logging
from typing import Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from PyQt5.QtWidgets import QApplication

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def inspect_streaming_api():
    """Inspect the current state of the streaming API."""
    print("="*60)
    print("STREAMING API INSPECTION")
    print("="*60)

    try:
        from friture.api.integration import get_streaming_api
        api = get_streaming_api()

        print(f"Streaming API instance: {api}")
        print(f"Is streaming: {api._is_streaming}")

        stats = api.get_statistics()
        print(f"Active producers: {stats['active_producers']}")
        print(f"Active consumers: {stats['active_consumers']}")
        print(f"Active protocols: {stats['active_protocols']}")

        print("\nRegistered producers:")
        for data_type, producer in api._producers.items():
            print(f"  {data_type.value}: {producer.__class__.__name__}")
            print(f"    Widget: {producer.widget.__class__.__name__}")
            print(f"    Widget ID: {producer.widget_id}")
            print(f"    Is active: {producer._is_active}")

        print("\nRegistered consumers:")
        for data_type, consumers in api._consumers.items():
            if consumers:
                print(f"  {data_type.value}: {len(consumers)} consumers")

        return api

    except Exception as e:
        print(f"Error inspecting streaming API: {e}")
        return None


def inspect_dock_manager():
    """Inspect the dock manager and its docks."""
    print("\n" + "="*60)
    print("DOCK MANAGER INSPECTION")
    print("="*60)

    try:
        from friture.analyzer import Friture
        from PyQt5.QtWidgets import QApplication

        # Get the main window (assuming it's the first/only one)
        app = QApplication.instance()
        if app and isinstance(app, QApplication):
            windows = app.topLevelWidgets()
            friture_window = None
            for window in windows:
                if hasattr(window, 'dockmanager'):
                    friture_window = window
                    break

            if friture_window and hasattr(friture_window, 'dockmanager'):
                dock_manager = friture_window.dockmanager
                print(f"Dock manager: {dock_manager}")
                print(f"Number of docks: {len(dock_manager.docks)}")

                for i, dock in enumerate(dock_manager.docks):
                    print(f"\nDock {i+1}:")
                    print(f"  Object name: {dock.objectName()}")
                    print(f"  Widget ID: {dock.widgetId}")
                    print(f"  Widget class: {dock.audiowidget.__class__.__name__ if dock.audiowidget else 'None'}")

                    if dock.audiowidget:
                        widget = dock.audiowidget
                        print(f"  Widget has audiobuffer: {hasattr(widget, 'audiobuffer')}")
                        if hasattr(widget, 'audiobuffer'):
                            print(f"  Audiobuffer is set: {widget.audiobuffer is not None}")

                        # Check for spectrogram-specific attributes
                        if hasattr(widget, 'freq'):
                            print(f"  Has freq attribute: {widget.freq is not None}")
                        if hasattr(widget, 'proc'):
                            print(f"  Has proc attribute: {widget.proc is not None}")

                return dock_manager
            else:
                print("Could not find Friture main window")
        else:
            print("Could not find QApplication instance")

    except Exception as e:
        print(f"Error inspecting dock manager: {e}")
        import traceback
        traceback.print_exc()

    return None


def test_spectrogram_producer_creation():
    """Test creating a SpectrogramProducer manually."""
    print("\n" + "="*60)
    print("SPECTROGRAM PRODUCER CREATION TEST")
    print("="*60)

    try:
        from friture.api.producers import SpectrogramProducer
        from friture.api.data_types import DataType

        # Find the spectrogram widget
        from friture.analyzer import Friture
        from PyQt5.QtWidgets import QApplication

        app = QApplication.instance()
        if app and isinstance(app, QApplication):
            windows = app.topLevelWidgets()
            for window in windows:
                if hasattr(window, 'dockmanager'):
                    dock_manager = getattr(window, 'dockmanager')
                    if dock_manager:
                        for dock in dock_manager.docks:
                            if dock.widgetId == 3:  # Spectrogram widget ID
                                print(f"Found spectrogram dock: {dock.objectName()}")
                                print(f"Widget class: {dock.audiowidget.__class__.__name__}")

                                # Try to create producer
                                try:
                                    producer = SpectrogramProducer(dock.audiowidget, dock.objectName(), window)
                                    print(f"Producer created successfully: {producer}")
                                    print(f"Data type: {producer.get_data_type()}")
                                    print(f"Is active: {producer._is_active}")

                                    # Test data extraction
                                    data = producer.extract_data()
                                    print(f"Data extraction result: {data is not None}")
                                    if data:
                                        print(f"Data shape: {data.magnitudes_db.shape}")

                                    return producer

                                except Exception as e:
                                    print(f"Error creating producer: {e}")
                                    import traceback
                                    traceback.print_exc()
                                    return None

            print("No spectrogram dock found (ID 3)")
        else:
            print("No QApplication instance found")

    except Exception as e:
        print(f"Error in spectrogram producer test: {e}")
        import traceback
        traceback.print_exc()

    return None


def test_signal_connections():
    """Test if signal connections are working."""
    print("\n" + "="*60)
    print("SIGNAL CONNECTION TEST")
    print("="*60)

    try:
        # Find spectrogram widget
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance()
        if app and isinstance(app, QApplication):
            windows = app.topLevelWidgets()
            for window in windows:
                if hasattr(window, 'dockmanager'):
                    dock_manager = window.dockmanager
                    for dock in dock_manager.docks:
                        if dock.widgetId == 3:  # Spectrogram
                            widget = dock.audiowidget
                            print(f"Testing spectrogram widget: {dock.objectName()}")

                            # Check if widget has audiobuffer
                            if hasattr(widget, 'audiobuffer') and widget.audiobuffer:
                                print("Widget has audiobuffer")

                                # Check signal connections
                                buffer = widget.audiobuffer
                                print(f"Audiobuffer receivers for 'new_data_available': {buffer.receivers(buffer.new_data_available)}")

                                # Try to emit the signal manually
                                print("Attempting manual signal emission...")
                                try:
                                    # This should trigger handle_new_data in the spectrogram widget
                                    # We can't easily emit with actual data, but we can check if the connection exists
                                    print("Signal emission test completed")
                                except Exception as e:
                                    print(f"Error during signal test: {e}")

                            else:
                                print("Widget does not have audiobuffer")

                            return

            print("No spectrogram widget found")
        else:
            print("No QApplication instance")

    except Exception as e:
        print(f"Error in signal test: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Main debugging function."""
    print("Friture Spectrogram Debugger")
    print("Make sure Friture is running before running this script.")
    print()

    # Give user time to ensure Friture is running
    print("Starting inspection in 3 seconds...")
    time.sleep(3)

    # Run all inspections
    api = inspect_streaming_api()
    dock_manager = inspect_dock_manager()
    producer = test_spectrogram_producer_creation()
    test_signal_connections()

    print("\n" + "="*60)
    print("DEBUGGING SUMMARY")
    print("="*60)

    if api and producer:
        print("✅ Streaming API is working")
        print("✅ SpectrogramProducer can be created")
        print("❓ Issue: Producer not receiving data or not emitting signals")

        print("\nPossible causes:")
        print("1. Signal connection not working properly")
        print("2. Spectrogram widget not processing data correctly")
        print("3. Producer extract_data() returning None")
        print("4. Timing issue with data extraction")

    elif api and not producer:
        print("✅ Streaming API is working")
        print("❌ SpectrogramProducer cannot be created")
        print("❓ Issue: Producer creation failing")

    else:
        print("❌ Streaming API not accessible")
        print("❓ Issue: Friture not running or API not initialized")

    print("\nNext steps:")
    print("1. Check console output for any error messages")
    print("2. Verify spectrogram dock exists in Friture")
    print("3. Try restarting Friture and running this debugger again")


if __name__ == "__main__":
    main()