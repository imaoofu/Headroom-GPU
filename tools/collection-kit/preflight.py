"""
Prove this GPU can actually run the benchmark, before any clock is locked.

WHY torch.cuda.is_available() IS NOT ENOUGH
    It reports whether a CUDA device and driver were found. It does NOT report whether this
    PyTorch build contains compiled kernels for that device's compute capability. A wheel
    built without, say, sm_86 will happily say True on an Ampere card and then fail on the
    first real operation with "no kernel image is available for execution on the device".

    That failure would land mid-sweep, on someone else's machine, with the GPU clock-locked
    and nobody available to debug it. So this runs the two operations the workloads actually
    use - a matmul and an elementwise add - and synchronises to force any deferred launch
    error to surface here instead.

Prints one line per fact. Exits non-zero with a readable reason on any failure.
"""

import subprocess
import sys

# membw allocates three 256M-float buffers totalling 3.07 GB; gemm about 0.8 GB.
REQUIRED_VRAM_BYTES = 4.0e9


def freeVramBytesViaSmi():
    """Free VRAM according to nvidia-smi. Returns None if it cannot be determined.

    Checked BEFORE torch is imported, and that ordering is the whole point. torch does not
    fail fast on a starved GPU - it blocks trying to allocate. Measured here: with an
    unrelated 19 GB model resident and ~765 MB free, the preflight hung indefinitely at
    "testing the GPU" instead of refusing, and had to be killed. A hang with no message is
    the worst possible failure on a machine nobody can debug, so the cheap external check
    runs first.
    """
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits", "-i", "0"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return None
        return float(result.stdout.strip().splitlines()[0]) * 1024 * 1024
    except Exception:
        return None


def main():
    freeEarly = freeVramBytesViaSmi()
    if freeEarly is not None:
        print(f"INFO|vram_free_before_torch_gb={freeEarly / 1e9:.1f}")
        if freeEarly < REQUIRED_VRAM_BYTES:
            print(f"FAIL|only {freeEarly / 1e9:.1f} GB of VRAM is free and the benchmark needs "
                  f"about {REQUIRED_VRAM_BYTES / 1e9:.1f} GB. Close whatever is using the GPU - "
                  f"a game, a browser playing video, or a local AI model still loaded. "
                  f"Checked before loading PyTorch, which would otherwise hang rather than fail.")
            return 7

    try:
        import torch
    except Exception as error:
        print(f"FAIL|torch did not import: {error}")
        return 2

    if not torch.cuda.is_available():
        print("FAIL|PyTorch loaded but reports no CUDA device. Driver problem, or no NVIDIA GPU.")
        return 3

    name = torch.cuda.get_device_name(0)
    capability = torch.cuda.get_device_capability(0)
    smVersion = f"sm_{capability[0]}{capability[1]}"
    archList = list(torch.cuda.get_arch_list())

    print(f"INFO|device={name}")
    print(f"INFO|capability={smVersion}")
    print(f"INFO|built_for={','.join(archList)}")

    # A build lists the architectures it was compiled for. Ampere sm_86 code also runs on
    # sm_86; newer cards can fall back to PTX JIT if the build ships PTX, which is why this
    # is a warning rather than a refusal - the kernel test below is the real verdict.
    if archList and not any(smVersion.replace("sm_", "") in a for a in archList):
        print(f"WARN|{smVersion} is not in the build's architecture list")

    try:
        device = torch.device("cuda:0")
        left = torch.randn((512, 512), device=device, dtype=torch.float32)
        right = torch.randn((512, 512), device=device, dtype=torch.float32)
        product = torch.matmul(left, right)

        source = torch.randn(1 << 20, device=device, dtype=torch.float32)
        other = torch.randn(1 << 20, device=device, dtype=torch.float32)
        destination = torch.empty(1 << 20, device=device, dtype=torch.float32)
        torch.add(source, other, alpha=2.0, out=destination)

        # CUDA launches are asynchronous; without this the errors surface later, elsewhere.
        torch.cuda.synchronize()

        if not torch.isfinite(product).all() or not torch.isfinite(destination).all():
            print("FAIL|kernels ran but produced non-finite values. Unstable GPU or bad memory.")
            return 5
    except Exception as error:
        message = str(error).replace("\n", " ")[:300]
        print(f"FAIL|the GPU could not run the benchmark kernels: {message}")
        return 4
    finally:
        try:
            torch.cuda.empty_cache()
        except Exception:
            pass

    freeBytes, totalBytes = torch.cuda.mem_get_info(0)
    print(f"INFO|vram_total_gb={totalBytes / 1e9:.1f}")
    print(f"INFO|vram_free_gb={freeBytes / 1e9:.1f}")

    # Second look, now from torch's own view. The nvidia-smi check above already refused the
    # starved case; this catches the narrower one where memory was freed between the two
    # checks or where nvidia-smi was unavailable and returned None.
    if freeBytes < REQUIRED_VRAM_BYTES:
        print(f"FAIL|only {freeBytes / 1e9:.1f} GB of VRAM free; the benchmark needs about "
              f"{REQUIRED_VRAM_BYTES / 1e9:.1f} GB. Close anything using the GPU.")
        return 6

    print("OK|this GPU can run the benchmark")
    return 0


if __name__ == "__main__":
    sys.exit(main())
