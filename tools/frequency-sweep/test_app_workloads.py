"""CPU-only checks of the application workloads in app_workloads.py. No GPU, no clocks touched.

Each port is checked against an independent float64 reference written here in plain loops, so an
error in the vectorised version cannot be shared by its check.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import torch  # noqa: E402
except ImportError:
    # CI installs requirements.txt only, which has no PyTorch; the workloads cannot exist without it.
    print("[SKIP] PyTorch is not installed, so the application workloads cannot be built or checked here.")
    sys.exit(0)
import app_workloads as app  # noqa: E402

passed = 0


def check(description, condition):
    global passed
    if not condition:
        print("  [FAIL] " + description)
        raise AssertionError(description)
    passed += 1
    print("  [PASS] " + description)


# --- CNN graphs: the torchvision architectures, recognised by their exact parameter counts.
for name, expected in (("alexnet", 61_100_840), ("resnet50", 25_557_032)):
    model, images = app.build_cnn(name, torch.device("cpu"), torch, batch=2)
    count = sum(p.numel() for p in model.parameters())
    check(f"{name} has torchvision's parameter count ({expected:,})", count == expected)
    with torch.inference_mode():
        logits = model(images)
    check(f"{name} gives finite, non-constant 1000-class logits", logits.shape == (2, 1000)
          and bool(torch.isfinite(logits).all()) and float(logits.std()) > 0)
    again, images2 = app.build_cnn(name, torch.device("cpu"), torch, batch=2)
    same = all(torch.equal(a, b) for a, b in zip(model.state_dict().values(), again.state_dict().values()))
    check(f"{name} weights and inputs are identical across builds", same and torch.equal(images, images2))

# --- k-means against a float64 reference Lloyd.
data, initial = app.kmeans_inputs(torch, points=4096, features=8, clusters=4)
check("k-means mixture has the declared shape and per-cluster means",
      data.shape == (4096, 8) and abs(float(data[:1024, 0].mean()) - (-8.0)) < 0.2
      and abs(float(data[1024:2048, 0].mean()) - 8.0) < 0.2)
centres, member, inertia = app.kmeans_task(data, initial, torch, updates=5)


def reference_kmeans(points, start, updates):
    pts = points.double().tolist()
    cen = start.double().tolist()
    k = len(cen)
    for _ in range(updates + 1):
        assign = []
        for p in pts:
            d = [sum((a - b) ** 2 for a, b in zip(p, c)) for c in cen]
            assign.append(min(range(k), key=lambda i: (d[i], i)))
        if _ == updates:
            break
        new = []
        for i in range(k):
            rows = [p for p, a in zip(pts, assign) if a == i]
            new.append([sum(col) / len(rows) for col in zip(*rows)] if rows else cen[i])
        cen = new
    total = sum(sum((a - b) ** 2 for a, b in zip(p, cen[i])) for p, i in zip(pts, assign))
    return cen, assign, total


ref_centres, ref_member, ref_inertia = reference_kmeans(data, initial, 5)
check("k-means memberships match the float64 reference exactly", member.tolist() == ref_member)
check("k-means centres match the reference to 1e-4",
      max(abs(a - b) for row, ref in zip(centres.tolist(), ref_centres) for a, b in zip(row, ref)) < 1e-4)
check("k-means inertia matches the reference to 1e-4 relative", abs(float(inertia) - ref_inertia) / ref_inertia < 1e-4)
lonely = torch.tensor([[0.0, 0.0], [0.1, 0.0], [100.0, 100.0]])
kept = app.kmeans_task(torch.tensor([[0.0, 0.0], [0.2, 0.0]]), lonely, torch, updates=2)[0]
check("an empty cluster keeps its previous centre", kept[2].tolist() == [100.0, 100.0])

# --- HotSpot against a float64 loop with clamped edges.
grid, batch, steps = 16, 2, 4
temperature, power = app.hotspot_inputs(torch, grid=grid, batch=batch)
fast = app.hotspot_task(temperature, power, torch, steps=steps)
step, rx, ry, rz = app.hotspot_coefficients(grid)
T = temperature.double().tolist()
P = power.double().tolist()
for _ in range(steps):
    nxt = []
    for b in range(batch):
        plane = []
        for i in range(grid):
            row = []
            for j in range(grid):
                c = T[b][i][j]
                n = T[b][max(i - 1, 0)][j]; s = T[b][min(i + 1, grid - 1)][j]
                w = T[b][i][max(j - 1, 0)]; e = T[b][i][min(j + 1, grid - 1)]
                row.append(c + step * (P[b][i][j] + (s + n - 2 * c) / ry + (e + w - 2 * c) / rx + (80.0 - c) / rz))
            plane.append(row)
        nxt.append(plane)
    T = nxt
worst = max(abs(a - b) for pf, pr in zip(fast.tolist(), T) for rf, rr in zip(pf, pr) for a, b in zip(rf, rr))
check("HotSpot matches a float64 clamped-edge reference to 1e-3 C", worst < 1e-3)
still = app.hotspot_task(torch.full((1, 8, 8), 80.0), torch.zeros((1, 8, 8)), torch, steps=10)
check("a uniform ambient field with no power stays at ambient", float((still - 80.0).abs().max()) < 1e-4)
s, rx, ry, rz = app.hotspot_coefficients(app.HOTSPOT_GRID)
check("the registered grid is stable at Rodinia's timestep", s * (2 / rx + 2 / ry + 1 / rz) < 1.0)
check("the batch's power maps differ between instances and each sums to 180 W",
      not torch.equal(power[0], power[1]) and all(abs(float(p.double().sum()) - 180.0) < 1e-3 for p in power))

print(f"\n{passed} checks passed.")
