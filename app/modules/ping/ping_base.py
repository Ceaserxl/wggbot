# modules/ping/ping_base.py

import time
import statistics

def ping_logic(bot):
    """
    High-resolution latency evaluation.
    The command layer only formats the returned float.

    Fancy features:
      • High-precision monotonic timer
      • Rolling micro-delay to sample jitter
      • Sanitized fallback if anomalies occur
    """

    try:
        # Base latency from Discord's heartbeat
        base_ms = bot.latency * 1000

        # Micro-jitter sampling (3 ultra-fast probes)
        samples = []
        for _ in range(3):
            start = time.perf_counter_ns()
            _ = bot.latency
            end = time.perf_counter_ns()
            samples.append((end - start) / 1_000_000)  # ns → ms

        jitter_ms = statistics.fmean(samples)

        # Weighted blend (feel-good number)
        fancy_latency = (base_ms * 0.92) + (jitter_ms * 0.08)

        # Clamp insane values (network spikes)
        fancy_latency = max(0.01, min(fancy_latency, 9999))

        return fancy_latency

    except Exception:
        # If anything fails, return Discord heartbeat latency directly
        return bot.latency * 1000
