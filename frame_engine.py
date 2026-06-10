import os
import time
import math
import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim
from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot, QMutex, QMutexLocker

from utils import (
    setup_logging, log_capture_error, format_timestamp, format_timestamp_hms,
    apply_safe_zone_crop, resize_frame_720p, get_session_temp_dir,
    LAPLACIAN_THRESHOLD, BLANK_BRIGHT_THRESHOLD, BLACK_DARK_THRESHOLD,
    SSIM_THRESHOLD_DEFAULT, SSIM_THRESHOLD_BURST, EDGE_DENSITY_THRESHOLD,
    SCORE_THRESHOLD_CAPTURE, SCORE_OVERRIDE_GAP, MIN_GAP_DEFAULT,
    MIN_GAP_FAST_TEACHER, FAST_TEACHER_ENTRIES_PER_HOUR,
    ADAPTIVE_BURST_COUNT, ADAPTIVE_BURST_DURATION, MIN_CAPTURE_FLOOR,
    CONTEXT_WINDOW_BEFORE, CONTEXT_WINDOW_AFTER, SYNC_OFFSET_MIN,
    SYNC_OFFSET_MAX, contains_keywords, HINGLISH_KEYWORDS, HINDI_KEYWORDS,
    ENGLISH_KEYWORDS, MATH_SYMBOLS, QUESTION_INDICATORS, resolve_path_safe,
)
from transcript_parser import TranscriptParser


class FrameCaptureConfig:
    def __init__(self):
        self.mode = "smart_auto"
        self.sync_offset = 0
        self.min_gap_base = MIN_GAP_DEFAULT
        self.ssim_threshold = SSIM_THRESHOLD_DEFAULT
        self.ssim_threshold_burst = SSIM_THRESHOLD_BURST
        self.adaptive_burst_count = ADAPTIVE_BURST_COUNT
        self.adaptive_burst_duration = ADAPTIVE_BURST_DURATION
        self.score_threshold = SCORE_THRESHOLD_CAPTURE
        self.score_override_gap = SCORE_OVERRIDE_GAP
        self.fast_teacher_threshold = FAST_TEACHER_ENTRIES_PER_HOUR
        self.fast_teacher_min_gap = MIN_GAP_FAST_TEACHER
        self.min_capture_floor = MIN_CAPTURE_FLOOR
        self.safe_zone = {"crop_bottom_pct": 15, "crop_corner_pct": 20}
        self.speed = "normal"
        self._sampling_offsets = [0, 4, 8, 12]
        self.change_detection_interval = 6
        self.start_time_sec = 0
        self.end_time_sec = None
        self.frame_save_quality = 85

    @property
    def sampling_offsets(self):
        if self.speed == "fast":
            return [0]
        elif self.speed == "thorough":
            return [0, 2, 4, 6, 8, 10, 12]
        return self._sampling_offsets

    @sampling_offsets.setter
    def sampling_offsets(self, value):
        self._sampling_offsets = value
        self.start_time_sec = 0
        self.end_time_sec = None
        self.frame_save_quality = 85


class CapturedFrame:
    def __init__(self, frame_id, timestamp_sec, frame_array, content_score, transcript_text="", is_manual=False):
        self.id = frame_id
        self.timestamp_sec = timestamp_sec
        self.timestamp_display = format_timestamp(timestamp_sec)
        self.frame_array = frame_array
        self.content_score = content_score
        self.transcript_text = transcript_text
        self.is_manual = is_manual
        self.caption = ""
        self.tags = []
        self.file_path = None

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp_sec": self.timestamp_sec,
            "timestamp_display": self.timestamp_display,
            "frame_path": self.file_path,
            "caption": self.caption,
            "tags": self.tags,
            "transcript_context": self.transcript_text,
            "content_score": self.content_score,
            "is_manual": self.is_manual,
        }

    def save_to_disk(self, output_dir):
        os.makedirs(output_dir, exist_ok=True)
        filename = f"frame_{self.timestamp_sec:06d}.jpg"
        self.file_path = os.path.join(output_dir, filename)
        try:
            success, buffer = cv2.imencode(".jpg", self.frame_array,
                                           [cv2.IMWRITE_JPEG_QUALITY, 85])
            if success:
                with open(self.file_path, "wb") as f:
                    f.write(buffer.tobytes())
                return self.file_path
        except Exception as e:
            log_capture_error(self.timestamp_sec, f"Failed to save frame: {e}")
            return None


class FrameCaptureSignals(QObject):
    progress = pyqtSignal(int, int, int, str)
    frame_captured = pyqtSignal(object)
    frame_rejected = pyqtSignal(int, str)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)
    status_update = pyqtSignal(str)
    log_message = pyqtSignal(str)


class FrameCaptureEngine(QObject):
    def __init__(self):
        super().__init__()
        self.signals = FrameCaptureSignals()
        self.config = FrameCaptureConfig()
        self._mutex = QMutex()
        self._cancelled = False
        self._paused = False
        self.logger = setup_logging()
        self.captured_frames = []
        self._last_capture_times = []
        self._saved_ssim_paths = []
        self._burst_mode = False
        self._burst_timer = 0
        self._frame_counter = 0
        self._session_dir = None

    @pyqtSlot()
    def cancel(self):
        with QMutexLocker(self._mutex):
            self._cancelled = True

    @pyqtSlot()
    def pause(self):
        with QMutexLocker(self._mutex):
            self._paused = True

    @pyqtSlot()
    def resume(self):
        with QMutexLocker(self._mutex):
            self._paused = False

    @pyqtSlot(str, list)
    def process_video(self, video_path, transcript_entries):
        self._cancelled = False
        self._paused = False
        self.captured_frames = []
        self._last_capture_times = []
        self._saved_ssim_paths = []
        self._burst_mode = False
        self._burst_timer = 0
        self._frame_counter = 0
        self._session_dir = get_session_temp_dir()

        video_path = resolve_path_safe(video_path)
        cap = self._open_video(video_path)
        if cap is None:
            self.signals.error.emit(f"Could not open video: {video_path}")
            self.signals.finished.emit([])
            return

        try:
            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration_sec = total_frames / fps if fps > 0 else 0
            if self.config.end_time_sec is None:
                self.config.end_time_sec = duration_sec

            self.signals.status_update.emit(
                f"Video: {format_timestamp_hms(int(duration_sec))}, "
                f"{fps:.1f} fps, {total_frames} frames"
            )

            mode = self.config.mode
            sync_offset = self.config.sync_offset
            min_gap = self._calculate_min_gap(transcript_entries, duration_sec)
            current_threshold = self.config.ssim_threshold

            try:
                if mode == "smart_auto" and transcript_entries:
                    self._process_smart_auto(cap, transcript_entries, sync_offset,
                                             min_gap, duration_sec)
                elif mode == "change_only":
                    self._process_change_detection(cap, duration_sec, fps, min_gap)
                elif mode == "manual":
                    pass
                elif mode == "hybrid":
                    self._process_smart_auto(cap, transcript_entries, sync_offset,
                                             min_gap, duration_sec)
            except Exception as e:
                self.logger.error("Main capture loop error: %s", str(e), exc_info=True)
                self.signals.status_update.emit(f"Capture error in main loop: {e}")

            self._enforce_min_capture_floor(cap, transcript_entries, duration_sec)

            cap.release()
            self.signals.finished.emit(self.captured_frames)

        except Exception as e:
            self.logger.error("Frame capture error: %s", str(e), exc_info=True)
            cap.release()
            self.signals.error.emit(str(e))
            self.signals.finished.emit(self.captured_frames)

    def _open_video(self, video_path):
        if not os.path.isfile(video_path):
            self.logger.error("Video file not found: %s", video_path)
            return None
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                cap.release()
                return None
            return cap
        except cv2.error as e:
            self.logger.error("OpenCV error opening video: %s", e)
            return None

    def _calculate_min_gap(self, transcript_entries, duration_sec):
        min_gap = self.config.min_gap_base
        if transcript_entries and duration_sec > 0:
            entries_per_hour = len(transcript_entries) / (duration_sec / 3600)
            if entries_per_hour > self.config.fast_teacher_threshold:
                min_gap = self.config.fast_teacher_min_gap
                self.signals.status_update.emit(
                    f"Fast teacher detected ({entries_per_hour:.0f} entries/hr). "
                    f"Min gap set to {min_gap}s"
                )
        return min_gap

    def _process_smart_auto(self, cap, transcript_entries, sync_offset,
                            min_gap, duration_sec):
        total_entries = len(transcript_entries)
        last_capture_time = -min_gap

        for idx, entry in enumerate(transcript_entries):
            if self._check_cancelled():
                break
            self._wait_if_paused()

            progress_pct = int((idx / total_entries) * 100) if total_entries else 0
            self.signals.progress.emit(idx, total_entries, progress_pct,
                                        entry.get("text", "")[:50])

            if entry.get("is_silence"):
                continue

            base_time = entry["start_sec"] + sync_offset
            if base_time < self.config.start_time_sec or base_time > self.config.end_time_sec:
                continue
            if base_time < 0 or base_time >= duration_sec:
                continue

            if base_time - last_capture_time < min_gap:
                candidate_override = self._evaluate_candidate(
                    cap, base_time, entry["text"], current_threshold=None
                )
                if candidate_override and candidate_override.get("score", 0) >= self.config.score_override_gap:
                    pass
                else:
                    continue

            best_candidate = self._sample_candidates(cap, base_time, entry["text"])
            if best_candidate is None:
                continue

            do_save, reason = self._should_save(best_candidate, base_time, min_gap)
            if not do_save:
                self.signals.frame_rejected.emit(int(base_time), reason)
                continue

            captured = self._save_captured_frame(best_candidate, base_time, entry["text"])
            if captured:
                last_capture_time = base_time
                self._update_adaptive_state(base_time)
                self.signals.frame_captured.emit(captured)

    def _process_change_detection(self, cap, duration_sec, fps, min_gap):
        interval = self.config.change_detection_interval
        total_steps = max(1, int((self.config.end_time_sec - self.config.start_time_sec) / interval))
        last_capture_time = -min_gap
        step = 0

        t = self.config.start_time_sec
        while t < self.config.end_time_sec:
            if self._check_cancelled():
                break
            self._wait_if_paused()

            progress_pct = int((step / total_steps) * 100) if total_steps else 0
            self.signals.progress.emit(step, total_steps, progress_pct, "")
            step += 1

            candidate = self._evaluate_candidate(cap, t, "", current_threshold=None)
            if candidate is None:
                t += interval
                continue

            do_save, reason = self._should_save(candidate, t, min_gap)
            if not do_save:
                t += interval
                continue

            captured = self._save_captured_frame(candidate, t, "")
            if captured:
                last_capture_time = t
                self._update_adaptive_state(t)
                self.signals.frame_captured.emit(captured)

            t += interval

    def _sample_candidates(self, cap, base_time, transcript_text):
        best = None
        best_score = -1

        for offset in self.config.sampling_offsets:
            sample_time = base_time + offset
            candidate = self._evaluate_candidate(cap, sample_time, transcript_text)
            if candidate is None:
                continue
            if candidate["score"] > best_score:
                best_score = candidate["score"]
                best = candidate

        return best

    def _evaluate_candidate(self, cap, timestamp_sec, transcript_text,
                            current_threshold=None):
        frame = self._seek_and_read(cap, timestamp_sec)
        if frame is None:
            return None

        frame = resize_frame_720p(frame)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        safe_zone = apply_safe_zone_crop(gray, self.config.safe_zone)

        if self._rule1_reject(safe_zone, frame, timestamp_sec):
            return None

        score = self._rule5_score(safe_zone, frame, transcript_text,
                                   timestamp_sec, current_threshold)

        return {
            "score": score,
            "frame": frame,
            "gray_safe": safe_zone,
            "timestamp": timestamp_sec,
            "transcript": transcript_text,
        }

    def _seek_and_read(self, cap, timestamp_sec):
        if timestamp_sec < 0:
            return None
        try:
            msec = int(timestamp_sec * 1000)
            cap.set(cv2.CAP_PROP_POS_MSEC, msec)
            ret, frame = cap.read()
            if not ret or frame is None:
                log_capture_error(timestamp_sec, "Failed to read frame")
                return None
            if frame.size == 0:
                log_capture_error(timestamp_sec, "Empty frame")
                return None
            return frame
        except cv2.error as e:
            log_capture_error(timestamp_sec, f"OpenCV error: {e}")
            return None

    def _rule1_reject(self, gray_safe, frame_bgr, timestamp_sec):
        mean_brightness = np.mean(gray_safe)
        if mean_brightness > BLANK_BRIGHT_THRESHOLD:
            log_capture_error(timestamp_sec, f"Blank frame (brightness={mean_brightness:.0f})")
            return True
        if mean_brightness < BLACK_DARK_THRESHOLD:
            log_capture_error(timestamp_sec, f"Dark transition frame (brightness={mean_brightness:.0f})")
            return True
        laplacian_var = cv2.Laplacian(gray_safe, cv2.CV_64F).var()
        if laplacian_var < LAPLACIAN_THRESHOLD:
            log_capture_error(timestamp_sec, f"Blurry frame (laplacian_var={laplacian_var:.1f})")
            return True
        return False

    def _rule5_score(self, gray_safe, frame_bgr, transcript_text,
                     timestamp_sec, current_threshold=None):
        score = 0
        h, w = gray_safe.shape
        total_pixels = h * w

        edges = cv2.Canny(gray_safe, 50, 150)
        edge_pixels = np.count_nonzero(edges)
        edge_density = edge_pixels / total_pixels

        if edge_density > EDGE_DENSITY_THRESHOLD:
            score += 30

        if edge_density < 0.01:
            score -= 15

        if self.config.speed == "fast":
            pass
        elif self._saved_ssim_paths:
            gray_resized = cv2.resize(gray_safe, (320, 180))
            max_similarity = 0
            for saved_path in self._saved_ssim_paths[-5:]:
                try:
                    saved = cv2.imread(saved_path, cv2.IMREAD_GRAYSCALE)
                    if saved is None:
                        continue
                    saved_resized = cv2.resize(saved, (320, 180))
                    current_thresh = current_threshold or self._get_current_ssim_threshold()
                    sim = ssim(gray_resized, saved_resized, data_range=255)
                    max_similarity = max(max_similarity, sim)
                except Exception:
                    continue

            if max_similarity > 0.8:
                score -= 20

            if max_similarity <= 0.12:
                pass
            elif max_similarity < 0.65:
                score += 25

        if transcript_text:
            lower_text = transcript_text.lower()
            all_kw = ENGLISH_KEYWORDS + HINDI_KEYWORDS + HINGLISH_KEYWORDS
            if contains_keywords(lower_text, all_kw):
                score += 25
            elif any(sym in transcript_text for sym in MATH_SYMBOLS):
                score += 25
            if contains_keywords(lower_text, QUESTION_INDICATORS):
                score += 20

        return score

    def _rule2_dedup(self, gray_safe, current_threshold):
        if not self._saved_ssim_paths:
            return False
        gray_resized = cv2.resize(gray_safe, (320, 180))
        for saved_path in self._saved_ssim_paths[-5:]:
            try:
                saved = cv2.imread(saved_path, cv2.IMREAD_GRAYSCALE)
                if saved is None:
                    continue
                saved_resized = cv2.resize(saved, (320, 180))
                sim = ssim(gray_resized, saved_resized, data_range=255)
                if sim > current_threshold:
                    return True
            except Exception:
                continue
        return False

    def _rule4_min_gap(self, timestamp_sec, min_gap, score):
        if not self._last_capture_times:
            return True
        last_time = self._last_capture_times[-1]
        gap = timestamp_sec - last_time
        if gap >= min_gap:
            return True
        if score >= self.config.score_override_gap:
            return True
        return False

    def _rule7_adaptive_check(self):
        now = time.time()
        if self._burst_mode:
            if now - self._burst_timer > self.config.adaptive_burst_duration:
                self._burst_mode = False
                self.signals.status_update.emit("Adaptive threshold reset to normal")
            else:
                return True
        recent = [t for t in self._last_capture_times
                  if now - t < 60]
        if len(recent) > self.config.adaptive_burst_count:
            self._burst_mode = True
            self._burst_timer = now
            self.signals.status_update.emit("Burst detected. Raising dedup threshold")
        return True

    def _get_current_ssim_threshold(self):
        if self._burst_mode:
            return self.config.ssim_threshold_burst
        return self.config.ssim_threshold

    def _should_save(self, candidate, timestamp_sec, min_gap):
        score = candidate["score"]
        if score < self.config.score_threshold:
            return False, f"Low score ({score})"

        if not self._rule4_min_gap(timestamp_sec, min_gap, score):
            return False, f"Min gap ({min_gap}s) not met, score {score}"

        if self.config.speed != "fast":
            current_threshold = self._get_current_ssim_threshold()
            if self._rule2_dedup(candidate["gray_safe"], current_threshold):
                return False, f"Duplicate (SSIM > {current_threshold})"

        if not self._rule7_adaptive_check():
            return False, "Adaptive throttle active"

        return True, ""

    def _save_captured_frame(self, candidate, base_time, transcript_text):
        frame_id = len(self.captured_frames) + 1
        captured = CapturedFrame(
            frame_id=frame_id,
            timestamp_sec=base_time,
            frame_array=candidate["frame"],
            content_score=candidate["score"],
            transcript_text=transcript_text,
            is_manual=False,
        )
        path = captured.save_to_disk(self._session_dir)
        if path:
            self._saved_ssim_paths.append(path)
            self.captured_frames.append(captured)
            return captured
        return None

    def _update_adaptive_state(self, timestamp_sec):
        self._last_capture_times.append(time.time())
        self._frame_counter += 1

    def _enforce_min_capture_floor(self, cap, transcript_entries, duration_sec):
        if len(self.captured_frames) >= self.config.min_capture_floor:
            return
        needed = self.config.min_capture_floor - len(self.captured_frames)
        self.signals.status_update.emit(
            f"Only {len(self.captured_frames)} captured. Forcing {needed} more..."
        )
        step = max(1, int(duration_sec / (needed + 1)))
        t = step
        while t < duration_sec and len(self.captured_frames) < self.config.min_capture_floor:
            if self._check_cancelled():
                break
            frame = self._seek_and_read(cap, t)
            if frame is not None:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                mean_brightness = np.mean(gray)
                if mean_brightness > 20 and mean_brightness < 235:
                    text = ""
                    for e in transcript_entries:
                        if e["start_sec"] <= t <= e["end_sec"]:
                            text = e["text"]
                            break
                    frame_id = len(self.captured_frames) + 1
                    captured = CapturedFrame(
                        frame_id=frame_id,
                        timestamp_sec=t,
                        frame_array=frame,
                        content_score=50,
                        transcript_text=text,
                        is_manual=True,
                    )
                    captured.caption = f"Forced capture at {format_timestamp(t)}"
                    path = captured.save_to_disk(self._session_dir)
                    if path:
                        self._saved_ssim_paths.append(path)
                        self.captured_frames.append(captured)
                        self.signals.frame_captured.emit(captured)
            t += step

    def _check_cancelled(self):
        with QMutexLocker(self._mutex):
            return self._cancelled

    def _wait_if_paused(self):
        while True:
            with QMutexLocker(self._mutex):
                if not self._paused:
                    return
            QThread.msleep(100)


class FrameCaptureThread(QThread):
    def __init__(self, engine, video_path, transcript_entries):
        super().__init__()
        self.engine = engine
        self.video_path = video_path
        self.transcript_entries = transcript_entries

    def run(self):
        self.engine.process_video(self.video_path, self.transcript_entries)
