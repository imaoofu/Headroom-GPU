"""Application workloads for gpu_workload.py: two CNN inference graphs and two scientific codes.

Designed from GPT Job 60 (docs/gpt-findings/2026-10-07-real-workload-scoping.md), written
2026-10-08. One call of a built step() is one complete TASK, and throughput is reported in tasks
(or images) per second, not FLOP/s:

    alexnet   - one full AlexNet forward pass over a batch of 16 images      unit image/s
    resnet50  - one full ResNet-50 (v1.5, [3,4,6,3] bottlenecks) forward pass, batch 16   image/s
    kmeans    - one complete Lloyd k-means run: 20 updates + a final assignment and inertia   task/s
    hotspot   - one HotSpot transient thermal simulation: 100 explicit steps over a batch of
                chip temperature fields, Rodinia's physical constants                        task/s

What these are, and are not, stated here so it travels with the numbers:
- The CNNs are the torchvision architectures written out in torch.nn (no torchvision import),
  with **seeded random weights** (torchvision's own initialisation scheme) and a **seeded
  synthetic input batch**, not pretrained checkpoints or photographs. The arithmetic per image is
  the trained network's; the values are not, and switching activity (and so power) can differ
  from a trained network's by an unmeasured amount. No download is needed.
- k-means and HotSpot are this project's eager PyTorch ports of the algorithms, on deterministic
  generated inputs. They are not the Rodinia CUDA binaries, and do not reproduce Rodinia's
  convergence stopping rule (k-means) or temporal tiling (HotSpot).
- Sizes are chosen so GPU work, not kernel-launch overhead, dominates on an RTX 5060 Ti; that is a
  pilot decision recorded in the registration, not a property of the original applications.

Every builder is deterministic: same seed, same inputs, same task, whatever the clock.
"""

import math

APP_WORKLOADS = ("alexnet", "resnet50", "kmeans", "hotspot")
SEED = 20261008

CNN_BATCH = 16
CNN_IMAGE = 224
KMEANS_POINTS = 1_048_576
KMEANS_FEATURES = 32
KMEANS_CLUSTERS = 16
KMEANS_UPDATES = 20
HOTSPOT_GRID = 1024
HOTSPOT_BATCH = 16
HOTSPOT_STEPS = 100

# Rodinia hotspot.cu constants (commit 9c10d3e, read for GPT Job 60).
T_CHIP = 0.0005
CHIP_HEIGHT = 0.016
CHIP_WIDTH = 0.016
AMB_TEMP = 80.0
SPEC_HEAT_SI = 1.75e6
K_SI = 100.0
FACTOR_CHIP = 0.5
MAX_PD = 3.0e6
PRECISION = 0.001


def _alexnet(nn):
    class AlexNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.features = nn.Sequential(
                nn.Conv2d(3, 64, 11, stride=4, padding=2), nn.ReLU(inplace=True), nn.MaxPool2d(3, 2),
                nn.Conv2d(64, 192, 5, padding=2), nn.ReLU(inplace=True), nn.MaxPool2d(3, 2),
                nn.Conv2d(192, 384, 3, padding=1), nn.ReLU(inplace=True),
                nn.Conv2d(384, 256, 3, padding=1), nn.ReLU(inplace=True),
                nn.Conv2d(256, 256, 3, padding=1), nn.ReLU(inplace=True), nn.MaxPool2d(3, 2))
            self.avgpool = nn.AdaptiveAvgPool2d((6, 6))
            self.classifier = nn.Sequential(
                nn.Dropout(0.5), nn.Linear(256 * 36, 4096), nn.ReLU(inplace=True),
                nn.Dropout(0.5), nn.Linear(4096, 4096), nn.ReLU(inplace=True), nn.Linear(4096, 1000))

        def forward(self, x):
            x = self.avgpool(self.features(x))
            return self.classifier(x.flatten(1))
    return AlexNet()


def _resnet50(nn):
    class Bottleneck(nn.Module):
        expansion = 4

        def __init__(self, inplanes, planes, stride=1, downsample=None):
            super().__init__()
            self.conv1 = nn.Conv2d(inplanes, planes, 1, bias=False)
            self.bn1 = nn.BatchNorm2d(planes)
            self.conv2 = nn.Conv2d(planes, planes, 3, stride=stride, padding=1, bias=False)  # v1.5
            self.bn2 = nn.BatchNorm2d(planes)
            self.conv3 = nn.Conv2d(planes, planes * 4, 1, bias=False)
            self.bn3 = nn.BatchNorm2d(planes * 4)
            self.relu = nn.ReLU(inplace=True)
            self.downsample = downsample

        def forward(self, x):
            identity = x if self.downsample is None else self.downsample(x)
            out = self.relu(self.bn1(self.conv1(x)))
            out = self.relu(self.bn2(self.conv2(out)))
            out = self.bn3(self.conv3(out))
            return self.relu(out + identity)

    class ResNet50(nn.Module):
        def __init__(self):
            super().__init__()
            self.inplanes = 64
            self.conv1 = nn.Conv2d(3, 64, 7, stride=2, padding=3, bias=False)
            self.bn1 = nn.BatchNorm2d(64)
            self.relu = nn.ReLU(inplace=True)
            self.maxpool = nn.MaxPool2d(3, stride=2, padding=1)
            self.layer1 = self._layer(64, 3)
            self.layer2 = self._layer(128, 4, stride=2)
            self.layer3 = self._layer(256, 6, stride=2)
            self.layer4 = self._layer(512, 3, stride=2)
            self.avgpool = nn.AdaptiveAvgPool2d((1, 1))
            self.fc = nn.Linear(2048, 1000)

        def _layer(self, planes, blocks, stride=1):
            downsample = None
            if stride != 1 or self.inplanes != planes * 4:
                downsample = nn.Sequential(nn.Conv2d(self.inplanes, planes * 4, 1, stride=stride, bias=False),
                                           nn.BatchNorm2d(planes * 4))
            layers = [Bottleneck(self.inplanes, planes, stride, downsample)]
            self.inplanes = planes * 4
            layers += [Bottleneck(self.inplanes, planes) for _ in range(1, blocks)]
            return nn.Sequential(*layers)

        def forward(self, x):
            x = self.maxpool(self.relu(self.bn1(self.conv1(x))))
            x = self.layer4(self.layer3(self.layer2(self.layer1(x))))
            return self.fc(self.avgpool(x).flatten(1))
    return ResNet50()


def _initialise(model, nn, torch):
    """torchvision's initialisation for its ResNets, applied to both graphs, from a fixed seed."""
    torch.manual_seed(SEED)
    for m in model.modules():
        if isinstance(m, nn.Conv2d):
            nn.init.kaiming_normal_(m.weight, mode="fan_out", nonlinearity="relu")
            if m.bias is not None:
                nn.init.zeros_(m.bias)
        elif isinstance(m, nn.BatchNorm2d):
            nn.init.ones_(m.weight)
            nn.init.zeros_(m.bias)
        elif isinstance(m, nn.Linear):
            nn.init.normal_(m.weight, 0, 0.01)
            nn.init.zeros_(m.bias)
    return model


def build_cnn(name, device, torch, batch=CNN_BATCH):
    nn = torch.nn
    model = _initialise(_alexnet(nn) if name == "alexnet" else _resnet50(nn), nn, torch).to(device).eval()
    generator = torch.Generator().manual_seed(SEED + 1)
    # ImageNet-normalised pixels are roughly unit-variance; a seeded normal batch stands in for them.
    images = torch.randn((batch, 3, CNN_IMAGE, CNN_IMAGE), generator=generator).to(device)
    return model, images


def kmeans_inputs(torch, points=KMEANS_POINTS, features=KMEANS_FEATURES, clusters=KMEANS_CLUSTERS):
    """Job 60's mixture: equal groups, mean 8*(2*bit(c, d mod 4) - 1), unit Gaussian noise, CPU seed."""
    generator = torch.Generator().manual_seed(SEED)
    per = points // clusters
    bits = torch.tensor([[(c >> (d % 4)) & 1 for d in range(features)] for c in range(clusters)],
                        dtype=torch.float32)
    means = 8.0 * (2.0 * bits - 1.0)
    data = means.repeat_interleave(per, dim=0) + torch.randn((per * clusters, features), generator=generator)
    initial = data[torch.arange(clusters) * per].clone()
    return data, initial


def kmeans_task(data, initial, torch, updates=KMEANS_UPDATES):
    """Complete fixed-iteration Lloyd: returns (centres, memberships, inertia). Empty clusters keep
    their previous centre; ties go to the lowest index (torch.argmin returns the first minimum)."""
    clusters = initial.shape[0]
    centres = initial.clone()
    squared = (data * data).sum(dim=1, keepdim=True)
    for _ in range(updates):
        distance = squared - 2.0 * data @ centres.T + (centres * centres).sum(dim=1)
        member = torch.argmin(distance, dim=1)
        # Sums and counts through a one-hot matrix product rather than index_add_/bincount: no
        # host synchronisation (CUDA bincount reads its maximum back), and no float atomics, whose
        # arbitrary order would make the centres differ between runs in the last bits.
        onehot = (member.unsqueeze(1) == torch.arange(clusters, device=data.device)).to(data.dtype)
        sums = onehot.T @ data
        counts = onehot.sum(dim=0).unsqueeze(1)
        centres = torch.where(counts > 0, sums / counts.clamp(min=1.0), centres)
    distance = squared - 2.0 * data @ centres.T + (centres * centres).sum(dim=1)
    best, member = distance.min(dim=1)
    return centres, member, best.clamp(min=0.0).sum()


def hotspot_inputs(torch, grid=HOTSPOT_GRID, batch=HOTSPOT_BATCH):
    """Job 60's analytic maps, extended to a batch: instance b's power pattern is shifted by b rows so
    the batch is not one field repeated. Built in float64 on the CPU, converted once to float32."""
    i = torch.arange(grid, dtype=torch.float64).unsqueeze(1)
    j = torch.arange(grid, dtype=torch.float64).unsqueeze(0)
    temperature = 80.0 + 5.0 * i / (grid - 1) + 5.0 * j / (grid - 1)
    powers = []
    for b in range(batch):
        weight = 1.0 + 0.25 * torch.cos(2 * math.pi * (i + b * grid // max(batch, 1)) / grid) * torch.cos(2 * math.pi * j / grid)
        powers.append(180.0 * weight / weight.sum())
    return (temperature.expand(batch, grid, grid).contiguous().float(), torch.stack(powers).float())


def hotspot_coefficients(grid=HOTSPOT_GRID):
    """Rodinia's formulas for one cell; stability needs (dt/C)*(2/Rx + 2/Ry + 1/Rz) < 1."""
    h, w = CHIP_HEIGHT / grid, CHIP_WIDTH / grid
    capacitance = FACTOR_CHIP * SPEC_HEAT_SI * T_CHIP * w * h
    rx = w / (2.0 * K_SI * T_CHIP * h)
    ry = h / (2.0 * K_SI * T_CHIP * w)
    rz = T_CHIP / (K_SI * h * w)
    dt = PRECISION / (MAX_PD / (FACTOR_CHIP * T_CHIP * SPEC_HEAT_SI))
    step = dt / capacitance
    return step, rx, ry, rz


def hotspot_task(temperature, power, torch, steps=HOTSPOT_STEPS):
    """Explicit update with clamped (replicated) edges, all cells from the prior field."""
    grid = temperature.shape[-1]
    step, rx, ry, rz = hotspot_coefficients(grid)
    t = temperature.clone()
    pad = torch.nn.functional.pad
    for _ in range(steps):
        p = pad(t.unsqueeze(1), (1, 1, 1, 1), mode="replicate").squeeze(1)
        north, south = p[:, :-2, 1:-1], p[:, 2:, 1:-1]
        west, east = p[:, 1:-1, :-2], p[:, 1:-1, 2:]
        t = t + step * (power + (south + north - 2.0 * t) / ry + (east + west - 2.0 * t) / rx + (AMB_TEMP - t) / rz)
    return t


def build(name, device, torch):
    """Returns (step, units_per_step, unit, declared_flops, size) for gpu_workload.py's timed loop."""
    if name in ("alexnet", "resnet50"):
        model, images = build_cnn(name, device, torch)

        def step():
            with torch.inference_mode():
                model(images)
        return step, float(CNN_BATCH), "image/s", None, CNN_BATCH
    if name == "kmeans":
        data, initial = kmeans_inputs(torch)
        data, initial = data.to(device), initial.to(device)

        def step():
            kmeans_task(data, initial, torch)
        return step, 1.0, "task/s", None, KMEANS_POINTS
    if name == "hotspot":
        temperature, power = hotspot_inputs(torch)
        temperature, power = temperature.to(device), power.to(device)
        stability = hotspot_coefficients()[0] * (2 / hotspot_coefficients()[1] + 2 / hotspot_coefficients()[2])
        if stability >= 1.0:
            raise ValueError(f"HotSpot grid {HOTSPOT_GRID} is unstable at Rodinia's timestep ({stability:.3f})")

        def step():
            hotspot_task(temperature, power, torch)
        return step, 1.0, "task/s", None, HOTSPOT_GRID
    raise ValueError("unknown application workload: " + name)
