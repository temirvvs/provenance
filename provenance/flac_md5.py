import struct


def flac_md5(path):
    """Read the MD5 signature from a FLAC file's STREAMINFO metadata block.
    Returns the 32-hex-char signature or None if not a FLAC / no STREAMINFO.
    A signature of all zeros means 'unset'."""
    with open(path, "rb") as f:
        if f.read(4) != b"fLaC":
            return None
        while True:
            header = f.read(4)
            if len(header) != 4:
                return None
            last = header[0] & 0x80
            block_type = header[0] & 0x7F
            length = struct.unpack(">I", b"\x00" + header[1:4])[0]
            if block_type == 0:  # STREAMINFO
                if length < 18:
                    return None
                payload = f.read(length)
                if len(payload) < 34:
                    return None
                return payload[18:34].hex()
            if length:
                f.seek(length, 1)
            if last:
                return None
