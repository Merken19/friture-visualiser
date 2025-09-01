#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Simple FFT Spectrum Visualizer
Displays raw frequency vs magnitude data from WebSocket API.
"""

import json
import asyncio
import threading
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation

class WebSocketFFTClient:
    def __init__(self, host='localhost', port=8765):
        self.host = host
        self.port = port
        self.running = False
        self.frequencies = None
        self.magnitudes = None
        self.data_updated = False

    def start(self):
        if self.running:
            return
        self.running = True
        thread = threading.Thread(target=self._run_client, daemon=True)
        thread.start()

    def stop(self):
        self.running = False

    def _run_client(self):
        try:
            asyncio.run(self._connect_and_listen())
        except Exception as e:
            print(f"WebSocket error: {e}")

    async def _connect_and_listen(self):
        try:
            import websockets
            uri = f"ws://{self.host}:{self.port}"
            async with websockets.connect(uri) as websocket:
                print("Connected")
                while self.running:
                    try:
                        message = await websocket.recv()
                        self._process_message(message)
                    except:
                        break
        except Exception as e:
            print(f"Connection error: {e}")

    def _process_message(self, message):
        try:
            data = json.loads(message if isinstance(message, str) else message.decode('utf-8'))
            spectrum_data = data.get('data', {})
            frequencies = spectrum_data.get('frequencies', [])
            magnitudes = spectrum_data.get('magnitudes_db', [])
            
            if frequencies and magnitudes and len(frequencies) == len(magnitudes):
                self.frequencies = np.array(frequencies)
                self.magnitudes = np.array(magnitudes)
                self.data_updated = True
        except:
            pass

class FFTVisualizer:
    def __init__(self, host='localhost', port=8765):
        self.ws_client = WebSocketFFTClient(host, port)
        self.fig, self.ax = plt.subplots(figsize=(10, 6))
        self.line, = self.ax.plot([], [])
        self.info_text = self.ax.text(0.02, 0.98, '', transform=self.ax.transAxes,
                                    verticalalignment='top', fontsize=9,
                                    bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))

    def update_plot(self, frame):
        if self.ws_client.data_updated and self.ws_client.frequencies is not None:
            frequencies = self.ws_client.frequencies
            magnitudes = self.ws_client.magnitudes
            
            self.line.set_data(frequencies, magnitudes)
            self.ax.relim()
            self.ax.autoscale_view()
            
            # Update info text
            num_points = len(frequencies)
            freq_min, freq_max = np.min(frequencies), np.max(frequencies)
            mag_min, mag_max = np.min(magnitudes), np.max(magnitudes)
            
            info_text = f"Points: {num_points}\nFreq: {freq_min:.1f} - {freq_max:.1f} Hz\nMag: {mag_min:.2e} - {mag_max:.2e}"
            self.info_text.set_text(info_text)
            
            self.ws_client.data_updated = False
        return self.line, self.info_text

    def run(self):
        self.ws_client.start()
        self.ani = animation.FuncAnimation(self.fig, self.update_plot, interval=50, blit=True)
        plt.show()
        self.ws_client.stop()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='localhost')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    
    visualizer = FFTVisualizer(args.host, args.port)
    visualizer.run()