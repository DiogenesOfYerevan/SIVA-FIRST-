# simulate_rf_openems.py - SIVA FIRST REV-4.3-DIGITAL-4096D
#
# 3D Full-Wave FDTD Electromagnetic Simulation (openEMS)
# Calculates S11 / S21 resonance peaks and phase shift for Tile T14 (910 um) vs T15 (900 um)
#
# Run:
#   python simulate_rf_openems.py
# Pass = |Delta Phase @ 11.5 GHz - 180 deg| < 10 deg

import os
import json
import tempfile
import numpy as np
import matplotlib.pyplot as plt
from CSXCAD import ContinuousStructure
from openEMS import openEMS

with open("config_die.json", "r", encoding="utf-8") as f:
    CFG = json.load(f)

ROOF_X = CFG["matrix"]["tile_x_um"]        # 1500 um
DS = CFG["dimple"]["size_um"]              # 5 um
DP = CFG["dimple"]["pitch_um"]             # 90 um
DM = CFG["dimple"]["matrix_margin_um"]     # 44 um

# Vertical stack-up parameters (Z-axis in um)
# NOTE: These are NOT in config_die.json yet - must match FAB stack-up
CAVITY_HEIGHT_UM = 2.0     # Air gap between M5_Bottom and M6_Top_Roof
DIMPLE_HEIGHT_UM = 1.65    # Dimple pillar height (leaves 0.35 um capacitive tip gap for slow-wave)
METAL_THICK_UM = 0.5       # Metal thickness (Al / Cu)

# Frequency sweep: 6.0 GHz to 13.0 GHz (covers 7.0 - 11.5 GHz band)
F_MIN = 6.0e9
F_MAX = 13.0e9
F0 = 9.5e9
FC = 3.5e9

def build_mesh_lines(length_um, n_dimple, start_um, extra_coords=None):
    """Coarse mesh + fine refinement around each dimple edge and port coordinates.
    Coarse step = 25 um, fine step = ~1-2 um around dimple.
    Without this, 5 um dimple is invisible to FDTD."""
    coarse = np.arange(0, length_um + 1, 25.0)
    fine = []
    for i in range(n_dimple):
        x0 = start_um + i * DP
        fine += [x0 - 2.0, x0, x0 + DS / 2.0, x0 + DS, x0 + DS + 2.0]
    if extra_coords:
        fine += list(extra_coords)
    lines = np.unique(np.concatenate([coarse, np.array(fine)]))
    lines = lines[(lines >= 0) & (lines <= length_um)]
    return np.sort(lines)

def run_tile_fdtd(tile_name, roof_y_um, sim_path):
    """Builds 3D cavity with dimple array and runs openEMS FDTD solver."""
    FDTD = openEMS(NrTS=60000, EndCriteria=1e-4)
    FDTD.SetGaussExcite(F0, FC)
    FDTD.SetBoundaryCond(["PEC", "PEC", "PEC", "PEC", "PEC", "PEC"])  # Closed metal cavity
    CSX = ContinuousStructure()
    FDTD.SetCSX(CSX)
    mesh = CSX.GetGrid()
    mesh.SetDeltaUnit(1e-6)  # Units in micrometers (um)

    # Materials: Al/Cu conductor and vacuum cavity
    metal = CSX.AddMetal("Conductor_Al")
    air = CSX.AddMaterial("Vacuum_Cavity", epsilon=1.0, mue=1.0)

    # 1. Bottom Ground Plane (M5_Bottom)
    metal.AddBox([0, 0, -METAL_THICK_UM], [ROOF_X, roof_y_um, 0], priority=10)

    # 2. Top Resonator Roof (M6_Top_Roof)
    z_roof_bot = CAVITY_HEIGHT_UM
    z_roof_top = CAVITY_HEIGHT_UM + METAL_THICK_UM
    metal.AddBox([0, 0, z_roof_bot], [ROOF_X, roof_y_um, z_roof_top], priority=10)

    # 3. Periodic 180-deg Anti-Phase Dimple Array ("Brush")
    nx = int((ROOF_X - 2 * DM - DS) // DP) + 1
    ny = int((roof_y_um - 2 * DM - DS) // DP) + 1
    sx = (ROOF_X - ((nx - 1) * DP + DS)) / 2.0
    sy = (roof_y_um - ((ny - 1) * DP + DS)) / 2.0
    z_dimple_bot = CAVITY_HEIGHT_UM - DIMPLE_HEIGHT_UM
    for ix in range(nx):
        for iy in range(ny):
            x0 = sx + ix * DP
            y0 = sy + iy * DP
            metal.AddBox([x0, y0, z_dimple_bot], [x0 + DS, y0 + DS, z_roof_bot], priority=10)

    # 4. Non-uniform FDTD Mesh - FINE around dimples, ports, and capacitive tip gap
    port_x_coords = [ROOF_X / 2.0 - 10.0, ROOF_X / 2.0, ROOF_X / 2.0 + 10.0]
    port_y_coords = [20.0, roof_y_um - 20.0]
    mesh.SetLines("x", build_mesh_lines(ROOF_X, nx, sx, port_x_coords))
    mesh.SetLines("y", build_mesh_lines(roof_y_um, ny, sy, port_y_coords))
    mesh.SetLines(
        "z",
        [-METAL_THICK_UM, 0.0, 0.08, 0.17, 0.26, z_dimple_bot, 0.7, 1.2, 1.6, z_roof_bot, z_roof_top],
    )

    # 5. Input / Output Lumped Ports (Coupling at cavity edges)
    port1 = FDTD.AddLumpedPort(
        1, 50, [ROOF_X / 2 - 10, 20, 0], [ROOF_X / 2 + 10, 20, CAVITY_HEIGHT_UM], "z", 1.0, priority=20
    )
    port2 = FDTD.AddLumpedPort(
        2, 50, [ROOF_X / 2 - 10, roof_y_um - 20, 0], [ROOF_X / 2 + 10, roof_y_um - 20, CAVITY_HEIGHT_UM], "z", 0.0, priority=20
    )

    print(f"[{tile_name}] Running 3D FDTD: Roof={ROOF_X}x{roof_y_um} um, Dimples={nx}x{ny}={nx*ny}...")
    FDTD.Run(sim_path, verbose=0)

    freqs = np.linspace(F_MIN, F_MAX, 701)
    port1.CalcPort(sim_path, freqs)
    port2.CalcPort(sim_path, freqs)
    s11 = port1.uf_ref / port1.uf_inc
    s21 = port2.uf_ref / port1.uf_inc  # FIX: incident wave is from port 1 only, port 2 uf_inc = 0
    return freqs, s11, s21

if __name__ == "__main__":
    base_tmp = tempfile.mkdtemp(prefix="siva_rf_")

    # Simulate Phase-Reference Pair at 11.5 GHz: Tile 14 (910 um) vs Tile 15 (900 um)
    f14, s11_14, s21_14 = run_tile_fdtd("Tile_14_Ref", 910, os.path.join(base_tmp, "t14"))
    f15, s11_15, s21_15 = run_tile_fdtd("Tile_15_Shift", 900, os.path.join(base_tmp, "t15"))

    # Phase difference at 11.5 GHz
    idx_115 = np.argmin(np.abs(f14 - 11.5e9))
    phase_14 = np.angle(s21_14[idx_115], deg=True)
    phase_15 = np.angle(s21_15[idx_115], deg=True)
    delta_phi = (phase_15 - phase_14 + 180) % 360 - 180

    print(f"\n--- SIVA FIRST 3D EM RESULTS @ 11.5 GHz ---")
    print(f"Tile 14 (910 um): |S11| = {20*np.log10(np.abs(s11_14[idx_115])):.2f} dB, Phase(S21) = {phase_14:.2f} deg")
    print(f"Tile 15 (900 um): |S11| = {20*np.log10(np.abs(s11_15[idx_115])):.2f} dB, Phase(S21) = {phase_15:.2f} deg")
    print(f"Differential Phase Shift (T15 - T14) = {delta_phi:.2f} deg")

    # PASS / FAIL - do not claim 180 deg without this check
    err = abs(abs(delta_phi) - 180.0)
    if err < 10.0:
        print(f"PASS: Delta Phase = {delta_phi:.2f} deg (error {err:.2f} deg < 10 deg)")
    else:
        print(f"FAIL: Delta Phase = {delta_phi:.2f} deg (error {err:.2f} deg >= 10 deg) - pair 910/900 does NOT give 180 deg")

    # Plot S-parameters and Phase
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 7), sharex=True)
    ax1.plot(f14 / 1e9, 20 * np.log10(np.abs(s21_14)), label="T14 (910 um) |S21| dB")
    ax1.plot(f15 / 1e9, 20 * np.log10(np.abs(s21_15)), "--", label="T15 (900 um) |S21| dB")
    ax1.axvline(11.5, color="red", linestyle=":", label="11.5 GHz Target")
    ax1.set_ylabel("Transmission |S21| (dB)")
    ax1.set_title("SIVA FIRST REV-4.3: 3D EM Resonance & Phase Shift (openEMS)")
    ax1.grid(True)
    ax1.legend()

    ax2.plot(f14 / 1e9, np.unwrap(np.angle(s21_14)) * 180 / np.pi, label="T14 Phase (deg)")
    ax2.plot(f15 / 1e9, np.unwrap(np.angle(s21_15)) * 180 / np.pi, "--", label="T15 Phase (deg)")
    ax2.axvline(11.5, color="red", linestyle=":")
    ax2.set_xlabel("Frequency (GHz)")
    ax2.set_ylabel("Unwrapped Phase (deg)")
    ax2.grid(True)
    ax2.legend()

    plt.tight_layout()
    plt.savefig("siva_rf_signoff.png", dpi=200)
    print("Saved plot: siva_rf_signoff.png")
