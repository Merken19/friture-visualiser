#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test script for RawAudioProducer functionality.

This script tests the raw microphone input producer to ensure it streams
audio data with minimal overhead as intended.
"""

import sys
import time
import numpy as np
from PyQt5.QtCore import QCoreApplication

# Add the friture directory to the path
sys.path.insert(0, '.')

from friture.api.streaming_api import get_streaming_api
from friture.api.data_types import DataType
from friture.api.consumers import CallbackConsumer
from friture.api.producers import RawAudioProducer
from friture.audiobackend import AudioBackend


def test_raw_audio_producer():
    """Test the RawAudioProducer functionality."""

    # Create Qt application
    app = QCoreApplication(sys.argv)

    # Get audio backend
    audio_backend = AudioBackend()

    # Setup timer to fetch audio data (similar to main application)
    from PyQt5.QtCore import QTimer
    audio_timer = QTimer()
    audio_timer.timeout.connect(audio_backend.fetchAudioData)
    audio_timer.setInterval(20)  # ~50 Hz, similar to display timer
    audio_timer.start()

    # Get streaming API
    api = get_streaming_api()

    # Create raw audio producer
    producer = RawAudioProducer(audio_backend, "test_raw_audio")

    # Register producer
    api.register_producer(DataType.RAW_AUDIO, producer)

    # Create callback consumer to verify data
    received_data = []

    def data_callback(data):
        received_data.append(data)
        print(f"Received raw audio data: {data.data.samples.shape} samples, "
              f"{data.data.channels} channels, "
              f"sample_rate={data.data.sample_rate}, "
              f"dtype={data.data.dtype}")

    consumer = CallbackConsumer(data_callback)
    api.register_consumer(DataType.RAW_AUDIO, consumer)

    # Start streaming
    api.start_streaming()
    producer.start()

    print("RawAudioProducer test started. Listening for audio data...")

    # Run for a short time to collect some data
    start_time = time.time()
    while time.time() - start_time < 3.0:  # Run for 3 seconds
        app.processEvents()

        # Check if we received any data
        if received_data:
            print(f"Successfully received {len(received_data)} data packets")
            break

    # Stop everything
    audio_timer.stop()
    producer.stop()
    api.stop_streaming()

    # Verify results
    if received_data:
        print("✓ RawAudioProducer test PASSED")
        print(f"  - Received {len(received_data)} data packets")
        print(f"  - Sample shape: {received_data[0].data.samples.shape}")
        print(f"  - Sample rate: {received_data[0].data.sample_rate}")
        print(f"  - Channels: {received_data[0].data.channels}")
        print(f"  - Data type: {received_data[0].data.dtype}")
        return True
    else:
        print("✗ RawAudioProducer test FAILED - No data received")
        return False


if __name__ == "__main__":
    success = test_raw_audio_producer()
    sys.exit(0 if success else 1)