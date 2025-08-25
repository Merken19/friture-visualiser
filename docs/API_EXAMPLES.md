# Friture Streaming API Examples

This document provides practical examples for using the Friture Streaming API in various scenarios.

## Table of Contents

1. [Basic Examples](#basic-examples)
2. [Web Integration](#web-integration)
3. [Data Analysis](#data-analysis)
4. [External System Integration](#external-system-integration)
5. [Performance Optimization](#performance-optimization)
6. [Custom Implementations](#custom-implementations)

## Basic Examples

### Simple Pitch Monitoring

```python
from friture.api import get_streaming_api, DataType, CallbackConsumer

def monitor_pitch():
    api = get_streaming_api()
    
    def pitch_callback(data):
        pitch = data.data
        if pitch.frequency_hz and pitch.confidence > 0.7:
            print(f"♪ {pitch.note_name}: {pitch.frequency_hz:.1f} Hz "
                  f"(confidence: {pitch.confidence:.2f})")
    
    consumer = CallbackConsumer(pitch_callback)
    api.register_consumer(DataType.PITCH_TRACKER, consumer)
    api.start_streaming()
    
    print("Pitch monitoring started. Play some music!")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        api.stop_streaming()
        print("Monitoring stopped.")

if __name__ == "__main__":
    monitor_pitch()
```

### FFT Spectrum Analysis

```python
import numpy as np
from friture.api import get_streaming_api, DataType, CallbackConsumer

def analyze_spectrum():
    api = get_streaming_api()
    
    def spectrum_callback(data):
        spectrum = data.data
        
        # Find dominant frequencies
        threshold_db = -30
        dominant_mask = spectrum.magnitudes_db > threshold_db
        dominant_freqs = spectrum.frequencies[dominant_mask]
        dominant_mags = spectrum.magnitudes_db[dominant_mask]
        
        if len(dominant_freqs) > 0:
            print(f"Dominant frequencies:")
            for freq, mag in zip(dominant_freqs[:5], dominant_mags[:5]):
                print(f"  {freq:.1f} Hz: {mag:.1f} dB")
            print()
    
    consumer = CallbackConsumer(spectrum_callback)
    api.register_consumer(DataType.FFT_SPECTRUM, consumer)
    api.start_streaming()
    
    try:
        while True:
            time.sleep(2)
    except KeyboardInterrupt:
        api.stop_streaming()

if __name__ == "__main__":
    analyze_spectrum()
```

## Web Integration

### Real-time Web Dashboard

**Python Backend:**

```python
import json
import asyncio
import websockets
from friture.api import get_streaming_api, DataType, CallbackConsumer, WebSocketProtocol

class WebDashboard:
    def __init__(self):
        self.api = get_streaming_api()
        self.websocket_protocol = WebSocketProtocol(port=8765)
        self.api.add_protocol(self.websocket_protocol)
        
        # Setup consumers
        self.setup_consumers()
        
    def setup_consumers(self):
        # Pitch data
        pitch_consumer = CallbackConsumer(self.send_pitch_data)
        self.api.register_consumer(DataType.PITCH_TRACKER, pitch_consumer)
        
        # Spectrum data (downsampled for web)
        spectrum_consumer = CallbackConsumer(self.send_spectrum_data)
        self.api.register_consumer(DataType.FFT_SPECTRUM, spectrum_consumer)
        
        # Level meters
        levels_consumer = CallbackConsumer(self.send_levels_data)
        self.api.register_consumer(DataType.LEVELS, levels_consumer)
    
    def send_pitch_data(self, data):
        message = {
            'type': 'pitch',
            'data': {
                'frequency': data.data.frequency_hz,
                'note': data.data.note_name,
                'confidence': data.data.confidence,
                'timestamp': data.metadata.timestamp
            }
        }
        self.websocket_protocol.send_data(json.dumps(message))
    
    def send_spectrum_data(self, data):
        spectrum = data.data
        
        # Downsample for web (every 4th point)
        step = 4
        message = {
            'type': 'spectrum',
            'data': {
                'frequencies': spectrum.frequencies[::step].tolist(),
                'magnitudes': spectrum.magnitudes_db[::step].tolist(),
                'peak_frequency': spectrum.peak_frequency,
                'timestamp': data.metadata.timestamp
            }
        }
        self.websocket_protocol.send_data(json.dumps(message))
    
    def send_levels_data(self, data):
        message = {
            'type': 'levels',
            'data': {
                'peak_levels': data.data.peak_levels_db.tolist(),
                'rms_levels': data.data.rms_levels_db.tolist(),
                'timestamp': data.metadata.timestamp
            }
        }
        self.websocket_protocol.send_data(json.dumps(message))
    
    def start(self):
        self.api.start_streaming()
        print("Web dashboard started on ws://localhost:8765")
    
    def stop(self):
        self.api.stop_streaming()

# Start dashboard
dashboard = WebDashboard()
dashboard.start()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    dashboard.stop()
```

**HTML/JavaScript Frontend:**

```html
<!DOCTYPE html>
<html>
<head>
    <title>Friture Real-time Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .widget { margin: 20px 0; padding: 20px; border: 1px solid #ccc; }
        .pitch-display { font-size: 24px; font-weight: bold; }
        .levels { display: flex; gap: 20px; }
        .level-meter { width: 50px; height: 200px; background: #eee; position: relative; }
        .level-bar { position: absolute; bottom: 0; width: 100%; background: green; }
    </style>
</head>
<body>
    <h1>Friture Real-time Dashboard</h1>
    
    <div class="widget">
        <h2>Pitch Tracker</h2>
        <div id="pitch-display" class="pitch-display">No pitch detected</div>
        <div id="pitch-confidence">Confidence: 0%</div>
    </div>
    
    <div class="widget">
        <h2>Spectrum Analyzer</h2>
        <canvas id="spectrum-chart" width="800" height="400"></canvas>
    </div>
    
    <div class="widget">
        <h2>Level Meters</h2>
        <div class="levels">
            <div class="level-meter">
                <div id="level-bar-0" class="level-bar" style="height: 0%"></div>
                <div>Ch 1</div>
            </div>
            <div class="level-meter">
                <div id="level-bar-1" class="level-bar" style="height: 0%"></div>
                <div>Ch 2</div>
            </div>
        </div>
    </div>

    <script>
        // WebSocket connection
        const ws = new WebSocket('ws://localhost:8765');
        
        // Spectrum chart setup
        const ctx = document.getElementById('spectrum-chart').getContext('2d');
        const spectrumChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Magnitude (dB)',
                    data: [],
                    borderColor: 'rgb(75, 192, 192)',
                    tension: 0.1
                }]
            },
            options: {
                responsive: true,
                scales: {
                    x: { type: 'logarithmic', title: { display: true, text: 'Frequency (Hz)' }},
                    y: { title: { display: true, text: 'Magnitude (dB)' }}
                },
                animation: false
            }
        });
        
        // Message handler
        ws.onmessage = function(event) {
            const message = JSON.parse(event.data);
            
            switch(message.type) {
                case 'pitch':
                    updatePitchDisplay(message.data);
                    break;
                case 'spectrum':
                    updateSpectrumChart(message.data);
                    break;
                case 'levels':
                    updateLevelMeters(message.data);
                    break;
            }
        };
        
        function updatePitchDisplay(data) {
            const pitchElement = document.getElementById('pitch-display');
            const confidenceElement = document.getElementById('pitch-confidence');
            
            if (data.frequency && data.confidence > 0.5) {
                pitchElement.textContent = `${data.note} (${data.frequency.toFixed(1)} Hz)`;
                pitchElement.style.color = data.confidence > 0.8 ? 'green' : 'orange';
            } else {
                pitchElement.textContent = 'No pitch detected';
                pitchElement.style.color = 'gray';
            }
            
            confidenceElement.textContent = `Confidence: ${(data.confidence * 100).toFixed(0)}%`;
        }
        
        function updateSpectrumChart(data) {
            spectrumChart.data.labels = data.frequencies;
            spectrumChart.data.datasets[0].data = data.magnitudes;
            spectrumChart.update('none'); // No animation for real-time
        }
        
        function updateLevelMeters(data) {
            data.peak_levels.forEach((level, index) => {
                const levelBar = document.getElementById(`level-bar-${index}`);
                if (levelBar) {
                    // Convert dB FS to percentage (assuming -60 dB to 0 dB range)
                    const percentage = Math.max(0, Math.min(100, (level + 60) / 60 * 100));
                    levelBar.style.height = `${percentage}%`;
                    
                    // Color coding
                    if (level > -6) levelBar.style.background = 'red';
                    else if (level > -20) levelBar.style.background = 'yellow';
                    else levelBar.style.background = 'green';
                }
            });
        }
        
        ws.onopen = function() {
            console.log('Connected to Friture streaming API');
        };
        
        ws.onclose = function() {
            console.log('Disconnected from Friture streaming API');
        };
        
        ws.onerror = function(error) {
            console.error('WebSocket error:', error);
        };
    </script>
</body>
</html>
```

## Data Analysis

### Pitch Stability Analysis

```python
import numpy as np
from collections import deque
from friture.api import get_streaming_api, DataType, CallbackConsumer

class PitchStabilityAnalyzer:
    def __init__(self, window_size=50):
        self.api = get_streaming_api()
        self.pitch_history = deque(maxlen=window_size)
        self.stability_threshold = 5.0  # Hz
        
        # Setup consumer
        consumer = CallbackConsumer(self.analyze_pitch)
        self.api.register_consumer(DataType.PITCH_TRACKER, consumer)
    
    def analyze_pitch(self, data):
        pitch = data.data
        
        if pitch.frequency_hz and pitch.confidence > 0.6:
            self.pitch_history.append(pitch.frequency_hz)
            
            if len(self.pitch_history) >= 20:  # Minimum samples for analysis
                # Calculate stability metrics
                pitches = np.array(list(self.pitch_history))
                std_dev = np.std(pitches)
                mean_freq = np.mean(pitches)
                
                # Detect stability
                if std_dev < self.stability_threshold:
                    stability_score = 1.0 - (std_dev / self.stability_threshold)
                    print(f"STABLE: {mean_freq:.1f} Hz ± {std_dev:.2f} Hz "
                          f"(stability: {stability_score:.2f})")
                    
                    # Detect musical intervals
                    self.detect_musical_intervals(pitches)
    
    def detect_musical_intervals(self, pitches):
        """Detect if pitch sequence follows musical intervals."""
        if len(pitches) < 10:
            return
        
        # Calculate frequency ratios
        ratios = pitches[1:] / pitches[:-1]
        
        # Common musical intervals (frequency ratios)
        intervals = {
            'octave': 2.0,
            'perfect_fifth': 1.5,
            'perfect_fourth': 4/3,
            'major_third': 5/4,
            'minor_third': 6/5
        }
        
        for interval_name, ratio in intervals.items():
            # Check if any ratio is close to this interval
            close_ratios = np.abs(ratios - ratio) < 0.05
            if np.any(close_ratios):
                print(f"Musical interval detected: {interval_name}")
    
    def start(self):
        self.api.start_streaming()
        print("Pitch stability analyzer started")
    
    def stop(self):
        self.api.stop_streaming()

# Usage
analyzer = PitchStabilityAnalyzer()
analyzer.start()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    analyzer.stop()
```

### Spectral Feature Extraction

```python
import numpy as np
from scipy import signal
from friture.api import get_streaming_api, DataType, CallbackConsumer

class SpectralFeatureExtractor:
    def __init__(self):
        self.api = get_streaming_api()
        
        # Setup consumer
        consumer = CallbackConsumer(self.extract_features)
        self.api.register_consumer(DataType.FFT_SPECTRUM, consumer)
    
    def extract_features(self, data):
        spectrum = data.data
        
        # Calculate spectral features
        features = self.calculate_spectral_features(
            spectrum.frequencies, 
            spectrum.magnitudes_db
        )
        
        print(f"Spectral Features:")
        for name, value in features.items():
            print(f"  {name}: {value:.2f}")
        print()
    
    def calculate_spectral_features(self, frequencies, magnitudes_db):
        """Calculate various spectral features."""
        # Convert to linear scale
        magnitudes_linear = 10.0 ** (magnitudes_db / 20.0)
        
        # Normalize
        total_energy = np.sum(magnitudes_linear)
        if total_energy == 0:
            return {}
        
        normalized_spectrum = magnitudes_linear / total_energy
        
        features = {}
        
        # Spectral centroid
        features['centroid_hz'] = np.sum(frequencies * normalized_spectrum)
        
        # Spectral spread
        centroid = features['centroid_hz']
        features['spread_hz'] = np.sqrt(np.sum(((frequencies - centroid) ** 2) * normalized_spectrum))
        
        # Spectral skewness
        features['skewness'] = np.sum(((frequencies - centroid) ** 3) * normalized_spectrum) / (features['spread_hz'] ** 3)
        
        # Spectral kurtosis
        features['kurtosis'] = np.sum(((frequencies - centroid) ** 4) * normalized_spectrum) / (features['spread_hz'] ** 4)
        
        # Spectral rolloff (95% of energy)
        cumulative_energy = np.cumsum(normalized_spectrum)
        rolloff_idx = np.where(cumulative_energy >= 0.95)[0]
        features['rolloff_hz'] = frequencies[rolloff_idx[0]] if len(rolloff_idx) > 0 else frequencies[-1]
        
        # Spectral flux (change from previous spectrum)
        if hasattr(self, 'previous_spectrum'):
            flux = np.sum((normalized_spectrum - self.previous_spectrum) ** 2)
            features['flux'] = flux
        
        self.previous_spectrum = normalized_spectrum.copy()
        
        return features
    
    def start(self):
        self.api.start_streaming()
        print("Spectral feature extraction started")
    
    def stop(self):
        self.api.stop_streaming()

# Usage
extractor = SpectralFeatureExtractor()
extractor.start()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    extractor.stop()
```

## External System Integration

### MQTT Integration

```python
import json
import paho.mqtt.client as mqtt
from friture.api import get_streaming_api, DataType, CallbackConsumer

class MQTTIntegration:
    def __init__(self, mqtt_broker='localhost', mqtt_port=1883):
        self.api = get_streaming_api()
        
        # Setup MQTT client
        self.mqtt_client = mqtt.Client()
        self.mqtt_client.connect(mqtt_broker, mqtt_port, 60)
        self.mqtt_client.loop_start()
        
        # Setup consumers
        self.setup_consumers()
    
    def setup_consumers(self):
        # Pitch data to MQTT
        pitch_consumer = CallbackConsumer(self.publish_pitch_data)
        self.api.register_consumer(DataType.PITCH_TRACKER, pitch_consumer)
        
        # Levels data to MQTT
        levels_consumer = CallbackConsumer(self.publish_levels_data)
        self.api.register_consumer(DataType.LEVELS, levels_consumer)
    
    def publish_pitch_data(self, data):
        pitch = data.data
        
        payload = {
            'frequency_hz': pitch.frequency_hz,
            'note': pitch.note_name,
            'confidence': pitch.confidence,
            'timestamp': data.metadata.timestamp
        }
        
        self.mqtt_client.publish('friture/pitch', json.dumps(payload))
    
    def publish_levels_data(self, data):
        levels = data.data
        
        payload = {
            'peak_levels_db': levels.peak_levels_db.tolist(),
            'rms_levels_db': levels.rms_levels_db.tolist(),
            'timestamp': data.metadata.timestamp
        }
        
        self.mqtt_client.publish('friture/levels', json.dumps(payload))
    
    def start(self):
        self.api.start_streaming()
        print("MQTT integration started")
    
    def stop(self):
        self.api.stop_streaming()
        self.mqtt_client.loop_stop()
        self.mqtt_client.disconnect()

# Usage
mqtt_integration = MQTTIntegration()
mqtt_integration.start()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    mqtt_integration.stop()
```

### Database Logging

```python
import sqlite3
import json
import threading
from friture.api import get_streaming_api, DataType, QueueConsumer

class DatabaseLogger:
    def __init__(self, db_path='friture_data.db'):
        self.api = get_streaming_api()
        self.db_path = db_path
        
        # Setup database
        self.setup_database()
        
        # Setup queue consumers for batch processing
        self.setup_consumers()
        
        # Start processing thread
        self.processing_active = True
        self.processing_thread = threading.Thread(target=self.process_queues, daemon=True)
        self.processing_thread.start()
    
    def setup_database(self):
        """Create database tables."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Pitch data table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pitch_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                stream_time REAL,
                widget_id TEXT,
                frequency_hz REAL,
                confidence REAL,
                note_name TEXT,
                amplitude_db REAL
            )
        ''')
        
        # Spectrum data table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS spectrum_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                stream_time REAL,
                widget_id TEXT,
                peak_frequency REAL,
                peak_magnitude REAL,
                fft_size INTEGER,
                weighting TEXT
            )
        ''')
        
        # Levels data table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS levels_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                stream_time REAL,
                widget_id TEXT,
                channel_index INTEGER,
                peak_level_db REAL,
                rms_level_db REAL
            )
        ''')
        
        conn.commit()
        conn.close()
        print(f"Database initialized: {self.db_path}")
    
    def setup_consumers(self):
        """Setup queue consumers for each data type."""
        self.pitch_queue = QueueConsumer(max_queue_size=1000)
        self.api.register_consumer(DataType.PITCH_TRACKER, self.pitch_queue)
        
        self.spectrum_queue = QueueConsumer(max_queue_size=500)
        self.api.register_consumer(DataType.FFT_SPECTRUM, self.spectrum_queue)
        
        self.levels_queue = QueueConsumer(max_queue_size=1000)
        self.api.register_consumer(DataType.LEVELS, self.levels_queue)
    
    def process_queues(self):
        """Process queued data and write to database."""
        while self.processing_active:
            try:
                # Process pitch data
                pitch_data = self.pitch_queue.get_data(timeout=0.1)
                if pitch_data:
                    self.store_pitch_data(pitch_data)
                
                # Process spectrum data
                spectrum_data = self.spectrum_queue.get_data(timeout=0.1)
                if spectrum_data:
                    self.store_spectrum_data(spectrum_data)
                
                # Process levels data
                levels_data = self.levels_queue.get_data(timeout=0.1)
                if levels_data:
                    self.store_levels_data(levels_data)
                
            except Exception as e:
                print(f"Error processing queues: {e}")
                time.sleep(1)
    
    def store_pitch_data(self, data):
        """Store pitch data in database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        pitch = data.data
        cursor.execute('''
            INSERT INTO pitch_data 
            (timestamp, stream_time, widget_id, frequency_hz, confidence, note_name, amplitude_db)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            data.metadata.timestamp,
            data.metadata.stream_time,
            data.metadata.widget_id,
            pitch.frequency_hz,
            pitch.confidence,
            pitch.note_name,
            pitch.amplitude_db
        ))
        
        conn.commit()
        conn.close()
    
    def store_spectrum_data(self, data):
        """Store spectrum data in database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        spectrum = data.data
        cursor.execute('''
            INSERT INTO spectrum_data 
            (timestamp, stream_time, widget_id, peak_frequency, peak_magnitude, fft_size, weighting)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            data.metadata.timestamp,
            data.metadata.stream_time,
            data.metadata.widget_id,
            spectrum.peak_frequency,
            spectrum.peak_magnitude,
            spectrum.fft_size,
            spectrum.weighting
        ))
        
        conn.commit()
        conn.close()
    
    def store_levels_data(self, data):
        """Store levels data in database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        levels = data.data
        
        # Store each channel separately
        for i, (peak, rms) in enumerate(zip(levels.peak_levels_db, levels.rms_levels_db)):
            cursor.execute('''
                INSERT INTO levels_data 
                (timestamp, stream_time, widget_id, channel_index, peak_level_db, rms_level_db)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                data.metadata.timestamp,
                data.metadata.stream_time,
                data.metadata.widget_id,
                i,
                peak,
                rms
            ))
        
        conn.commit()
        conn.close()
    
    def start(self):
        self.api.start_streaming()
        print("Database logging started")
    
    def stop(self):
        self.processing_active = False
        self.api.stop_streaming()
        print("Database logging stopped")

# Usage
logger = DatabaseLogger()
logger.start()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    logger.stop()
```

## Performance Optimization

### Adaptive Rate Control

```python
import psutil
from friture.api import get_streaming_api, DataType

class AdaptiveRateController:
    def __init__(self):
        self.api = get_streaming_api()
        self.base_rates = {
            DataType.PITCH_TRACKER: 30.0,
            DataType.FFT_SPECTRUM: 20.0,
            DataType.LEVELS: 50.0
        }
        self.current_rates = self.base_rates.copy()
        
        # Performance thresholds
        self.cpu_threshold = 75.0
        self.memory_threshold_mb = 400.0
        
        # Start monitoring
        import threading
        self.monitoring_active = True
        monitor_thread = threading.Thread(target=self.monitor_performance, daemon=True)
        monitor_thread.start()
    
    def monitor_performance(self):
        """Monitor system performance and adjust rates."""
        while self.monitoring_active:
            try:
                # Get system metrics
                cpu_percent = psutil.cpu_percent(interval=1.0)
                memory_mb = psutil.Process().memory_info().rss / (1024 * 1024)
                
                # Calculate adjustment factor
                adjustment_factor = 1.0
                
                if cpu_percent > self.cpu_threshold:
                    adjustment_factor *= 0.8  # Reduce by 20%
                elif cpu_percent < self.cpu_threshold * 0.5:
                    adjustment_factor *= 1.1  # Increase by 10%
                
                if memory_mb > self.memory_threshold_mb:
                    adjustment_factor *= 0.7  # Reduce by 30%
                
                # Apply adjustments
                if adjustment_factor != 1.0:
                    self.adjust_rates(adjustment_factor)
                    print(f"Rate adjustment: {adjustment_factor:.2f} "
                          f"(CPU: {cpu_percent:.1f}%, Memory: {memory_mb:.1f}MB)")
                
            except Exception as e:
                print(f"Error in performance monitoring: {e}")
                time.sleep(1)
    
    def adjust_rates(self, factor):
        """Adjust all rate limits by a factor."""
        for data_type, base_rate in self.base_rates.items():
            new_rate = max(1.0, base_rate * factor)  # Minimum 1 Hz
            self.current_rates[data_type] = new_rate
            self.api.set_rate_limit(data_type, new_rate)
    
    def start(self):
        # Set initial rate limits
        for data_type, rate in self.base_rates.items():
            self.api.set_rate_limit(data_type, rate)
        
        print("Adaptive rate controller started")
    
    def stop(self):
        self.monitoring_active = False

# Usage
controller = AdaptiveRateController()
controller.start()

# Your main application code here
api = get_streaming_api()
# ... setup consumers ...
api.start_streaming()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    controller.stop()
    api.stop_streaming()
```

## Custom Implementations

### Custom Data Producer

```python
from friture.api.producers import DataProducer
from friture.api.data_types import DataType

class CustomAnalysisProducer(DataProducer):
    """Custom producer for specialized analysis."""
    
    def __init__(self, widget, widget_id, parent=None):
        super().__init__(widget, widget_id, parent)
        self.analysis_buffer = []
    
    def start(self):
        if self._is_active:
            return
        
        self._is_active = True
        
        # Connect to widget's data updates
        if hasattr(self.widget, 'audiobuffer'):
            self.widget.audiobuffer.new_data_available.connect(self._on_new_data)
        
        self.started.emit()
    
    def stop(self):
        if not self._is_active:
            return
        
        self._is_active = False
        
        if hasattr(self.widget, 'audiobuffer'):
            try:
                self.widget.audiobuffer.new_data_available.disconnect(self._on_new_data)
            except TypeError:
                pass
        
        self.stopped.emit()
    
    def _on_new_data(self, floatdata):
        """Process new audio data."""
        if not self._is_active:
            return
        
        # Perform custom analysis
        analysis_result = self.perform_custom_analysis(floatdata)
        
        if analysis_result:
            self._emit_data(analysis_result)
    
    def perform_custom_analysis(self, floatdata):
        """Implement your custom analysis here."""
        # Example: Zero crossing rate
        if floatdata.shape[0] > 0:
            signal = floatdata[0, :]  # First channel
            
            # Calculate zero crossing rate
            zero_crossings = np.sum(np.diff(np.sign(signal)) != 0)
            zcr = zero_crossings / len(signal)
            
            # Calculate spectral centroid using simple method
            fft = np.fft.rfft(signal)
            magnitude = np.abs(fft)
            freqs = np.fft.rfftfreq(len(signal), 1/48000)
            
            if np.sum(magnitude) > 0:
                centroid = np.sum(freqs * magnitude) / np.sum(magnitude)
            else:
                centroid = 0.0
            
            return {
                'zero_crossing_rate': zcr,
                'spectral_centroid': centroid,
                'signal_energy': np.sum(signal ** 2),
                'timestamp': time.time()
            }
        
        return None
    
    def extract_data(self):
        """Required by base class."""
        return None
    
    def get_data_type(self):
        """Required by base class."""
        return DataType.CUSTOM_ANALYSIS  # Would need to add this to enum

# Usage
# custom_producer = CustomAnalysisProducer(widget, "custom_widget")
# api.register_producer(DataType.CUSTOM_ANALYSIS, custom_producer)
```

### Custom Network Protocol

```python
import socket
import threading
from friture.api.protocols import StreamingProtocol

class CustomTCPProtocol(StreamingProtocol):
    """Custom TCP protocol with binary format."""
    
    def __init__(self, host='localhost', port=8769, parent=None):
        super().__init__(host, port, parent)
        self._server_socket = None
        self._server_thread = None
    
    def start(self):
        if self._is_running:
            return
        
        self._is_running = True
        
        try:
            self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_socket.bind((self.host, self.port))
            self._server_socket.listen(5)
            
            self._server_thread = threading.Thread(target=self._accept_clients, daemon=True)
            self._server_thread.start()
            
            self.logger.info(f"Custom TCP server started on {self.host}:{self.port}")
            
        except Exception as e:
            self.logger.error(f"Failed to start custom TCP server: {e}")
            self.error_occurred.emit(str(e))
    
    def stop(self):
        if not self._is_running:
            return
        
        self._is_running = False
        
        if self._server_socket:
            self._server_socket.close()
        
        if self._server_thread:
            self._server_thread.join(timeout=5.0)
    
    def _accept_clients(self):
        """Accept client connections."""
        while self._is_running:
            try:
                client_socket, address = self._server_socket.accept()
                client_id = f"{address[0]}:{address[1]}"
                
                self._clients[client_id] = client_socket
                self.client_connected.emit(client_id)
                
                # Start client handler
                client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_socket, client_id),
                    daemon=True
                )
                client_thread.start()
                
            except Exception as e:
                if self._is_running:
                    self.logger.error(f"Error accepting client: {e}")
    
    def _handle_client(self, client_socket, client_id):
        """Handle client connection."""
        try:
            while self._is_running:
                # Keep connection alive
                time.sleep(1.0)
        except Exception as e:
            self.logger.error(f"Client handler error: {e}")
        finally:
            client_socket.close()
            if client_id in self._clients:
                del self._clients[client_id]
            self.client_disconnected.emit(client_id)
    
    def send_data(self, data, client_id=None):
        """Send data using custom binary format."""
        if not self._is_running or not self._clients:
            return
        
        try:
            # Custom binary serialization
            binary_data = self.serialize_to_binary(data)
            
            # Send to clients
            clients = [self._clients[client_id]] if client_id else list(self._clients.values())
            
            for client_socket in clients:
                try:
                    # Send length prefix + data
                    length_bytes = len(binary_data).to_bytes(4, byteorder='big')
                    client_socket.sendall(length_bytes + binary_data)
                except Exception as e:
                    self.logger.error(f"Error sending to client: {e}")
        
        except Exception as e:
            self.logger.error(f"Error in custom protocol send: {e}")
    
    def serialize_to_binary(self, data):
        """Serialize data to custom binary format."""
        # Implement your custom binary serialization here
        # This is just a placeholder
        import pickle
        return pickle.dumps(data)

# Usage
custom_protocol = CustomTCPProtocol()
api.add_protocol(custom_protocol)
```

These examples demonstrate the flexibility and power of the Friture Streaming API. The API can be adapted for virtually any real-time audio analysis application, from simple monitoring to complex multi-system integrations.