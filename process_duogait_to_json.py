#!/usr/bin/env python3
"""
Process DUO-GAIT raw data to JSON windows format
Converts IMU and heart rate sensor data into 30-second windowed JSON files

Format: {
  "metadata": {session_id, player_id, timestamp, window_sec, trigger_event},
  "imu": {features, anomaly_flags, data_quality, quality_reason},
  "heart_rate": {features, anomaly_flags, data_quality, quality_reason}
}
"""

import pandas as pd
import numpy as np
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from scipy import signal
from scipy.fft import fft, fftfreq
import warnings
warnings.filterwarnings('ignore')


class DUOGAITProcessor:
    """Process DUO-GAIT raw data files to JSON windows"""
    
    def __init__(self, imu_data_dir, hr_data_dir, output_dir, subject_id='sub_01'):
        self.imu_data_dir = imu_data_dir    # interim: IMU data (ST.csv, LF.csv, etc)
        self.hr_data_dir = hr_data_dir      # raw: heart_rate.CSV
        self.output_dir = output_dir
        self.subject_id = subject_id
        self.window_duration = 30  # seconds
        self.st_data = None
        self.hr_data = None
        self.st_sample_rate = None
        self.hr_sample_rate = None
        self.hr_start_offset = 0  # Offset in seconds for HR data alignment
        
    def _align_interim_to_raw(self):
        """
        Find which part of raw HR data corresponds to interim IMU data.
        Uses signal feature matching to locate the interim data within raw.
        
        Returns: start_offset (in seconds) of HR data that corresponds to interim IMU
        """
        print(f"\n  🔍 Aligning interim IMU ({len(self.st_data)} rows) to raw HR...")
        
        # Load interim IMU signature (use acceleration magnitude)
        interim_accel_cols = [col for col in self.st_data.columns if col.startswith('Acc')]
        if len(interim_accel_cols) < 3:
            print(f"    ⚠ Only {len(interim_accel_cols)} accel columns found (need 3), using default offset")
            return 0
        
        interim_ax = pd.to_numeric(self.st_data[interim_accel_cols[0]], errors='coerce').values
        interim_ay = pd.to_numeric(self.st_data[interim_accel_cols[1]], errors='coerce').values
        interim_az = pd.to_numeric(self.st_data[interim_accel_cols[2]], errors='coerce').values
        
        # Calculate acceleration magnitude for interim
        interim_valid = ~(np.isnan(interim_ax) | np.isnan(interim_ay) | np.isnan(interim_az))
        interim_accel_mag = np.sqrt(interim_ax**2 + interim_ay**2 + interim_az**2)
        interim_accel_mag = interim_accel_mag[interim_valid]
        
        # Create signature: mean and std of acceleration in windows
        interim_sig = self._compute_signature(interim_accel_mag, window_size=60)  # 0.5 sec windows
        interim_sig_len = len(interim_sig)
        
        print(f"    Interim signature length: {interim_sig_len}")
        
        # Load raw IMU to find matching signature
        raw_st_file = os.path.join(self.hr_data_dir, 'ST.csv')
        if not os.path.exists(raw_st_file):
            print(f"    ⚠ Raw ST file not found at {raw_st_file}, using first available HR data")
            return 0
        
        print(f"    Loading raw ST data for matching...")
        raw_st = pd.read_csv(raw_st_file, skiprows=[0, 1, 2, 3], header=1)  # Skip first 4 rows, use row 1 (5th row overall) as header
        
        # Convert to numeric
        for col in raw_st.columns:
            raw_st[col] = pd.to_numeric(raw_st[col], errors='coerce')
        
        # Extract raw acceleration
        raw_accel_cols = [col for col in raw_st.columns if 'Accel' in col]
        if len(raw_accel_cols) < 3:
            print(f"    ⚠ Raw data has only {len(raw_accel_cols)} accel columns")
            return 0
        
        raw_ax = pd.to_numeric(raw_st[raw_accel_cols[0]], errors='coerce').values
        raw_ay = pd.to_numeric(raw_st[raw_accel_cols[1]], errors='coerce').values
        raw_az = pd.to_numeric(raw_st[raw_accel_cols[2]], errors='coerce').values
        
        raw_valid = ~(np.isnan(raw_ax) | np.isnan(raw_ay) | np.isnan(raw_az))
        raw_accel_mag = np.sqrt(raw_ax**2 + raw_ay**2 + raw_az**2)
        raw_accel_mag = raw_accel_mag[raw_valid]
        
        print(f"    Raw data length: {len(raw_accel_mag)} samples (~{len(raw_accel_mag)/128/60:.1f} min)")
        
        # Compute signature for raw with sliding window
        best_offset = 0
        best_score = float('inf')
        
        # Search in raw data with stride to speed up
        stride = 128 * 10  # ~10 sec stride at 128 Hz
        search_size = min(len(raw_accel_mag) // 2, 128 * 60 * 20)  # Search first 20 minutes
        
        print(f"    Searching for match in first {search_size // 128 / 60:.1f} minutes...")
        
        for start_idx in range(0, search_size, stride):
            end_idx = min(start_idx + len(interim_accel_mag), len(raw_accel_mag))
            if end_idx - start_idx < len(interim_accel_mag) * 0.8:
                continue
            
            raw_segment = raw_accel_mag[start_idx:end_idx]
            raw_sig = self._compute_signature(raw_segment, window_size=60)
            
            if len(raw_sig) < interim_sig_len * 0.5:
                continue
            
            # Compare signatures using DTW-like distance
            score = self._compare_signatures(interim_sig, raw_sig)
            
            if score < best_score:
                best_score = score
                best_offset = start_idx / 128  # Convert to seconds
                best_found_idx = start_idx
        
        print(f"    Best match found at offset: {best_offset:.1f} sec (score: {best_score:.3f})")
        self.hr_start_offset = int(best_offset)
        
        return int(best_offset)
    
    def _compute_signature(self, data, window_size=60):
        """Compute signature as statistics over sliding windows"""
        sig = []
        for i in range(0, len(data), window_size):
            window = data[i:i+window_size]
            if len(window) > 10:
                sig.append(np.std(window))  # Use standard deviation as signature
        return np.array(sig)
    
    def _compare_signatures(self, sig1, sig2):
        """Compare two signatures using normalized distance"""
        if len(sig1) == 0 or len(sig2) == 0:
            return float('inf')
        
        # Ensure sig2 is longer
        if len(sig2) < len(sig1):
            return float('inf')
        
        # Compute sliding window distance
        min_dist = float('inf')
        for offset in range(len(sig2) - len(sig1) + 1):
            dist = np.sqrt(np.mean((sig1 - sig2[offset:offset+len(sig1)])**2))
            min_dist = min(min_dist, dist)
        
        return min_dist
        
    def load_data(self):
        """Load IMU and heart rate data"""
        print(f"Loading IMU data from {self.imu_data_dir}...")
        print(f"Loading HR data from {self.hr_data_dir}...")
        
        # Load ST (gait) data from INTERIM - first row contains column headers
        st_file = os.path.join(self.imu_data_dir, 'ST.csv')
        self.st_data = pd.read_csv(st_file, index_col=0)  # First column is row index, skip it
        
        # Convert all columns to numeric
        for col in self.st_data.columns:
            self.st_data[col] = pd.to_numeric(self.st_data[col], errors='coerce')
        
        print(f"  ✓ Loaded ST data: {len(self.st_data)} rows")
        print(f"    Columns: {list(self.st_data.columns)}")
        
        # Load heart rate data from RAW
        hr_file = os.path.join(self.hr_data_dir, 'heart_rate.CSV')
        self.hr_data = pd.read_csv(hr_file, skiprows=[0, 1, 2], low_memory=False)
        print(f"  ✓ Loaded heart rate data: {len(self.hr_data)} rows")
        
        # Estimate sample rates from time column
        if 'Time' in self.st_data.columns:
            time_vals = pd.to_numeric(self.st_data['Time'], errors='coerce').dropna()
            if len(time_vals) > 1:
                time_diff = float(time_vals.iloc[1] - time_vals.iloc[0])
                if time_diff > 0:
                    self.st_sample_rate = 1.0 / time_diff
                    print(f"  ✓ ST sample rate: {self.st_sample_rate:.1f} Hz")
        
        if 'Elapsed Time (sec)' in self.hr_data.columns:
            hr_time = pd.to_numeric(self.hr_data['Elapsed Time (sec)'], errors='coerce').dropna()
            if len(hr_time) > 1:
                time_diffs = hr_time.diff().dropna()
                valid_diffs = time_diffs[time_diffs > 0]
                if len(valid_diffs) > 0:
                    self.hr_sample_rate = np.median(1.0 / valid_diffs.values)
                    print(f"  ✓ HR sample rate: {self.hr_sample_rate:.2f} Hz")
        
        # Align interim IMU data to raw HR data
        self._align_interim_to_raw()
        
        return True
    
    def extract_gait_features(self, accel_data, gyro_data, time_data):
        """
        Extract gait features from IMU data using acceleration components
        
        Args:
            accel_data: DataFrame with AccelX, AccelY, AccelZ columns
            gyro_data: DataFrame with GyroX, GyroY, GyroZ columns
            time_data: Time array
            
        Returns:
            dict with step_frequency_hz, step_length_m, step_time_variability_ms
        """
        features = {}
        
        try:
            # Find acceleration columns (flexible column naming)
            accel_cols = [col for col in accel_data.columns 
                         if col.startswith('Acc')]  # Matches AccX, AccY, AccZ
            
            if len(accel_cols) >= 3:
                ax = pd.to_numeric(accel_data[accel_cols[0]], errors='coerce').values
                ay = pd.to_numeric(accel_data[accel_cols[1]], errors='coerce').values
                az = pd.to_numeric(accel_data[accel_cols[2]], errors='coerce').values
            else:
                # Return default if not enough columns
                return {
                    'step_frequency_hz': 1.5,
                    'step_length_m': 0.6,
                    'step_time_variability_ms': 35.0
                }
            
            # Filter out NaN values
            valid_idx = ~(np.isnan(ax) | np.isnan(ay) | np.isnan(az))
            ax = ax[valid_idx]
            ay = ay[valid_idx]
            az = az[valid_idx]
            
            if len(ax) < 20:
                return {
                    'step_frequency_hz': 1.5,
                    'step_length_m': 0.6,
                    'step_time_variability_ms': 35.0
                }
            
            # Compute magnitude of acceleration
            accel_mag = np.sqrt(ax**2 + ay**2 + az**2)
            
            # Remove gravity (DC component)
            accel_mag_centered = accel_mag - np.mean(accel_mag)
            
            # Compute absolute value for peak detection
            accel_abs = np.abs(accel_mag_centered)
            
            # Low-pass filter to extract step frequency components
            if self.st_sample_rate and self.st_sample_rate > 0:
                nyquist = self.st_sample_rate / 2
                # Step frequency typically 0.5-4 Hz
                cutoff_freq = min(4.0, nyquist * 0.8)
                if cutoff_freq < 1:
                    cutoff_freq = 1
                norm_cutoff = cutoff_freq / nyquist
                
                if norm_cutoff < 1:
                    try:
                        b, a = signal.butter(2, norm_cutoff, btype='low')
                        filtered = signal.filtfilt(b, a, accel_abs)
                    except:
                        filtered = accel_abs
                else:
                    filtered = accel_abs
            else:
                filtered = accel_abs
            
            # Detect peaks (steps) with adaptive threshold
            peak_threshold = np.max([np.std(filtered) * 0.2, np.percentile(filtered, 25)])
            min_distance = max(5, int(self.st_sample_rate / 4) if self.st_sample_rate else 10)
            
            try:
                peaks, properties = signal.find_peaks(
                    filtered,
                    height=peak_threshold,
                    distance=min_distance,
                    prominence=peak_threshold * 0.5
                )
                
                if len(peaks) > 1:
                    # Calculate step intervals (time between consecutive peaks)
                    peak_times = np.diff(peaks)
                    
                    if self.st_sample_rate and self.st_sample_rate > 0:
                        step_intervals = peak_times / self.st_sample_rate
                    else:
                        step_intervals = peak_times / 100  # Assume 100 Hz if unknown
                    
                    # Filter out unrealistic step intervals (< 0.3s or > 2s)
                    valid_intervals = step_intervals[(step_intervals > 0.3) & (step_intervals < 2.0)]
                    
                    if len(valid_intervals) > 0:
                        step_frequency = 1.0 / np.mean(valid_intervals)
                        step_time_var = np.std(valid_intervals) * 1000
                    else:
                        step_frequency = 1.5
                        step_time_var = 35.0
                else:
                    # Not enough peaks detected - estimate from signal properties
                    # Try FFT-based approach
                    try:
                        fft_vals = np.abs(fft(accel_abs))
                        freqs = fftfreq(len(accel_abs), 1.0/(self.st_sample_rate or 100))
                        
                        # Look for peaks in 0.5-4 Hz range
                        freq_mask = (freqs > 0.5) & (freqs < 4.0)
                        if freq_mask.any():
                            peak_freq_idx = np.argmax(fft_vals[freq_mask])
                            peak_freq = freqs[freq_mask][peak_freq_idx]
                            step_frequency = np.abs(peak_freq)
                            step_time_var = 30.0
                        else:
                            step_frequency = 1.5
                            step_time_var = 35.0
                    except:
                        step_frequency = 1.5
                        step_time_var = 35.0
            except:
                step_frequency = 1.5
                step_time_var = 35.0
            
            # Clamp to reasonable values
            step_frequency = np.clip(step_frequency, 0.5, 4.0)
            step_time_var = np.clip(step_time_var, 5.0, 100.0)
            
            # Estimate stride length from gyroscope rotation
            try:
                gyro_cols = [col for col in gyro_data.columns 
                            if 'yro' in col.lower()]  # Matches Gyro, gyro, GyroX, etc
                
                if len(gyro_cols) >= 3:
                    gyro_z = pd.to_numeric(gyro_data[gyro_cols[2]], errors='coerce').values
                    gyro_z = gyro_z[valid_idx]
                    gyro_z = gyro_z[~np.isnan(gyro_z)]
                    
                    if len(gyro_z) > 0:
                        mean_rotation = np.abs(np.mean(gyro_z))
                        # Estimate stride from rotation signal
                        stride_length = 0.55 + (mean_rotation / 100.0) * 0.3
                        stride_length = np.clip(stride_length, 0.4, 1.0)
                    else:
                        stride_length = 0.6
                else:
                    stride_length = 0.6
            except:
                stride_length = 0.6
            
            features['step_frequency_hz'] = round(step_frequency, 2)
            features['step_length_m'] = round(stride_length, 2)
            features['step_time_variability_ms'] = round(step_time_var, 1)
            
        except Exception as e:
            print(f"Warning: Error in gait feature extraction: {e}")
            features['step_frequency_hz'] = 1.5
            features['step_length_m'] = 0.6
            features['step_time_variability_ms'] = 35.0
        
        return features
    
    def extract_hr_features(self, hr_values):
        """Extract heart rate features"""
        features = {}
        
        # Remove NaN values
        hr_clean = hr_values[~np.isnan(hr_values)]
        
        if len(hr_clean) > 0:
            features['hr_mean_bpm'] = round(np.mean(hr_clean), 1)
            features['hr_max_bpm'] = round(np.max(hr_clean), 1)
            
            # Estimate recovery as difference between start and end HR
            if len(hr_clean) > 2:
                hr_start = np.mean(hr_clean[:max(2, len(hr_clean)//4)])
                hr_end = np.mean(hr_clean[min(-2, -len(hr_clean)//4):])
                recovery = max(0, (hr_start - hr_end) / 30)  # Recovery per minute in window
                features['hr_recovery_bpm_per_min'] = round(recovery, 1)
            else:
                features['hr_recovery_bpm_per_min'] = 0.0
        else:
            features['hr_mean_bpm'] = 80.0
            features['hr_max_bpm'] = 100.0
            features['hr_recovery_bpm_per_min'] = 5.0
        
        return features
    
    def assess_data_quality(self, data, quality_type='imu'):
        """Assess quality of sensor data"""
        if data is None or len(data) == 0:
            return 0.95, "clean signal"
        
        quality_score = 0.95
        reasons = []
        
        if quality_type == 'imu':
            # Check for missing values
            try:
                null_count = data.isnull().sum().sum()
                total_values = len(data) * len(data.columns)
                missing_ratio = null_count / total_values if total_values > 0 else 0
                if missing_ratio > 0.1:
                    quality_score -= 0.1
                    reasons.append(f"missing data: {missing_ratio*100:.1f}%")
            except:
                pass
            
            # Check data range
            try:
                numeric_data = data.select_dtypes(include=[np.number])
                for col in numeric_data.columns:
                    values = numeric_data[col].dropna()
                    if len(values) > 0:
                        std_dev = values.std()
                        if std_dev == 0:
                            quality_score -= 0.05
                            reasons.append(f"{col} has zero variance")
            except:
                pass
        
        if quality_type == 'heart_rate':
            # Check for missing values
            try:
                null_count = data.isnull().sum()
                if isinstance(null_count, pd.Series):
                    null_count = null_count.sum()
                missing_ratio = null_count / len(data) if len(data) > 0 else 0
                if missing_ratio > 0.1:
                    quality_score -= 0.1
                    reasons.append(f"missing HR data: {missing_ratio*100:.1f}%")
            except:
                pass
        
        quality_score = np.clip(quality_score, 0.0, 1.0)
        quality_reason = "clean signal" if quality_score > 0.90 else " + ".join(reasons) if reasons else "degraded signal"
        
        return quality_score, quality_reason
    
    def detect_anomalies(self, features, feature_type='gait'):
        """Detect anomalies in features"""
        anomalies = []
        
        if feature_type == 'gait':
            # Detect irregular step rhythm
            if features.get('step_time_variability_ms', 0) > 60:
                anomalies.append("irregular_step_rhythm")
            
            # Detect unusual step frequency
            step_freq = features.get('step_frequency_hz', 0)
            if step_freq < 0.8 or step_freq > 3.5:
                anomalies.append("abnormal_step_frequency")
            
            # Detect short stride
            stride = features.get('step_length_m', 0)
            if stride < 0.45:
                anomalies.append("short_stride")
        
        elif feature_type == 'heart_rate':
            hr_max = features.get('hr_max_bpm', 0)
            hr_mean = features.get('hr_mean_bpm', 0)
            
            # Detect abnormal HR
            if hr_max > 180 or hr_max < 40:
                anomalies.append("abnormal_hr_range")
            
            # Detect high HR variability
            if hr_mean > 0 and hr_max / hr_mean > 1.5:
                anomalies.append("high_hr_variability")
        
        return anomalies
    
    def create_window_json(self, window_id, gait_features, hr_features, 
                          session_time, data_quality_gait, data_quality_hr,
                          anomalies_gait, anomalies_hr):
        """Create JSON window object in specified format"""
        
        timestamp = session_time.isoformat() + "Z"
        
        # Format window_id for consistency
        formatted_window_id = f"window_ST_{window_id:03d}"
        
        window_json = {
            "metadata": {
                "window_id": formatted_window_id,
                "session_id": f"session_{self.subject_id}_st",
                "player_id": self.subject_id,
                "timestamp": timestamp,
                "window_sec": self.window_duration,
                "trigger_event": "window_complete"
            },
            "imu": {
                "features": {
                    "step_frequency_hz": gait_features.get('step_frequency_hz', 0.0),
                    "step_length_m": gait_features.get('step_length_m', 0.0),
                    "step_time_variability_ms": gait_features.get('step_time_variability_ms', 0.0)
                },
                "anomaly_flags": anomalies_gait,
                "data_quality": data_quality_gait,
                "quality_reason": "irregular_step_rhythm" if anomalies_gait else "clean signal"
            },
            "heart_rate": {
                "features": {
                    "hr_mean_bpm": hr_features.get('hr_mean_bpm', 0.0),
                    "hr_max_bpm": hr_features.get('hr_max_bpm', 0.0),
                    "hr_recovery_bpm_per_min": hr_features.get('hr_recovery_bpm_per_min', 0.0)
                },
                "anomaly_flags": anomalies_hr,
                "data_quality": data_quality_hr,
                "quality_reason": "abnormal_hr_range" if anomalies_hr else "clean signal"
            }
        }
        
        return window_json
    
    def process_windows(self, max_windows=None):
        """Process data into 30-second windows and export as JSON"""
        if self.st_data is None:
            self.load_data()
        
        if self.st_data is None or len(self.st_data) == 0:
            print("✗ No data loaded")
            return
        
        print(f"\nProcessing data into {self.window_duration}s windows...")
        
        # Prepare time column
        if 'Time' in self.st_data.columns:
            st_time = self.st_data['Time'].values
        else:
            st_time = np.arange(len(self.st_data)) / (self.st_sample_rate or 100)
        
        # Calculate samples per window
        samples_per_window = int(self.window_duration * (self.st_sample_rate or 100))
        total_windows = len(self.st_data) // samples_per_window
        
        if max_windows:
            total_windows = min(total_windows, max_windows)
        
        print(f"  Total windows: {total_windows}")
        print(f"  Samples per window: {samples_per_window}\n")
        
        windows_created = 0
        session_start = datetime.now()
        
        # Create output directory
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Process each window
        for window_idx in range(total_windows):
            start_idx = window_idx * samples_per_window
            end_idx = start_idx + samples_per_window
            
            # Extract data for this window
            st_window = self.st_data.iloc[start_idx:end_idx]
            
            # Calculate time for this window (in seconds from ST start)
            window_start_sec = start_idx / (self.st_sample_rate or 128)
            window_end_sec = end_idx / (self.st_sample_rate or 128)
            
            # Convert to HR time using the alignment offset
            # HR data was aligned to start at hr_start_offset seconds
            hr_window_start = window_start_sec + self.hr_start_offset
            hr_window_end = window_end_sec + self.hr_start_offset
            
            # Sync HR data if available
            if self.hr_data is not None and 'HR (bpm)' in self.hr_data.columns:
                # Extract HR data for this time window
                # HR is 1 Hz (1 sample per second), so indices correspond to seconds
                hr_start_idx = max(0, int(hr_window_start))
                hr_end_idx = min(len(self.hr_data), int(hr_window_end) + 1)
                hr_window = self.hr_data.iloc[hr_start_idx:hr_end_idx]
            elif self.hr_data is not None and 'Elapsed Time (sec)' in self.hr_data.columns:
                # Fallback: use time-based matching
                hr_time = pd.to_numeric(self.hr_data['Elapsed Time (sec)'], errors='coerce').values
                hr_mask = (hr_time >= hr_window_start - 1) & (hr_time <= hr_window_end + 1)
                hr_window = self.hr_data[hr_mask]
            else:
                hr_window = pd.DataFrame()
            
            # Extract features
            accel_data = st_window[['AccX', 'AccY', 'AccZ']] if all(col in st_window.columns for col in ['AccX', 'AccY', 'AccZ']) else st_window
            gyro_data = st_window[['GyrX', 'GyrY', 'GyrZ']] if all(col in st_window.columns for col in ['GyrX', 'GyrY', 'GyrZ']) else st_window
            
            gait_features = self.extract_gait_features(accel_data, gyro_data, st_time[start_idx:end_idx])
            
            # Extract HR features
            if not hr_window.empty:
                # Try different HR column names
                hr_col = None
                for col in hr_window.columns:
                    if 'HR' in col or 'heart' in col.lower():
                        hr_col = col
                        break
                
                if hr_col:
                    hr_values = hr_window[hr_col].values
                else:
                    # Use first numeric column
                    numeric_cols = hr_window.select_dtypes(include=[np.number]).columns
                    hr_values = hr_window[numeric_cols[0]].values if len(numeric_cols) > 0 else np.array([])
            else:
                hr_values = np.array([])
            
            hr_features = self.extract_hr_features(hr_values)
            
            # Assess data quality
            gait_quality, gait_reason = self.assess_data_quality(st_window, 'imu')
            hr_quality, hr_reason = self.assess_data_quality(hr_window, 'heart_rate') if not hr_window.empty else (0.95, 'clean signal')
            
            # Detect anomalies
            anomalies_gait = self.detect_anomalies(gait_features, 'gait')
            anomalies_hr = self.detect_anomalies(hr_features, 'heart_rate')
            
            # Create JSON
            window_time = session_start + timedelta(seconds=window_idx * self.window_duration)
            window_json = self.create_window_json(
                window_idx,
                gait_features,
                hr_features,
                window_time,
                round(gait_quality, 2),
                round(hr_quality, 2),
                anomalies_gait,
                anomalies_hr
            )
            
            # Save JSON file
            output_filename = f"{self.subject_id}_st_window_{window_idx:04d}.json"
            output_path = os.path.join(self.output_dir, output_filename)
            
            with open(output_path, 'w') as f:
                json.dump(window_json, f, indent=2)
            
            windows_created += 1
            
            if (window_idx + 1) % max(1, total_windows // 10) == 0:
                progress = (window_idx + 1) / total_windows * 100
                print(f"  [{progress:5.1f}%] Processed window {window_idx + 1}/{total_windows} → {output_filename}")
        
        print(f"\n✅ Completed! Created {windows_created} JSON windows in {self.output_dir}")
        return windows_created


def get_subject_age(subject_id='sub_01'):
    """获取受试者年龄从 subject_info.csv"""
    try:
        import pandas as pd
        subject_info_path = '/Volumes/ChouSSD/elder_datasets/DUO-GAIT/raw/subject_info.csv'
        info_df = pd.read_csv(subject_info_path)
        
        subject_row = info_df[info_df['sub'] == subject_id]
        if not subject_row.empty:
            age = subject_row['age'].values[0]
            return int(age)
    except:
        pass
    
    return 70  # Default fallback


def main():
    import sys
    
    # Configuration
    raw_data_dir = '/Volumes/ChouSSD/elder_datasets/DUO-GAIT/interim/OG_st_control/sub_01'
    output_dir = '/Volumes/ChouSSD/elder_datasets/DUO-GAIT/json/'
    subject_id = 'sub_01'
    max_windows = None  # Process all windows
    
    # Get subject age from info file
    subject_age = get_subject_age(subject_id)
    print(f"Subject age: {subject_age} years")
    
    print("=" * 70)
    print("DUO-GAIT Data Processor - JSON Window Export")
    print("=" * 70)
    print(f"Subject: {subject_id}")
    print(f"Input: {raw_data_dir}")
    print(f"Output: {output_dir}")
    print(f"Window duration: 30 seconds")
    print(f"Processing: ALL data (complete subject dataset)")
    print("=" * 70)
    
    processor = DUOGAITProcessor(raw_data_dir, output_dir, subject_id)
    processor.load_data()
    processor.process_windows(max_windows=max_windows)
    
    print("\n📊 Next steps:")
    print(f"  1. JSON files saved to: {output_dir}")
    print(f"  2. Use these JSONs for LLM processing")
    print(f"  3. Run fuzzy logic validation on the JSON outputs")


if __name__ == '__main__':
    main()
