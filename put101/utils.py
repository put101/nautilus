def print_bytes(n_bytes: int, use_iec_binary=True):
    # print the bytes in a human-readable format
    # according to this table: https://en.wikipedia.org/wiki/Byte#Multiple-byte_units

    if use_iec_binary:
        units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]
        base = 1024
    else:
        units = ["B", "KB", "MB", "GB", "TB", "PB"]
        base = 1000

    for unit in units:
        if n_bytes < base:
            print(f"{n_bytes:.1f} {unit}")
            return
        n_bytes /= base

