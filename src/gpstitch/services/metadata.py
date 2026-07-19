"""Metadata extraction service using gopro_overlay."""

import json
import logging
from pathlib import Path

from gpstitch.config import settings
from gpstitch.models.schemas import GpxFitMetadata, VideoMetadata

# Apply runtime patches if enabled
if settings.enable_gopro_patches:
    from gpstitch.patches import apply_patches

    apply_patches()

logger = logging.getLogger(__name__)


_VALID_ROTATIONS = {0, 90, 180, 270}


def get_video_rotation(file_path: Path) -> int:
    """Get video rotation magnitude from metadata.

    Returns one of 0, 90, 180, 270. Unrecognised values fall back to 0.
    """
    from gopro_overlay.ffmpeg import FFMPEG

    try:
        ffmpeg = FFMPEG()
        output = (
            ffmpeg.ffprobe().invoke(["-hide_banner", "-print_format", "json", "-show_streams", str(file_path)]).stdout
        )
        data = json.loads(str(output))
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                for sd in stream.get("side_data_list", []):
                    if "rotation" in sd:
                        rotation = abs(int(sd["rotation"]))
                        return rotation if rotation in _VALID_ROTATIONS else 0
                rotation_tag = stream.get("tags", {}).get("rotate")
                if rotation_tag:
                    rotation = abs(int(rotation_tag))
                    return rotation if rotation in _VALID_ROTATIONS else 0
    except Exception as e:
        logger.debug("Could not determine video rotation for %s: %s", file_path, e)
    return 0


def get_display_dimensions(width: int, height: int, rotation: int) -> tuple[int, int]:
    """Return (width, height) accounting for rotation."""
    if rotation in (90, 270):
        return height, width
    return width, height


def extract_video_metadata(file_path: Path) -> VideoMetadata | None:
    """Extract metadata from a video file using FFMPEGGoPro."""
    from gopro_overlay.ffmpeg import FFMPEG
    from gopro_overlay.ffmpeg_gopro import FFMPEGGoPro

    try:
        ffmpeg = FFMPEG()
        ffmpeg_gopro = FFMPEGGoPro(ffmpeg)
        recording = ffmpeg_gopro.find_recording(file_path)

        video = recording.video
        has_gps = recording.data is not None

        rotation = get_video_rotation(file_path)
        display_w, display_h = get_display_dimensions(video.dimension.x, video.dimension.y, rotation)

        # Detect embedded DJI meta GPS stream
        has_dji_meta = False
        dji_meta_point_count = None
        try:
            from gpstitch.services.dji_meta_parser import detect_dji_meta_stream, get_dji_meta_metadata

            stream_idx = detect_dji_meta_stream(file_path)
            if stream_idx is not None:
                meta = get_dji_meta_metadata(file_path, stream_index=stream_idx)
                dji_meta_point_count = meta.get("gps_point_count", 0)
                has_dji_meta = dji_meta_point_count > 0
        except Exception:
            logger.debug("DJI meta detection skipped for %s", file_path)

        return VideoMetadata(
            width=display_w,
            height=display_h,
            duration_seconds=video.duration.millis() / 1000.0,
            frame_count=video.frame_count,
            frame_rate=video.frame_rate(),
            has_gps=has_gps,
            has_dji_meta=has_dji_meta,
            dji_meta_point_count=dji_meta_point_count,
        )
    except Exception:
        logger.exception("Error extracting video metadata from %s", file_path)
        return None


def extract_gpx_fit_metadata(file_path: Path) -> GpxFitMetadata | None:
    """Extract metadata from a GPX, FIT, or SRT file."""
    try:
        if file_path.suffix.lower() == ".srt":
            from gpstitch.services.srt_parser import get_srt_metadata

            meta = get_srt_metadata(file_path)
            return GpxFitMetadata(
                gps_point_count=meta["gps_point_count"],
                duration_seconds=meta["duration_seconds"],
            )

        from gopro_overlay.loading import load_external
        from gopro_overlay.units import units

        timeseries = load_external(file_path, units)

        # Count GPS points
        point_count = len(timeseries)

        # Calculate duration if we have timestamps
        duration = None
        if point_count > 0:
            start_time = timeseries.min
            end_time = timeseries.max
            duration = (end_time - start_time).total_seconds()

        return GpxFitMetadata(
            gps_point_count=point_count,
            duration_seconds=duration,
            fit_developer_fields=extract_fit_developer_fields(file_path),
        )
    except Exception:
        logger.exception("Error extracting GPX/FIT metadata from %s", file_path)
        return None


def get_file_type(file_path: Path) -> str:
    """Determine the file type from extension."""
    suffix = file_path.suffix.lower()
    return {".mp4": "video", ".mov": "video", ".gpx": "gpx", ".fit": "fit", ".srt": "srt"}.get(suffix, "unknown")


def extract_fit_developer_fields(file_path: Path) -> list[dict]:
    """Extract developer field definitions from a FIT file.

    Returns a list of dicts with keys: name, key (snake_case), scale, offset, units.
    These represent configurable DIDs that the user can display in the overlay.
    """
    import re

    if file_path.suffix.lower() != ".fit":
        return []

    try:
        import struct
        from pathlib import Path as P

        data = file_path.read_bytes()
        if len(data) < 12 or data[8:12] != b'.FIT':
            return []

        hdr_size = data[0]
        data_size = struct.unpack('<I', data[4:8])[0]
        pos = hdr_size
        end = hdr_size + data_size

        MSG_FIELD_DESC = 206
        BASE_TYPE_SIZE = {
            0x00: 1, 0x01: 1, 0x02: 1,
            0x83: 2, 0x84: 2, 0x85: 4, 0x86: 4,
            0x07: 1, 0x88: 4, 0x89: 8,
            0x0A: 1, 0x8B: 2, 0x8C: 4,
            0x0D: 1, 0x8E: 8, 0x8F: 8, 0x90: 8,
        }

        def _decode(raw, bt):
            bt = bt & 0xFF
            if bt == 0x00:
                return raw[0]
            elif bt == 0x01:
                return struct.unpack('<b', raw[:1])[0]
            elif bt == 0x02:
                return raw[0]
            elif bt == 0x83:
                return struct.unpack('<h', raw[:2])[0]
            elif bt == 0x84:
                return struct.unpack('<H', raw[:2])[0]
            elif bt == 0x85:
                return struct.unpack('<i', raw[:4])[0]
            elif bt == 0x86:
                return struct.unpack('<I', raw[:4])[0]
            elif bt == 0x07:
                return raw.rstrip(b'\x00').decode('utf-8', errors='replace')
            elif bt == 0x88:
                return struct.unpack('<f', raw[:4])[0]
            elif bt == 0x89:
                return struct.unpack('<d', raw[:8])[0]
            else:
                return raw.hex()

        def _name_to_key(name):
            return re.sub(r'[^a-zA-Z0-9]+', '_', name).strip('_').lower()

        mesg_defs = {}
        dev_fields = {}

        while pos < end and pos < len(data):
            hdr_byte = data[pos]; pos += 1
            is_def = bool(hdr_byte & 0x40)
            local_num = hdr_byte & 0x0F

            if is_def:
                if pos + 4 > len(data):
                    break
                pos += 1  # reserved
                pos += 1  # arch
                global_num = struct.unpack('<H', data[pos:pos+2])[0]
                pos += 2
                n_fields = data[pos]; pos += 1
                fields = []
                for _ in range(n_fields):
                    if pos + 3 > len(data):
                        break
                    fields.append((data[pos], data[pos+1], data[pos+2]))
                    pos += 3
                has_dev = bool(hdr_byte & 0x20)
                if has_dev:
                    if pos >= len(data):
                        break
                    n_dev = data[pos]; pos += 1
                    for _ in range(n_dev):
                        if pos + 3 > len(data):
                            break
                        pos += 3
                mesg_defs[local_num] = (global_num, fields)
            else:
                defn = mesg_defs.get(local_num)
                if defn is None:
                    break
                global_num, fields = defn

                if global_num == MSG_FIELD_DESC:
                    msg_start = pos
                    parsed = {}
                    for field_num, size, base_type in fields:
                        if pos + size > len(data):
                            pos = end
                            break
                        raw = data[pos:pos+size]
                        parsed[field_num] = _decode(raw, base_type)
                        pos += size

                    name_val = parsed.get(3, '')
                    if isinstance(name_val, bytes):
                        name_val = name_val.rstrip(b'\x00').decode('utf-8', errors='replace')
                    name = str(name_val) if name_val else ''
                    if not name:
                        continue

                    scale_val = parsed.get(6, 0xFF)
                    if scale_val == 0xFF or scale_val is None:
                        scale_val = None
                    offset_val = parsed.get(7, 0x7F)
                    if offset_val == 0x7F or offset_val is None:
                        offset_val = None
                    units_val = parsed.get(8, '')
                    if isinstance(units_val, bytes):
                        units_val = units_val.rstrip(b'\x00').decode('utf-8', errors='replace')

                    dev_fields[name] = {
                        'name': name,
                        'key': _name_to_key(name),
                        'scale': scale_val,
                        'offset': offset_val,
                        'units': str(units_val),
                    }
                else:
                    # Skip data message — advance past all fields
                    for _, size, _ in fields:
                        if pos + size > len(data):
                            pos = end
                            break
                        pos += size

        return list(dev_fields.values())
    except Exception:
        logger.debug("Could not extract FIT developer fields from %s", file_path)
        return []
