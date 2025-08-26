#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test script to check if Friture streaming API is working
"""

import time
from friture.api.streaming_api import get_streaming_api
from friture.api.data_types import DataType
from friture.api.consumers import CallbackConsumer

def test_callback(data):
    """Simple callback to test if data is flowing"""
    print(f"Received data: {data.metadata.data_type.value} at {data.metadata.timestamp}")
    if hasattr(data.data, 'frequency_hz'):
        print(f"  Pitch: {data.data.frequency_hz} Hz")
    elif hasattr(data.data, 'peak_frequency'):
        print(f"  Spectrum peak: {data.data.peak_frequency} Hz")

def main():
    print("Testing Friture streaming API...")
    
    # Get the streaming API
    api = get_streaming_api()
    
    # Create test consumers for different data types
    pitch_consumer = CallbackConsumer(test_callback)
    spectrum_consumer = CallbackConsumer(test_callback)
    
    # Register consumers
    try:
        pitch_id = api.register_consumer(DataType.PITCH_TRACKER, pitch_consumer)
        spectrum_id = api.register_consumer(DataType.FFT_SPECTRUM, spectrum_consumer)
        print(f"Registered consumers: pitch={pitch_id}, spectrum={spectrum_id}")
    except Exception as e:
        print(f"Error registering consumers: {e}")
        return
    
    # Start streaming
    try:
        api.start_streaming()
        print("Streaming started. Listening for data... (Ctrl+C to stop)")
        
        # Wait for data
        for i in range(30):  # Wait 30 seconds
            time.sleep(1)
            print(f"Waiting... {i+1}/30")
            
    except KeyboardInterrupt:
        print("\nStopping...")
    except Exception as e:
        print(f"Error during streaming: {e}")
    finally:
        api.stop_streaming()
        print("Streaming stopped")

if __name__ == "__main__":
    main()