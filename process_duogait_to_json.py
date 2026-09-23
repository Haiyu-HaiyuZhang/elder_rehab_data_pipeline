#!/usr/bin/env python3
"""
Process DUO-GAIT raw data to JSON windows format
Converts IMU and heart rate sensor data into 30-second windowed JSON files

Format: {
  "sample_id": "001",
  "subject_id": "S01",
  "player_age": 72,
  "dataset_source": "DUO-GAIT",
  "input_features": {
    "step_frequency_hz": 1.82,
    "step_length_m": 0.58,
    "step_time_variability_ms": 22.0,
    "mean_hr_bpm": 88,
    "max_hr_bpm": 102
  },
  "warmup_baseline": {
    "warmup_cadence_hz": 1.85,
    "warmup_stride_m": 0.60,
    "warmup_var_ms": 18.0
  },
  "rpe": null,
  "imu_quality": 0.95,
  "hr_quality": 0.95,
  "ground_truth": {
    "exercise_load": "moderate",
    "fatigue_level": "none",
    "movement_quality": "good",
    "composite_state": "normal"
  }
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

# Import fuzzy classifier + DUO 足部/验证辅助（仓库内相对路径，避免硬编码机器目录）
import sys
_PIPELINE_ROOT = Path(__file__).resolve().parent / "signal_processing_pipeline"
sys.path.insert(0, str(_PIPELINE_ROOT))
import config as _proc_config
from duogait_metrics import stride_from_cadence_height_and_feet
from fuzzy_classifier import FuzzyExerciseClassifier


def _metric_fallbacks_enabled() -> bool:
    return bool(getattr(_proc_config, "METRIC_ALLOW_DEFAULT_FALLBACKS", False))


def _imu_time_column_name(df: pd.DataFrame):
    """DUO INTERIM 常见为 'timestamp' 或 'Time'。"""
    preferred = ("Time", "time", "timestamp", "Timestamp", "TIME", "Time(s)", "time(s)")
    for c in preferred:
        if c in df.columns:
            return c
    lower_map = {str(c).strip().lower(): c for c in df.columns}
    for key in ("time", "timestamp", "time(s)"):
        if key in lower_map:
            return lower_map[key]
    return None


class DUOGAITProcessor:
    """Process DUO-GAIT raw data files to JSON windows"""

    def __init__(self, imu_data_dir, hr_data_dir, output_dir, subject_id='sub_01', task_type='st_control'):
        self.imu_data_dir = imu_data_dir    # interim: IMU data (ST.csv, LF.csv, etc)
        self.hr_data_dir = hr_data_dir      # raw: heart_rate.CSV
        self.output_dir = output_dir
        self.subject_id = subject_id
        self.task_type = task_type          # e.g., 'st_control', 'st_fatigue', 'dt_control'
        self.window_duration = 30  # seconds
        self.st_data = None
        self.hr_data = None
        self.st_sample_rate = None
        self.hr_sample_rate = None
        self.hr_start_offset = 0  # Offset in seconds for HR data alignment
        self.lf_data = None
        self.rf_data = None
        self.subject_height_m = None  # 双足 IMU 步长弱先验（身高）；主流程不读 DUO processed

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
        # HR CSV format (Garmin export): rows 0-4 = metadata, row 5 = type label, row 6 = headers, row 7+ = data
        # Note: Columns are: [empty, Time, HR (bpm), Speed, Pace, Cadence, ...]
        hr_file = os.path.join(self.hr_data_dir, 'heart_rate.CSV')
        self.hr_data = pd.read_csv(hr_file, skiprows=6, low_memory=False)

        # The HR CSV has a weird format: actual column names are shifted
        # Rename columns to match the expected structure
        # Position: 0=empty, 1=Time, 2=HR, 3+=others
        # We'll use positional indexing to be safe
        if len(self.hr_data.columns) >= 3:
            # Rename columns for clarity
            col_names = ['meta'] + list(self.hr_data.columns[1:])
            self.hr_data.columns = col_names
            # Specifically rename the HR column (position 2)
            rename_dict = {col_names[2]: 'HR (bpm)'}
            self.hr_data = self.hr_data.rename(columns=rename_dict)

        print(f"  ✓ Loaded heart rate data: {len(self.hr_data)} rows")
        print(f"    HR Columns: {list(self.hr_data.columns)[:5]}...")

        # Estimate sample rates from时间列（timestamp / Time）
        st_tc = _imu_time_column_name(self.st_data)
        if st_tc:
            time_vals = pd.to_numeric(self.st_data[st_tc], errors="coerce").dropna()
            if len(time_vals) > 1:
                time_diff = float(time_vals.iloc[1] - time_vals.iloc[0])
                if time_diff > 0:
                    self.st_sample_rate = 1.0 / time_diff
                    print(f"  ✓ ST sample rate ({st_tc}): {self.st_sample_rate:.1f} Hz")

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

        # 双足 INTERIM（可选）：与 ST 同目录
        for fname, attr in (("LF.csv", "lf_data"), ("RF.csv", "rf_data")):
            fp = os.path.join(self.imu_data_dir, fname)
            if os.path.isfile(fp):
                try:
                    setattr(self, attr, pd.read_csv(fp, index_col=0))
                except Exception:
                    setattr(self, attr, pd.read_csv(fp))
                print(f"  ✓ Loaded {fname}: {len(getattr(self, attr))} rows")

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
            （config.METRIC_ALLOW_DEFAULT_FALLBACKS=False 时，不可靠则为 None，便于初期发现问题）
        """
        allow_fb = _metric_fallbacks_enabled()
        bad = {"step_frequency_hz": None, "step_length_m": None, "step_time_variability_ms": None}
        fb = {"step_frequency_hz": 1.5, "step_length_m": 0.6, "step_time_variability_ms": 35.0}
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
                return dict(fb) if allow_fb else dict(bad)

            # Filter out NaN values
            valid_idx = ~(np.isnan(ax) | np.isnan(ay) | np.isnan(az))
            ax = ax[valid_idx]
            ay = ay[valid_idx]
            az = az[valid_idx]

            if len(ax) < 20:
                return dict(fb) if allow_fb else dict(bad)

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
            # Use standard config parameters instead of hardcoded values
            # Peak height multiplier = 2.5 (was 0.2, too sensitive)
            peak_threshold = np.std(filtered) * 2.5
            # Min distance = 0.4s (was int(rate/4), too small)
            min_distance = max(1, int(0.4 * (self.st_sample_rate or 100)))

            step_frequency = None
            step_time_var = None

            try:
                peaks, properties = signal.find_peaks(
                    filtered,
                    height=peak_threshold,
                    distance=min_distance,
                    prominence=peak_threshold * 0.5
                )

                if len(peaks) > 1:
                    peak_times = np.diff(peaks)

                    if self.st_sample_rate and self.st_sample_rate > 0:
                        step_intervals = peak_times / self.st_sample_rate
                    else:
                        step_intervals = peak_times / 100

                    valid_intervals = step_intervals[(step_intervals > 0.3) & (step_intervals < 2.0)]

                    if len(valid_intervals) > 0:
                        step_frequency = float(1.0 / np.mean(valid_intervals))
                        step_time_var = float(np.std(valid_intervals) * 1000.0)
                    elif allow_fb:
                        step_frequency = 1.5
                        step_time_var = 35.0
                elif allow_fb:
                    try:
                        fft_vals = np.abs(fft(accel_abs))
                        freqs = fftfreq(len(accel_abs), 1.0 / (self.st_sample_rate or 100))
                        freq_mask = (freqs > 0.5) & (freqs < 4.0)
                        if freq_mask.any():
                            peak_freq_idx = np.argmax(fft_vals[freq_mask])
                            peak_freq = freqs[freq_mask][peak_freq_idx]
                            step_frequency = float(np.abs(peak_freq))
                            step_time_var = 30.0
                        else:
                            step_frequency = 1.5
                            step_time_var = 35.0
                    except Exception:
                        step_frequency = 1.5
                        step_time_var = 35.0
            except Exception:
                if allow_fb:
                    step_frequency = 1.5
                    step_time_var = 35.0

            if allow_fb:
                if step_frequency is None:
                    step_frequency = 1.5
                if step_time_var is None:
                    step_time_var = 35.0
                step_frequency = float(np.clip(step_frequency, 0.5, 4.0))
                step_time_var = float(np.clip(step_time_var, 5.0, 100.0))
            else:
                if step_frequency is not None:
                    step_frequency = float(step_frequency)
                if step_time_var is not None:
                    step_time_var = max(0.0, float(step_time_var))

            # 步长：无可靠步频时（验证模式）不输出胸戴估计，避免掩盖步态检测失败
            stride_length = None
            if step_frequency is not None or allow_fb:
                try:
                    if len(accel_cols) >= 3:
                        accel_x = pd.to_numeric(accel_data[accel_cols[0]], errors="coerce").values
                        accel_y = pd.to_numeric(accel_data[accel_cols[1]], errors="coerce").values
                        accel_z = pd.to_numeric(accel_data[accel_cols[2]], errors="coerce").values
                        accel_x = accel_x[valid_idx]
                        accel_y = accel_y[valid_idx]
                        accel_z = accel_z[valid_idx]
                        accel_dynamic = np.sqrt(
                            accel_x ** 2 + accel_y ** 2 + (accel_z - 1.0) ** 2
                        )
                        accel_intensity = np.sqrt(np.nanmean(accel_dynamic ** 2))
                        stride_length = 1.0 + (accel_intensity / 0.2) * 0.4
                        if allow_fb:
                            stride_length = float(np.clip(stride_length, 0.9, 1.5))
                        else:
                            stride_length = float(stride_length)
                    else:
                        stride_length = 1.2 if allow_fb else None
                except Exception:
                    stride_length = 1.2 if allow_fb else None

            def _r2(x):
                return None if x is None else round(float(x), 2)

            def _r1(x):
                return None if x is None else round(float(x), 1)

            features["step_frequency_hz"] = _r2(step_frequency)
            features["step_length_m"] = _r2(stride_length)
            features["step_time_variability_ms"] = _r1(step_time_var)

        except Exception as e:
            print(f"Warning: Error in gait feature extraction: {e}")
            if allow_fb:
                features = dict(fb)
            else:
                features = dict(bad)

        return features

    def _enhance_gait_with_foot_imu(
        self,
        chest_gait: dict,
        start_idx: int,
        end_idx: int,
    ) -> dict:
        """
        用 INTERIM 双足 LF/RF 仅修正步长（与部署时 IMU+心率一致）。
        步频与步时变异始终来自胸戴 ST；不使用 DUO processed。
        """
        out = dict(chest_gait)
        lf_win = (
            self.lf_data.iloc[start_idx:end_idx]
            if self.lf_data is not None and len(self.lf_data) >= end_idx
            else None
        )
        rf_win = (
            self.rf_data.iloc[start_idx:end_idx]
            if self.rf_data is not None and len(self.rf_data) >= end_idx
            else None
        )
        if lf_win is None and rf_win is None:
            return out
        cad = out.get("step_frequency_hz")
        if cad is None and not _metric_fallbacks_enabled():
            return out
        chest_s = out.get("step_length_m")
        if chest_s is None and not _metric_fallbacks_enabled():
            return out
        cad_f = float(cad if cad is not None else 1.5)
        chest_f = float(chest_s if chest_s is not None else 0.6)
        out["step_length_m"] = round(
            stride_from_cadence_height_and_feet(
                cad_f,
                self.subject_height_m,
                lf_win,
                rf_win,
                chest_f,
            ),
            2,
        )
        return out

    def extract_hr_features(self, hr_values):
        """
        Extract heart rate features from a 30-second window
        """
        features = {}

        # Remove NaN values
        hr_clean = hr_values[~np.isnan(hr_values)]

        if len(hr_clean) > 0:
            features['hr_mean_bpm'] = round(np.mean(hr_clean), 1)
            features['hr_max_bpm'] = round(np.max(hr_clean), 1)
        else:
            # No HR data available - use NaN to indicate missing data
            # Don't use hardcoded defaults as that masks data quality issues
            features['hr_mean_bpm'] = np.nan
            features['hr_max_bpm'] = np.nan

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

    def create_window_json(self, window_idx, gait_features, hr_features,
                          warmup_baseline, imu_quality, hr_quality, player_age,
                          rpe_value=None):
        """Create JSON window object in new format"""

        def to_serializable(value):
            """Convert numpy types to Python native types for JSON serialization"""
            if value is None:
                return None
            if isinstance(value, (np.integer, np.int64)):
                return int(value)
            elif isinstance(value, (np.floating, np.float64)):
                return float(value)
            elif isinstance(value, np.ndarray):
                return value.tolist()
            elif isinstance(value, (float, np.floating)) and np.isnan(value):
                return None
            return value

        # Initialize fuzzy classifier for ground_truth（与同事 LLM 规则对齐）
        classifier = FuzzyExerciseClassifier(age=player_age)

        raw_hr_mean = hr_features.get("hr_mean_bpm")
        if raw_hr_mean is None or (isinstance(raw_hr_mean, float) and np.isnan(raw_hr_mean)):
            mean_hr = None
        else:
            mean_hr = float(raw_hr_mean)

        def _feat_float(key: str):
            v = gait_features.get(key)
            if v is None:
                return None
            try:
                f = float(v)
            except (TypeError, ValueError):
                return None
            if np.isnan(f) or np.isinf(f):
                return None
            return f

        step_var = _feat_float("step_time_variability_ms")
        step_freq = _feat_float("step_frequency_hz")
        stride_length = _feat_float("step_length_m")

        raw_hr_max = hr_features.get("hr_max_bpm")
        if raw_hr_max is None or (isinstance(raw_hr_max, float) and np.isnan(raw_hr_max)):
            max_hr = None
        else:
            max_hr = float(raw_hr_max)

        try:
            fuzzy_result = classifier.classify(
                hr_mean=mean_hr,
                step_var=step_var,
                hr_recovery=None,
                stride_length=stride_length,
                rpe_score=rpe_value,
                cadence_hz=step_freq,
                imu_quality=imu_quality,
                hr_quality=hr_quality,
                warmup_baseline=warmup_baseline or {},
                max_hr=max_hr,
            )

            exercise_load = fuzzy_result["exercise_load"][1]
            fatigue_level = fuzzy_result["fatigue_level"][1]
            movement_quality = fuzzy_result["movement_quality"][1]
            composite_state = fuzzy_result["composite_state"]

        except Exception as e:
            # Fallback if fuzzy logic fails
            print(f"    ⚠ Fuzzy classifier error for window {window_idx}: {e}")
            exercise_load = 'moderate'
            fatigue_level = 'none'
            movement_quality = 'good'
            composite_state = 'normal'

        window_json = {
            "sample_id": f"{window_idx:03d}",
            "subject_id": self.subject_id,
            "player_age": int(player_age),
            "dataset_source": "DUO-GAIT",
            "input_features": {
                "step_frequency_hz": to_serializable(step_freq),
                "step_length_m": to_serializable(stride_length),
                "step_time_variability_ms": to_serializable(step_var),
                "mean_hr_bpm": to_serializable(mean_hr),
                "max_hr_bpm": to_serializable(max_hr),
            },
            "warmup_baseline": warmup_baseline,
            "rpe": to_serializable(rpe_value),
            "imu_quality": to_serializable(imu_quality),
            "hr_quality": to_serializable(hr_quality),
            "ground_truth": {
                "exercise_load": exercise_load,
                "fatigue_level": fatigue_level,
                "movement_quality": movement_quality,
                "composite_state": composite_state
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

        # Get player age / 身高（用于无 processed 时双足步长弱先验）
        player_age = get_subject_age(self.subject_id)
        self.subject_height_m = get_subject_height_m(self.subject_id)
        print(f"  Player age: {player_age} years (MHR = {220 - player_age} bpm)")
        if self.subject_height_m:
            print(f"  Subject height (for foot IMU fallback): {self.subject_height_m:.2f} m")

        # Prepare time column
        st_tc = _imu_time_column_name(self.st_data)
        if st_tc:
            st_time = pd.to_numeric(self.st_data[st_tc], errors="coerce").values
        else:
            st_time = np.arange(len(self.st_data)) / (self.st_sample_rate or 128)

        # Calculate samples per window
        samples_per_window = int(self.window_duration * (self.st_sample_rate or 100))
        total_windows = len(self.st_data) // samples_per_window

        if max_windows:
            total_windows = min(total_windows, max_windows)

        print(f"  Total windows: {total_windows}")
        print(f"  Samples per window: {samples_per_window}\n")

        windows_created = 0
        warmup_baseline = None  # Will be set from first window

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
            gait_features = self._enhance_gait_with_foot_imu(
                gait_features,
                start_idx,
                end_idx,
            )

            # Extract HR features
            hr_values = np.array([])
            if not hr_window.empty and 'HR (bpm)' in hr_window.columns:
                # Now HR column should be correctly named 'HR (bpm)' after fixing skiprows
                hr_values = pd.to_numeric(hr_window['HR (bpm)'], errors='coerce').values
            else:
                # Fallback: try to find any HR-like column
                if not hr_window.empty:
                    for col in hr_window.columns:
                        if 'HR' in col or 'heart' in col.lower() or 'bpm' in col.lower():
                            hr_values = pd.to_numeric(hr_window[col], errors='coerce').values
                            break

            hr_features = self.extract_hr_features(hr_values)

            # Assess data quality
            gait_quality, gait_reason = self.assess_data_quality(st_window, 'imu')
            if hr_window.empty:
                hr_quality, hr_reason = (0.25, "no hr window")
            else:
                hr_quality, hr_reason = self.assess_data_quality(hr_window, "heart_rate")
            hm = hr_features.get("hr_mean_bpm")
            if hm is None or (isinstance(hm, float) and np.isnan(hm)):
                hr_quality = float(min(hr_quality, 0.35))

            # Set warmup_baseline from first window
            if window_idx == 0:
                warmup_baseline = {
                    "warmup_cadence_hz": gait_features.get('step_frequency_hz', 1.8),
                    "warmup_stride_m": gait_features.get('step_length_m', 0.6),
                    "warmup_var_ms": gait_features.get('step_time_variability_ms', 20.0)
                }

            # Create JSON with new format
            window_json = self.create_window_json(
                window_idx,
                gait_features,
                hr_features,
                warmup_baseline,
                gait_quality,
                hr_quality,
                player_age
            )

            # Save JSON file
            output_filename = f"{self.subject_id}_{self.task_type}_window_{window_idx:04d}.json"
            output_path = os.path.join(self.output_dir, output_filename)

            with open(output_path, 'w') as f:
                json.dump(window_json, f, indent=2)

            windows_created += 1

            if (window_idx + 1) % max(1, total_windows // 10) == 0:
                progress = (window_idx + 1) / total_windows * 100
                print(f"  [{progress:5.1f}%] Processed window {window_idx + 1}/{total_windows} → {output_filename}")
                # Diagnostic: show HR and metrics
                hr_mean = hr_features.get('hr_mean_bpm', np.nan)
                cadence = gait_features.get('step_frequency_hz', 'N/A')
                if not np.isnan(hr_mean):
                    print(f"        ↳ HR: {hr_mean:.1f} bpm, Cadence: {cadence} Hz")

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


def get_subject_height_m(subject_id='sub_01'):
    """身高（米），用于双足 IMU 无 processed 时的步长先验；缺失则返回 None。"""
    try:
        subject_info_path = '/Volumes/ChouSSD/elder_datasets/DUO-GAIT/raw/subject_info.csv'
        info_df = pd.read_csv(subject_info_path)
        subject_row = info_df[info_df['sub'] == subject_id]
        if subject_row.empty:
            return None
        row = subject_row.iloc[0]
        for col in ('height(cm)', 'height_m', 'height'):
            if col in info_df.columns:
                h = float(row[col])
                if col == 'height_m':
                    return h if h > 0.5 else None
                return (h / 100.0) if h > 30 else None
    except Exception:
        pass
    return None


def main():
    import sys

    # Configuration
    imu_data_dir = '/Volumes/ChouSSD/elder_datasets/DUO-GAIT/interim/OG_st_control/sub_01'
    hr_data_dir = '/Volumes/ChouSSD/elder_datasets/DUO-GAIT/raw/OG_st_raw/sub_01'  # Where heart_rate.CSV is located
    output_dir = '/Volumes/ChouSSD/elder_datasets/DUO-GAIT/json/'
    subject_id = 'sub_01'
    task_type = 'st_control'  # 与 interim 子目录任务名一致，用于输出文件名
    max_windows = None  # Process all windows

    # Get subject age from info file
    subject_age = get_subject_age(subject_id)
    print(f"Subject age: {subject_age} years")

    print("=" * 70)
    print("DUO-GAIT Data Processor - JSON Window Export")
    print("=" * 70)
    print(f"Subject: {subject_id}")
    print(f"IMU Input: {imu_data_dir}")
    print(f"HR Input: {hr_data_dir}")
    print(f"Output: {output_dir}")
    print(f"Window duration: 30 seconds")
    print(f"Processing: ALL data (complete subject dataset)")
    print("=" * 70)

    processor = DUOGAITProcessor(imu_data_dir, hr_data_dir, output_dir, subject_id, task_type)
    processor.load_data()
    processor.process_windows(max_windows=max_windows)

    print("\n📊 Next steps:")
    print(f"  1. JSON files saved to: {output_dir}")
    print(f"  2. Use these JSONs for LLM processing")
    print(f"  3. Run fuzzy logic validation on the JSON outputs")


if __name__ == '__main__':
    main()
