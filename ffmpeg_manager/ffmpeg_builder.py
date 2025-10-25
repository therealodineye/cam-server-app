SPLIT_TYPE_VERTICAL = "vertical"
SPLIT_TYPE_HORIZONTAL = "horizontal"


def _get_bitrate_in_k(rate_str):
    rate_str = rate_str.lower()
    if "m" in rate_str:
        return int(float(rate_str.replace("m", ""))) * 1000
    elif "k" in rate_str:
        return int(float(rate_str.replace("k", "")))
    return int(rate_str)


def get_input_url(camera_config):
    cam_info = camera_config["camera"]
    ip = cam_info["ip"]
    rtsp_path = cam_info.get("rtsp_path", "/stream1")

    if "user=" in rtsp_path and "password=" in rtsp_path:
        return f"rtsp://{ip}:554{rtsp_path}"

    user, password = cam_info["user"], cam_info["pass"]
    return f"rtsp://{user}:{password}@{ip}:554{rtsp_path}"


def get_codec_parameters(processing_config, hwaccel_enabled):
    input_codec = processing_config.get("input_codec", "h264")
    output_codec = processing_config.get("output_codec", "copy")
    details = {
        "codec": output_codec
    }

    if hwaccel_enabled:
        if input_codec == "h265":
            input_params = ["-c:v", "hevc_cuvid"]
        else:
            input_params = ["-c:v", "h264_cuvid"]

        if output_codec == "copy":
            output_params = ["-c:v", "copy"]
        elif output_codec == "h265":
            output_params = ["-c:v", "hevc_nvenc", "-preset", "p5"]
        else:
            output_params = ["-c:v", "h264_nvenc", "-preset", "p5"]
    else:
        input_params = []
        if output_codec == "copy":
            output_params = ["-c:v", "copy"]
        else:
            output_params = ["-c:v", "libx264"]

    output_option_params = []
    if output_codec != "copy":
        bitrate = processing_config.get("bitrate", "2M")
        maxrate = processing_config.get("maxrate", "4M")
        details["bitrate"] = bitrate

        maxrate_k = _get_bitrate_in_k(maxrate)
        bufsize_k = maxrate_k * 2

        output_option_params.extend(
            ["-b:v", bitrate, "-maxrate", maxrate, "-bufsize", f"{bufsize_k}k"]
        )

        keyframe_interval = processing_config.get("keyframe_interval")
        if keyframe_interval:
            output_option_params.extend(["-g", str(keyframe_interval)])

    return input_params, output_params, output_option_params, details


def build_ffmpeg_command(camera_config):
    cam_info = camera_config["camera"]
    cam_name = cam_info["name"]
    input_url = get_input_url(camera_config)
    processing_config = cam_info.get("processing", {})
    hwaccel_enabled = processing_config.get("hwaccel", True)

    input_codec_params, output_codec_params, output_option_params, codec_details = (
        get_codec_parameters(processing_config, hwaccel_enabled)
    )

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
    ]

    if hwaccel_enabled:
        cmd += [
            "-hwaccel",
            "cuda",
            "-hwaccel_output_format",
            "cuda",
        ]

    cmd += input_codec_params + [
        "-fflags",
        "nobuffer",
        "-flags",
        "low_delay",
        "-analyzeduration",
        "500000",
        "-probesize",
        "500000",
        "-timeout",
        "15000000",
        "-rtsp_transport",
        "tcp",
        "-i",
        input_url,
    ]

    split_config = processing_config.get("split", {})
    details = {
        "camera": cam_name,
        "splitting": "Enabled" if split_config.get("enabled", False) else "Disabled",
        "audio": "copy" if not split_config.get("enabled", False) else "part2 only",
    }
    details.update(codec_details)

    if split_config.get("enabled", False):
        split_type = split_config.get("type", SPLIT_TYPE_VERTICAL)
        if split_type == SPLIT_TYPE_HORIZONTAL:
            crop1, crop2 = ("crop=w=iw:h=ih/2:x=0:y=0", "crop=w=iw:h=ih/2:x=0:y=in_h/2")
        else:
            crop1, crop2 = ("crop=w=iw/2:h=ih:x=0:y=0", "crop=w=iw/2:h=ih:x=in_w/2:y=0")

        if hwaccel_enabled:
            filter_graph = (
                f"[0:v]hwdownload,format=nv12,split=2[split1][split2];"
                f"[split1]{crop1}[part1];[split2]{crop2}[part2]"
            )
        else:
            filter_graph = (
                f"[0:v]split=2[split1][split2];"
                f"[split1]{crop1}[part1];[split2]{crop2}[part2]"
            )

        cmd += ["-filter_complex", filter_graph]

        cmd += [
            "-map", "[part1]",
            "-an",
            *output_codec_params,
            *output_option_params,
            "-f", "rtsp",
            "-rtsp_transport", "tcp",
            f"rtsp://mediamtx:8554/{cam_name}_part1",
            "-map", "[part2]",
            "-map", "0:a?",
            "-c:a", "copy",
            *output_codec_params,
            *output_option_params,
            "-f", "rtsp",
            "-rtsp_transport", "tcp",
            f"rtsp://mediamtx:8554/{cam_name}_part2",
        ]
    else:
        cmd += [
            "-map", "0:v",
            "-map", "0:a?",
            "-c:a", "copy",
            *output_codec_params,
            *output_option_params,
            "-f", "rtsp",
            "-rtsp_transport", "tcp",
            f"rtsp://mediamtx:8554/{cam_name}",
        ]

    return cmd, details
