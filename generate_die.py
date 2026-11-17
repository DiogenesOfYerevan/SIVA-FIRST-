import json, struct, os, datetime
with open('config_die.json') as f:
    cfg = json.load(f)

scale = 1000
mm_scale = 1000000
tiles_x = cfg["tiles_grid_x"]
tiles_y = cfg["tiles_grid_y"]
az = int(cfg["tile_active_zone_size_mm"] * mm_scale)
tile_pitch = int(cfg["tile_pitch_um"] * scale)
tw = int(cfg["trench_width_um"] * scale)
sw = int(cfg["seal_width_um"] * scale)
gap_trench_seal = 1 * scale
die_total = int(cfg["die_size_total_mm"] * mm_scale)
half_die = die_total // 2
half_az = az // 2
pin_w = int(cfg["cpw_central_pin_um"] * scale)
gap_w = int(cfg["cpw_gap_um"] * scale)
spacing = int(cfg["ports_spacing_um"] * scale)
dimple_s = int(cfg["dimple_size_um"] * scale)
grid_x = cfg["dimple_grid_per_tile_x"]
fixed_pitch = int(cfg["dimple_pitch_um"] * scale)
die_margin = int(cfg["matrix_margin_um"] * scale)

HEADER, BGNLIB, LIBNAME, UNITS, ENDLIB = 0x0002, 0x0102, 0x0206, 0x0305, 0x0400
BGNSTR, STRNAME, ENDSTR, BOUNDARY, LAYER = 0x0502, 0x0606, 0x0700, 0x0800, 0x0d02
DATATYPE, XY, ENDEL, TEXT, TEXTTYPE = 0x0e02, 0x1003, 0x1100, 0x0c02, 0x1602
PRESENTATION, STRING = 0x1701, 0x1906

def rec(t, d=b''): return struct.pack('>HH', len(d) + 4, t) + d
def add_box(l, dt, x1, y1, x2, y2):
    pts = struct.pack('>10i', x1, y1, x1, y2, x2, y2, x2, y1, x1, y1)
    return rec(BOUNDARY) + rec(LAYER, struct.pack('>H', l)) + rec(DATATYPE, struct.pack('>H', dt)) + rec(XY, pts) + rec(ENDEL)
def add_label(l, tt, x, y, s):
    b = s.encode('ascii')
    if len(b) % 2: b += b'\x00'
    return rec(TEXT) + rec(LAYER, struct.pack('>H', l)) + rec(TEXTTYPE, struct.pack('>H', tt)) + rec(PRESENTATION, struct.pack('>H', 5)) + rec(XY, struct.pack('>2i', x, y)) + rec(STRING, b) + rec(ENDEL)

def build_gds(cell, boxes, labels):
    now = datetime.datetime.now()
    gds = rec(HEADER, struct.pack('>H', 600))
    gds += rec(BGNLIB, struct.pack('>12h', now.year, now.month, now.day, now.hour, now.minute, now.second, now.year, now.month, now.day, now.hour, now.minute, now.second))
    gds += rec(LIBNAME, b'SIVA_DIE_LIB\x00')
    gds += rec(UNITS, struct.pack('>dd', 0.001, 1e-9))
    gds += rec(BGNSTR, struct.pack('>12h', now.year, now.month, now.day, now.hour, now.minute, now.second, now.year, now.month, now.day, now.hour, now.minute, now.second))
    gds += rec(STRNAME, cell.encode() + b'\x00')
    for bx in boxes: gds += add_box(*bx)
    for lb in labels: gds += add_label(*lb)
    gds += rec(ENDSTR) + rec(ENDLIB)
    return gds

start_tile_x = -(tiles_x - 1) * tile_pitch // 2
start_tile_y = -(tiles_y - 1) * tile_pitch // 2
shift_x = spacing // 2
slot_half = pin_w // 2 + gap_w
pad_size = 100 * scale
pitch = 150 * scale
y_pad = -700 * scale
local_pad_centers_x = [-200*scale-pitch, -200*scale, -200*scale+pitch, 200*scale-pitch, 200*scale, 200*scale+pitch]

base_boxes, labels, cap_boxes = [], [], []
frequencies = [[7.0,7.3,7.6,7.9],[8.2,8.5,8.8,9.1],[9.4,9.7,10.0,10.3],[10.6,10.9,11.2,11.5]]
total_dimples = 0

for tx in range(tiles_x):
    for ty in range(tiles_y):
        t_cx = start_tile_x + tx * tile_pitch
        t_cy = start_tile_y + ty * tile_pitch
        freq = frequencies[ty][tx]
        length_reduction = int((freq - 7.0) * 300 * scale / 4.5)
        current_half_az_y = half_az - length_reduction
        base_boxes += [(31,0,t_cx-half_az,t_cy-current_half_az_y,t_cx-shift_x-slot_half,t_cy),(31,0,t_cx-shift_x+slot_half,t_cy-current_half_az_y,t_cx+shift_x-slot_half,t_cy),(31,0,t_cx+shift_x+slot_half,t_cy-current_half_az_y,t_cx+half_az,t_cy),(31,0,t_cx-half_az,t_cy,t_cx+half_az,t_cy+current_half_az_y)]
        base_boxes += [(31,0,t_cx-shift_x-pin_w//2,t_cy-current_half_az_y,t_cx-shift_x+pin_w//2,t_cy+y_pad+pad_size//2),(31,0,t_cx+shift_x-pin_w//2,t_cy-current_half_az_y,t_cx+shift_x+pin_w//2,t_cy+y_pad+pad_size//2)]
        for cx in local_pad_centers_x:
            gx,gy = t_cx+cx, t_cy+y_pad
            base_boxes.append((31,0,gx-pad_size//2,gy-pad_size//2,gx+pad_size//2,gy+pad_size//2))
            base_boxes.append((33,0,gx-pad_size//2,gy-pad_size//2,gx+pad_size//2,gy+pad_size//2))
            v_start_x,v_start_y = gx-pad_size//2+1000, gy-pad_size//2+1000
            for vx in range(0,pad_size-2000,10000):
                for vy in range(0,pad_size-2000,10000):
                    base_boxes.append((38,0,v_start_x+vx,v_start_y+vy,v_start_x+vx+2000,v_start_y+vy+2000))
        for idx,name in enumerate(["DIG_IN_G1","DIG_IN_S","DIG_IN_G2","DIG_OUT_G1","DIG_OUT_S","DIG_OUT_G2"]):
            labels.append((33,0,t_cx+local_pad_centers_x[idx],t_cy+y_pad,f"T{tx}{ty}{name}"))
        labels.append((32,0,t_cx,t_cy,f"CORE{freq}GHz"))
        cap_boxes.append((32,0,t_cx-half_az,t_cy-current_half_az_y,t_cx+half_az,t_cy+current_half_az_y))
        grid_y_calc = int((current_half_az_y*2 - dimple_s) // fixed_pitch) + 1
        while grid_y_calc > 1 and (current_half_az_y*2 - ((grid_y_calc-1)*fixed_pitch + dimple_s)) / 2 < die_margin:
            grid_y_calc -= 1
        start_d_x = t_cx - (grid_x - 1) * fixed_pitch // 2
        start_d_y = t_cy - (grid_y_calc - 1) * fixed_pitch // 2
        for ix in range(grid_x):
            for iy in range(grid_y_calc):
                dx = start_d_x + ix * fixed_pitch
                dy = start_d_y + iy * fixed_pitch
                cap_boxes.append((45,0,dx-dimple_s//2,dy-dimple_s//2,dx+dimple_s//2,dy+dimple_s//2))
        total_dimples += grid_x * grid_y_calc

base_boxes += [(100,0,-half_die,-half_die,-half_die+tw,half_die),(100,0,half_die-tw,-half_die,half_die,half_die)]
base_boxes += [(100,0,-half_die,-half_die,half_die,-half_die+tw),(100,0,-half_die,half_die-tw,half_die,half_die)]
die_sr_outer = half_die - tw - gap_trench_seal
base_boxes += [(90,0,-die_sr_outer,-die_sr_outer,-die_sr_outer+sw,die_sr_outer),(90,0,die_sr_outer-sw,-die_sr_outer,die_sr_outer,die_sr_outer)]
base_boxes += [(90,0,-die_sr_outer,-die_sr_outer,die_sr_outer,-die_sr_outer+sw),(90,0,-die_sr_outer,die_sr_outer-sw,die_sr_outer,die_sr_outer)]

open('SIVA_MATRIX_BASE.gds','wb').write(build_gds('SIVA_MATRIX_BASE',base_boxes,labels))
open('SIVA_MATRIX_CAP.gds','wb').write(build_gds('SIVA_MATRIX_CAP',cap_boxes,[]))
print(f"GDS OK FINAL 4.3: BASE {len(base_boxes)} CAP {len(cap_boxes)} DIMPLES {total_dimples} PITCH 90um MIN_MARGIN 44um")
