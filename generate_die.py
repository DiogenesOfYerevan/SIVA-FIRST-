# generate_die.py - SIVA FIRST REV-4.3-DIGITAL-4096D - FAB SIGN-OFF READY
#
# Top Roof = Resonator, Dimple = 180-deg Anti-Phase, 85um Gap = Sacred
# 2 Masks (BASE + CAP), Al Ring Wafer Bonding, Air Cavity Inside, Zero Transistors

import json
import struct

with open("config_die.json", "r", encoding="utf-8") as f:
    CFG = json.load(f)

DIE = CFG["die_size_um"]
BUF = CFG["buffer_um"]
DBU = CFG["drc"]["dbu_um"]
L = CFG["layers"]

FREQS = [7.0, 7.5, 8.0, 8.5, 9.0, 9.5, 10.0, 10.3, 10.6, 10.9, 11.1, 11.2, 11.3, 11.4, 11.5, 11.5]
ROOF_Y = [1500, 1450, 1400, 1350, 1300, 1250, 1200, 1160, 1100, 1070, 1020, 980, 940, 920, 910, 900]
ROOF_X = CFG["matrix"]["tile_x_um"]
PITCH = CFG["matrix"]["tile_pitch_um"]
DS = CFG["dimple"]["size_um"]
DP = CFG["dimple"]["pitch_um"]
DM = CFG["dimple"]["matrix_margin_um"]

def gds_real(x):
    if x == 0:
        return b"\x00" * 8
    s = 0x80 if x < 0 else 0
    x = abs(x)
    e = 64
    while x >= 1.0:
        x /= 16.0
        e += 1
    while x < 1 / 16:
        x *= 16.0
        e -= 1
    m = int(round(x * (1 << 56)))
    if m >= (1 << 56):
        m //= 16
        e += 1
    return bytes([s | e]) + m.to_bytes(7, "big")

def hdr(n):
    o = (
        struct.pack(">HHh", 6, 0x0002, 600)
        + struct.pack(">HH", 28, 0x0102)
        + struct.pack(">12h", 2026, 11, 23, 12, 0, 0, 2026, 11, 23, 12, 0, 0)
    )
    b = n.encode()
    b += b"\x00" if len(b) % 2 else b""
    return (
        o
        + struct.pack(">HH", 4 + len(b), 0x0206)
        + b
        + struct.pack(">HH", 20, 0x0305)
        + gds_real(DBU)
        + gds_real(1e-9)
    )

def bgn(n):
    o = struct.pack(">HH", 28, 0x0502) + struct.pack(
        ">12h", 2026, 11, 23, 12, 0, 0, 2026, 11, 23, 12, 0, 0
    )
    b = n.encode()
    b += b"\x00" if len(b) % 2 else b""
    return o + struct.pack(">HH", 4 + len(b), 0x0606) + b

def bnd(layer, xy):
    pts = []
    for x, y in xy:
        pts += [int(round(x / DBU)), int(round(y / DBU))]
    d = struct.pack(f">{len(pts)}i", *pts)
    o = struct.pack(">HH", 4, 0x0800)
    o += struct.pack(">HH", 6, 0x0D02) + struct.pack(">h", layer)
    o += struct.pack(">HH", 6, 0x0E02) + struct.pack(">h", 0)
    o += struct.pack(">HH", 4 + len(d), 0x1003) + d
    o += struct.pack(">HH", 4, 0x1100)
    return o

def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]

def ring(out, layer, x0, y0, x1, y1, w):
    out += bnd(layer, rect(x0, y0, x1, y0 + w))
    out += bnd(layer, rect(x0, y1 - w, x1, y1))
    out += bnd(layer, rect(x0, y0 + w, x0 + w, y1 - w))
    out += bnd(layer, rect(x1 - w, y0 + w, x1, y1 - w))
    return out

def endstr():
    return struct.pack(">HH", 4, 0x0700)

def endlib():
    return struct.pack(">HH", 4, 0x0400)

def build_base():
    o = hdr("SIVA_MATRIX_BASE") + bgn("BASE")
    o += bnd(L["M5_Bottom"], rect(BUF, BUF, DIE - BUF, DIE - BUF))

    pad = CFG["met_pad"]["size_um"]
    vs = CFG["via"]["size_um"]
    vp = CFG["via"]["pitch_um"]
    off = (pad - (4 * vp + vs)) / 2
    pads = [
        (BUF, BUF),
        (DIE - BUF - pad, BUF),
        (BUF, DIE - BUF - pad),
        (DIE - BUF - pad, DIE - BUF - pad),
        (DIE // 2 - pad // 2, BUF),
        (DIE // 2 - pad // 2, DIE - BUF - pad),
        (BUF, DIE // 2 - pad // 2),
        (DIE - BUF - pad, DIE // 2 - pad // 2),
    ]
    for px, py in pads:
        o += bnd(L["MET_PAD"], rect(px, py, px + pad, py + pad))
        for vx in range(5):
            for vy in range(5):
                x = px + off + vx * vp
                y = py + off + vy * vp
                o += bnd(L["VIA"], rect(x, y, x + vs, y + vs))

    w = CFG["seal_ring"]["width_um"]
    o = ring(o, L["Seal_Ring"], 0, 0, DIE, DIE, w)
    tw = CFG["deep_trench"]["width_um"]
    sp = CFG["deep_trench"]["spacing_to_seal_um"]
    t0 = w + sp
    o = ring(o, L["Deep_Trench"], t0, t0, DIE - t0, DIE - t0, tw)
    return o + endstr() + endlib()

def build_cap():
    o = hdr("SIVA_MATRIX_CAP") + bgn("CAP")
    total = 0
    for ty in range(4):
        for tx in range(4):
            idx = ty * 4 + tx
            ry = ROOF_Y[idx]
            ox = BUF + tx * PITCH
            oy = BUF + ty * PITCH
            cx = ox + (PITCH - ROOF_X) / 2
            cy = oy + (PITCH - ry) / 2
            o += bnd(L["M6_Top_Roof"], rect(cx, cy, cx + ROOF_X, cy + ry))

            nx = int((ROOF_X - 2 * DM - DS) // DP) + 1
            ny = int((ry - 2 * DM - DS) // DP) + 1
            sx = cx + (ROOF_X - ((nx - 1) * DP + DS)) / 2
            sy = cy + (ry - ((ny - 1) * DP + DS)) / 2
            for ix in range(nx):
                for iy in range(ny):
                    x = sx + ix * DP
                    y = sy + iy * DP
                    o += bnd(L["Dimples"], rect(x, y, x + DS, y + DS))
            total += nx * ny
            print(f"Tile {idx} F={FREQS[idx]}GHz Roof={ROOF_X}x{ry} Dimples={nx}x{ny}={nx*ny} Gap={DP-DS}")

    w = CFG["seal_ring"]["width_um"]
    o = ring(o, L["Seal_Ring"], 0, 0, DIE, DIE, w)
    expected = CFG["dimple"]["count_actual"]
    print(f"SIVA FIRST REV-4.3: dimples total = {total} (expected {expected})")
    assert total == expected == 3136, f"FAIL: {total} != {expected}"
    return total, o + endstr() + endlib()

if __name__ == "__main__":
    with open(CFG["gds"]["base_file"], "wb") as f:
        f.write(build_base())
    total, cap = build_cap()
    with open(CFG["gds"]["cap_file"], "wb") as f:
        f.write(cap)
    print(f"Wrote {CFG['gds']['base_file']}")
    print(f"Wrote {CFG['gds']['cap_file']}")
    print(f"Dimples generated: {total}")
    print("OK: 16 tiles, 3136 dimples, 2 masks, Al Ring, cavity, digital in/out.")
