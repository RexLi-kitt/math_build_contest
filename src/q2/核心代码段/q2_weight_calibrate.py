# 功能：以蒙特卡洛场景和单纯形网格校准四指标权重，并进行稳定性排序。
from __future__ import annotations


def simplex_grid(step: float = 0.25) -> list[tuple[float, float, float, float]]:
    """列举 w_i>=0、sum(w_i)=1 的四维单纯形网格。"""
    n = round(1 / step)
    return [(a / n, b / n, c / n, (n - a - b - c) / n)
            for a in range(n + 1)
            for b in range(n - a + 1)
            for c in range(n - a - b + 1)]


def outer_loss(mean_mec_m: float, receive_rate: float, mean_time_s: float, baseline_time_s: float) -> float:
    """以实际二测 MEC、接收率和总时间构造外层损失，越小越好。"""
    return 0.40 * mean_mec_m / 20.0 + 0.35 * (1.0 - receive_rate) + 0.25 * mean_time_s / baseline_time_s


def normalize_perturbation(weights: tuple[float, float, float, float], index: int, factor: float) -> tuple[float, float, float, float]:
    """只扰动一个权重后重新归一化，保持总权重恒为 1。"""
    changed = list(weights)
    changed[index] *= factor
    total = sum(changed)
    return tuple(value / total for value in changed)


def calibrate(weights_grid, scenarios, evaluate_policy, baseline_time_s: float,
              perturb_factors: tuple[float, ...] = (0.9, 1.1),
              stability_tolerance: float | None = None):
    """按外层损失校准，并记录权重扰动后的最大损失变化。"""
    result = []
    for weights in weights_grid:
        metrics = evaluate_policy(weights, scenarios)
        loss = outer_loss(metrics["mean_mec_m"], metrics["receive_rate"], metrics["mean_time_s"], baseline_time_s)
        perturbation_losses = []
        for index in range(4):
            for factor in perturb_factors:
                perturbed = normalize_perturbation(weights, index, factor)
                trial = evaluate_policy(perturbed, scenarios)
                perturbation_losses.append(
                    outer_loss(trial["mean_mec_m"], trial["receive_rate"], trial["mean_time_s"], baseline_time_s)
                )
        max_loss_change = max((abs(value - loss) for value in perturbation_losses), default=0.0)
        stable = stability_tolerance is None or max_loss_change <= stability_tolerance
        result.append({"weights": weights, "loss": loss,
                       "max_loss_change": max_loss_change, "stable": stable, **metrics})
    return sorted(result, key=lambda row: (not row["stable"], row["loss"], row["max_loss_change"]))
