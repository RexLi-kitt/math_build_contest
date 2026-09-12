"""Q4 方向—位置联合信念地图、主动复测与失败清除回补的本地动作级验证。"""
from __future__ import annotations

import csv
import math
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from engine.q4_local_simulator import LocalQ4Simulator, wrap

ROOT = HERE.parents[2]
OUT = ROOT / "outputs" / "q4"
# 仅管理输出位置，不参与模型决策；默认标签锁定正式 V13，探索实验必须显式另设标签。
OUTPUT_TAG = os.environ.get("Q4_OUTPUT_TAG", "v13")
FIG, TAB, LOG = OUT / OUTPUT_TAG / "figures", OUT / OUTPUT_TAG / "tables", OUT / OUTPUT_TAG / "logs" / "risk_belief_runs"
BLUE, ORANGE, GRAY, DARK = "#1F5A94", "#E67E22", "#8A8F98", "#23364A"
# 首测越早，立即定位成功后可省去的后续频道扫描越多，故可采用较低阈值。
EARLY_Q2_SCORE_MIN = float(os.environ.get("Q4_EARLY_Q2_SCORE_MIN", "0"))
EARLY_Q2_SCORE_MAX = float(os.environ.get("Q4_EARLY_Q2_SCORE_MAX", "0"))
RUN_SEED = int(os.environ.get("Q4_RUN_SEED", "20260915"))
STRICT_DIRECTIONAL_COVERAGE = os.environ.get("Q4_STRICT_DIRECTIONAL_COVERAGE", "0") == "1"
LOCAL_TASK_ORDER = os.environ.get("Q4_LOCAL_TASK_ORDER", "q2_lookahead")
TWO_BEARING_CLEAR_BOUND_M = float(os.environ.get("Q4_TWO_BEARING_CLEAR_BOUND_M", "35"))
TRY_TWO_BEARING_CLEAR = os.environ.get("Q4_TRY_TWO_BEARING_CLEAR", "1") == "1"
TWO_BEARING_PROBE_RADIUS_M = float(os.environ.get("Q4_TWO_BEARING_PROBE_RADIUS_M", "0"))
SYMMETRIC_Q2_PROBE = os.environ.get("Q4_SYMMETRIC_Q2_PROBE", "1") == "1"
Q2_W_GEO = float(os.environ.get("Q4_W_GEO", "0.30"))
Q2_W_RECEIVE = float(os.environ.get("Q4_W_RECEIVE", "0.20"))
Q2_W_MOVE = float(os.environ.get("Q4_W_MOVE", "0.50"))
TASK_SCORE_WEIGHT = float(os.environ.get("Q4_TASK_SCORE_WEIGHT", "0.20"))
Q2_LOOKAHEAD_WEIGHT = float(os.environ.get("Q4_Q2_LOOKAHEAD_WEIGHT", "0.25"))
Q2_ROUTE_BEAM_WIDTH = int(os.environ.get("Q4_Q2_ROUTE_BEAM_WIDTH", "48"))
SURVEY_LAYOUT = os.environ.get("Q4_SURVEY_LAYOUT", "full")
DYNAMIC_SURVEY_ORDER = os.environ.get("Q4_DYNAMIC_SURVEY_ORDER", "0") == "1"
SOFT_RECEIVE_PROBABILITY = os.environ.get("Q4_SOFT_RECEIVE_PROBABILITY", "0") == "1"
MAX_Q2_TASKS_PER_STATION = int(os.environ.get("Q4_MAX_Q2_TASKS_PER_STATION", "0"))
BELIEF_GRID_STEP_M = int(os.environ.get("Q4_BELIEF_GRID_STEP_M", "50"))
BELIEF_DIRECTION_STEP_DEG = int(os.environ.get("Q4_BELIEF_DIRECTION_STEP_DEG", "10"))
WEIGHTED_BELIEF = os.environ.get("Q4_WEIGHTED_BELIEF", "0") == "1"
Q2_SELECTION_MODE = os.environ.get("Q4_SELECTION_MODE", "weighted_sum")
Q2_MIN_GEOMETRY = float(os.environ.get("Q4_MIN_GEOMETRY", "0.85"))
Q2_MIN_RECEIVE = float(os.environ.get("Q4_MIN_RECEIVE", "0.20"))
Q2_UNCERTAINTY_TIERED = os.environ.get("Q4_UNCERTAINTY_TIERED", "0") == "1"
Q2_NARROW_IQR_M = float(os.environ.get("Q4_NARROW_IQR_M", "300"))
Q2_MEDIUM_IQR_M = float(os.environ.get("Q4_MEDIUM_IQR_M", "600"))
Q2_FIXED_RANGES = tuple(float(value) for value in os.environ.get("Q4_Q2_FIXED_RANGES", "600,700,800,900,1000,1100").split(","))
Q2_FIXED_LATERALS = tuple(float(value) for value in os.environ.get("Q4_Q2_FIXED_LATERALS", "150,250,350").split(","))
TRIANGULAR_EDGE_M = float(os.environ.get("Q4_TRIANGULAR_EDGE_M", "950"))


def visible(point: tuple[float, float], g: tuple[float, float], phi: float) -> bool:
    angle = math.degrees(math.atan2(point[1] - g[1], point[0] - g[0]))
    return abs(wrap(angle - phi)) <= 90.0


def bearing_line_estimate(obs: list[tuple[float, float, float]]) -> tuple[float, float] | None:
    """多条带误差示向度的中心线最小二乘估计；只生成清除候选，不能替代 MEC 判据。"""
    if len(obs) < 2:
        return None
    a00 = a01 = a11 = b0 = b1 = 0.0
    for x, y, deg in obs:
        nx, ny = -math.sin(math.radians(deg)), math.cos(math.radians(deg))
        a00 += nx*nx; a01 += nx*ny; a11 += ny*ny
        z = nx*x + ny*y; b0 += nx*z; b1 += ny*z
    det = a00*a11 - a01*a01
    if abs(det) < 1e-8:
        return None
    return ((a11*b0-a01*b1)/det, (a00*b1-a01*b0)/det)


def max_bearing_residual(point: tuple[float, float], obs: list[tuple[float, float, float]]) -> float:
    """以最大角残差检验多条示向度是否一致，避免两线偶然交会就直接清除。"""
    return max(abs(wrap(math.degrees(math.atan2(point[1]-y, point[0]-x))-deg)) for x, y, deg in obs)


def two_bearing_error_bound(point: tuple[float, float], obs: list[tuple[float, float, float]]) -> float:
    """两条 ±1° 示向度在交会点附近诱导的位置误差上界近似，用于是否值得低成本尝试清除。

    该量只触发尝试，不承担可靠成功证明；若 /clear 失败，策略仍追加 Q2 第三测向。
    """
    if len(obs) != 2:
        return float("inf")
    (x1, y1, a1), (x2, y2, a2) = obs
    r1, r2 = math.dist(point, (x1, y1)), math.dist(point, (x2, y2))
    gamma = abs(wrap(a1 - a2))
    gamma = min(gamma, 180.0 - gamma)
    if gamma <= 1e-6:
        return float("inf")
    return math.tan(math.radians(1.005)) * (r1 + r2) / math.sin(math.radians(gamma))


def _clip_halfplane(polygon: list[tuple[float, float]], origin: tuple[float, float],
                    direction_deg: float, keep_left: bool) -> list[tuple[float, float]]:
    """Sutherland--Hodgman 半平面裁剪：把一条测向的 ±1° 区间写成两个线性约束。"""
    if not polygon:
        return []
    vx, vy = math.cos(math.radians(direction_deg)), math.sin(math.radians(direction_deg))

    def signed(p: tuple[float, float]) -> float:
        return vx * (p[1] - origin[1]) - vy * (p[0] - origin[0])

    def inside(p: tuple[float, float]) -> bool:
        return signed(p) >= -1e-9 if keep_left else signed(p) <= 1e-9

    clipped: list[tuple[float, float]] = []
    previous = polygon[-1]
    previous_inside = inside(previous)
    for current in polygon:
        current_inside = inside(current)
        if current_inside != previous_inside:
            sp, sc = signed(previous), signed(current)
            ratio = sp / (sp - sc)
            clipped.append((previous[0] + ratio * (current[0] - previous[0]),
                            previous[1] + ratio * (current[1] - previous[1])))
        if current_inside:
            clipped.append(current)
        previous, previous_inside = current, current_inside
    return clipped


def triangular_cover_stations() -> list[tuple[float, float]]:
    """定向源的三角格点保底层，随后用最近邻顺序降低巡检移动距离。

    边长 h=950m。目标圆内任一点位于某个等边格三角形内，三个顶点到该点均不超过
    h<1000m；该点又是三个顶点的凸组合，故任意 180° 发射半平面至少包含一个顶点。
    只保留距原点不超过 1800+h 的格点即可保留所有可能包含目标圆点的三角形顶点。
    """
    radius, h = 1800.0, TRIANGULAR_EDGE_M
    dy = math.sqrt(3.0) * h / 2.0
    max_row = math.ceil((radius + h) / dy)
    max_col = math.ceil((radius + h) / h) + 1
    remaining = []
    for row in range(-max_row, max_row + 1):
        for column in range(-max_col, max_col + 1):
            x, y = h * (column + 0.5 * (row & 1)), dy * row
            if x*x + y*y <= (radius + h) ** 2 + 1e-9:
                remaining.append((x, y))
    # 覆盖证书与访问顺序分离：最近邻仅优化时间，不影响三角覆盖的几何保证。
    route, current = [], (0.0, 0.0)
    while remaining:
        station = min(remaining, key=lambda point: math.dist(current, point))
        route.append(station)
        remaining.remove(station)
        current = station
    return route


def survey_stations() -> list[tuple[float, float]]:
    """Q2 主链路的快速三环巡检：尽早获得首测向并触发主动二测。

    它是效率层，不单独作为任意定向朝向的不漏检证明；严格三角覆盖由
    triangular_cover_stations() 按需作为尚未发现频道的终止兜底。
    """
    if SURVEY_LAYOUT == "triangular_certified":
        # h=950m 的三角格点来自定向可见性覆盖证明：仅替换发现层，
        # 一旦获得首测向，仍由 Q2 主动二测与风险信念链路完成定位。
        return triangular_cover_stations()
    layouts = {
        "full": ((900.0, 0.0, 12), (1500.0, 15.0, 12), (1800.0, 0.0, 12)),
        "two_ring": ((900.0, 0.0, 12), (1500.0, 15.0, 12)),
        "two_ring_8": ((900.0, 0.0, 8), (1500.0, 22.5, 8)),
        "outer_ring": ((1500.0, 15.0, 12),),
    }
    rings = layouts.get(SURVEY_LAYOUT, layouts["full"])
    points = [(0.0, 0.0)]
    for radius, shift, count in rings:
        points += [(radius * math.cos(math.radians(shift + 360 * k / count)),
                    radius * math.sin(math.radians(shift + 360 * k / count))) for k in range(count)]
    return points


@dataclass
class DirectionalBelief:
    """离散的 (位置, 发射方向) 风险状态；策略不会访问模拟器隐藏 Source。"""
    channel: int
    directions: list[tuple[float, float, float]] = field(default_factory=list)
    negatives: list[tuple[float, float]] = field(default_factory=list)
    q2_second_attempted: bool = False
    q2_second_decided: bool = False
    q2_second_score: float | None = None
    q2_second_threshold: float | None = None
    q2_second_location: tuple[float, float] | None = None
    q2_symmetric_location: tuple[float, float] | None = None
    q2_predicted_target: tuple[float, float] | None = None
    q2_selected_geometry: float | None = None
    q2_selected_receive: float | None = None
    q2_selected_move: float | None = None
    q2_range_iqr_m: float | None = None
    q2_uncertainty_band: str = "未分级"
    # 位置分辨率 150m、方向 30°；仅用于风险评分，不作为最终清除精度。
    states: list[tuple[float, float, float]] = field(default_factory=list)

    def initialise(self) -> None:
        if self.states:
            return
        for x in range(-1800, 1801, BELIEF_GRID_STEP_M):
            for y in range(-1800, 1801, BELIEF_GRID_STEP_M):
                if x*x+y*y <= 1800*1800:
                    for phi in range(0, 360, BELIEF_DIRECTION_STEP_DEG):
                        self.states.append((float(x), float(y), float(phi)))

    def update_direction(self, point: tuple[float, float], svd: float) -> None:
        self.initialise(); self.directions.append((point[0], point[1], svd))
        # 网格位置误差用额外 6°裕量吸收；最终定位仍使用连续观测线和清除反馈。
        self.states = [state for state in self.states if abs(wrap(math.degrees(math.atan2(state[1]-point[1], state[0]-point[0]))-svd)) <= 7.0
                       and math.dist(point, state[:2]) <= 1500.0 and visible(point, state[:2], state[2])]

    def update_no_signal(self, point: tuple[float, float]) -> None:
        self.initialise(); self.negatives.append(point)
        # 仅在保证接收半径 1000m 内且该朝向本应可见时，no_signal 才能排除状态。
        self.states = [state for state in self.states if not (math.dist(point, state[:2]) <= 1000.0 and visible(point, state[:2], state[2]))]

    @staticmethod
    def receive_likelihood(distance: float) -> float:
        """接收半径 R~U(1000,1500) 时，在给定距离下收到信号的先验概率。"""
        if distance <= 1000.0:
            return 1.0
        if distance <= 1500.0:
            return (1500.0 - distance) / 500.0
        return 0.0

    def posterior_weight(self, state: tuple[float, float, float]) -> float:
        """用已有 direction/no_signal 对状态加权；仅用于 Q2 主动选点。"""
        if not WEIGHTED_BELIEF:
            return 1.0
        weight = 1.0
        for x, y, _ in self.directions:
            weight *= self.receive_likelihood(math.dist((x, y), state[:2]))
        for point in self.negatives:
            if visible(point, state[:2], state[2]):
                weight *= 1.0 - self.receive_likelihood(math.dist(point, state[:2]))
        return weight

    def expected_visible_fraction(self, point: tuple[float, float]) -> float:
        if not self.states:
            return 0.0
        def receive_probability(state: tuple[float, float, float]) -> float:
            distance = math.dist(point, state[:2])
            if distance <= 1000.0:
                return 1.0
            if (SOFT_RECEIVE_PROBABILITY or WEIGHTED_BELIEF) and distance <= 1500.0:
                # R~U(1000,1500) 时 P(R≥d)=(1500-d)/500；再叠加定向可见性。
                return (1500.0 - distance) / 500.0
            return 0.0
        weights = [self.posterior_weight(s) for s in self.states]
        normalizer = sum(weights)
        if normalizer <= 1e-12:
            return 0.0
        return sum(weight * receive_probability(s) * visible(point, s[:2], s[2])
                   for s, weight in zip(self.states, weights)) / normalizer

    def conservative_angle_polygon(self) -> tuple[list[tuple[float, float]], bool]:
        """求源分布外包框内的角度带交集；触边即说明位置不确定域尚未封闭。"""
        bound = 1800.0
        polygon = [(-bound, -bound), (bound, -bound), (bound, bound), (-bound, bound)]
        for x, y, deg in self.directions:
            polygon = _clip_halfplane(polygon, (x, y), deg - 1.0, keep_left=True)
            polygon = _clip_halfplane(polygon, (x, y), deg + 1.0, keep_left=False)
            if not polygon:
                return [], True
        touches_box = any(abs(abs(x) - bound) < 1e-6 or abs(abs(y) - bound) < 1e-6 for x, y in polygon)
        return polygon, touches_box

    def certified_clear_circle(self) -> tuple[tuple[float, float], float] | None:
        """用角度带交集顶点的质心构造保守包含圆，半径≤20m才允许 /clear。"""
        if len(self.directions) < 3:
            return None
        polygon, touches_box = self.conservative_angle_polygon()
        if len(polygon) < 3 or touches_box:
            return None
        center = (sum(x for x, _ in polygon) / len(polygon), sum(y for _, y in polygon) / len(polygon))
        radius = max(math.dist(center, vertex) for vertex in polygon)
        return center, radius

    def q2_second_point(self, current: tuple[float, float]) -> tuple[float, float] | None:
        """首次 direction 后的 Q2 自适应二测点。

        用首次方向后的信念状态的源距分位数和自适应横向偏移构造候选点，再按
        几何交会质量、保证可见比例、移动时间打分。它只调用一次；若 no_signal，
        则保留该频道并回退到全局巡检，不把定向盲区当成目标不存在。
        """
        if len(self.directions) != 1 or self.q2_second_attempted:
            return None
        x, y, deg = self.directions[0]
        ux, uy = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        vx, vy = -uy, ux
        weighted_ranges = sorted((math.dist((x, y), state[:2]), self.posterior_weight(state)) for state in self.states)
        ranges = [value for value, _ in weighted_ranges]
        if ranges:
            # 首测角带过宽时，分位半径会把离散先验误差放大；此时保留 Q2 已校准网格。
            if WEIGHTED_BELIEF and sum(weight for _, weight in weighted_ranges) > 1e-12:
                total_weight = sum(weight for _, weight in weighted_ranges)
                def weighted_quantile(q: float) -> float:
                    threshold, cumulative = q * total_weight, 0.0
                    for value, weight in weighted_ranges:
                        cumulative += weight
                        if cumulative >= threshold:
                            return value
                    return weighted_ranges[-1][0]
                quantiles = tuple(weighted_quantile(q) for q in (.25, .50, .75))
            else:
                quantiles = tuple(ranges[round((len(ranges) - 1) * q)] for q in (.25, .50, .75))
            self.q2_range_iqr_m = quantiles[2] - quantiles[0]
            adaptive_range = self.q2_range_iqr_m <= 250.0
            source_ranges = quantiles if adaptive_range else Q2_FIXED_RANGES
        else:
            adaptive_range = False
            source_ranges = Q2_FIXED_RANGES
            self.q2_range_iqr_m = None
        candidates: list[tuple[float, tuple[float, float], tuple[float, float], float, float, float]] = []
        for source_range in source_ranges:
            prior = (x + source_range * ux, y + source_range * uy)
            # 仅在距离不确定域收敛时随源距调整横向偏移；否则维持 Q2 校准网格。
            laterals = (tuple(sorted({max(260.0, min(850.0, ratio * source_range))
                                      for ratio in (.38, .55, .72)})) if adaptive_range else Q2_FIXED_LATERALS)
            for lateral in laterals:
                for sign in (-1.0, 1.0):
                    point = (prior[0] + sign * lateral * vx, prior[1] + sign * lateral * vy)
                    # 第一条测向与预测第二条测向的交会角；越近 90° 越好。
                    second_bearing = math.degrees(math.atan2(prior[1] - point[1], prior[0] - point[0]))
                    angle = abs(wrap(deg - second_bearing))
                    geometry = math.sin(math.radians(min(angle, 180.0 - angle))) ** 2
                    receive = self.expected_visible_fraction(point)
                    move = min(math.dist(current, point) / 1800.0, 1.0)
                    score = Q2_W_GEO * geometry + Q2_W_RECEIVE * receive - Q2_W_MOVE * move
                    candidates.append((score, point, prior, geometry, receive, move))
        if not candidates:
            return None
        range_iqr = self.q2_range_iqr_m if self.q2_range_iqr_m is not None else float("inf")
        if Q2_UNCERTAINTY_TIERED and range_iqr <= Q2_NARROW_IQR_M:
            self.q2_uncertainty_band = "窄域"
            eligible = [item for item in candidates if item[3] >= Q2_MIN_GEOMETRY and item[4] >= 0.55]
            pool = eligible if eligible else candidates
            score, point, prior, geometry, receive, move = min(
                pool, key=lambda item: math.dist(current, item[1]) + math.dist(item[1], item[2]))
        elif Q2_UNCERTAINTY_TIERED and range_iqr <= Q2_MEDIUM_IQR_M:
            self.q2_uncertainty_band = "中域"
            score, point, prior, geometry, receive, move = max(candidates, key=lambda item: item[0])
        elif Q2_UNCERTAINTY_TIERED:
            self.q2_uncertainty_band = "宽域"
            # 宽域不确定性大：接收保障优先于行程缩短，避免二测落入定向盲侧。
            score, point, prior, geometry, receive, move = max(
                candidates, key=lambda item: 0.35 * item[3] + 0.45 * item[4] - 0.20 * item[5])
        elif Q2_SELECTION_MODE == "cautious_service":
            eligible = [item for item in candidates if item[3] >= Q2_MIN_GEOMETRY and item[4] >= Q2_MIN_RECEIVE]
            # 先满足信息与接收底线，再最小化当前→二测→预测交会中心的服务路程。
            if eligible:
                score, point, prior, geometry, receive, move = min(
                    eligible, key=lambda item: math.dist(current, item[1]) + math.dist(item[1], item[2]))
            else:
                score, point, prior, geometry, receive, move = max(candidates, key=lambda item: item[0])
        else:
            score, point, prior, geometry, receive, move = max(candidates, key=lambda item: item[0])
        self.q2_second_score = score
        self.q2_second_location = point
        self.q2_predicted_target = prior
        self.q2_selected_geometry = geometry
        self.q2_selected_receive = receive
        self.q2_selected_move = move
        # 关于首测向线镜像的备选点：仅当首个主动二测无信号时使用，
        # 用于快速区分“定向盲侧”与“源已远离候选位置”。
        longitudinal = (point[0] - x) * ux + (point[1] - y) * uy
        lateral = (point[0] - x) * vx + (point[1] - y) * vy
        self.q2_symmetric_location = (x + longitudinal * ux - lateral * vx,
                                      y + longitudinal * uy - lateral * vy)
        return point

    def early_second_threshold(self, remaining_stations: int, total_stations: int) -> float:
        """剩余巡检点越多，立即二测成功后可节省的频道扫描越多，阈值越低。"""
        progress = 1.0 - max(0, remaining_stations) / max(1, total_stations)
        threshold = EARLY_Q2_SCORE_MIN + (EARLY_Q2_SCORE_MAX - EARLY_Q2_SCORE_MIN) * progress
        self.q2_second_threshold = threshold
        return threshold

    def active_point(self, current: tuple[float, float]) -> tuple[float, float] | None:
        estimate = bearing_line_estimate(self.directions)
        if estimate is None:
            return None
        candidates = []
        for radius in (450.0, 650.0, 850.0):
            for degree in range(0, 360, 30):
                p = (estimate[0] + radius*math.cos(math.radians(degree)), estimate[1] + radius*math.sin(math.radians(degree)))
                geometry = 0.0
                if self.directions:
                    first = self.directions[0]
                    a = abs(wrap(math.degrees(math.atan2(estimate[1]-first[1], estimate[0]-first[0])) - math.degrees(math.atan2(estimate[1]-p[1], estimate[0]-p[0]))))
                    geometry = math.sin(math.radians(min(a, 180-a)))**2
                score = (Q2_W_GEO * geometry + Q2_W_RECEIVE * self.expected_visible_fraction(p)
                         - Q2_W_MOVE * math.dist(current, p) / 1800.0)
                candidates.append((score, p))
        return max(candidates, key=lambda item: item[0])[1]


def main(seed: int = RUN_SEED) -> dict:
    for directory in (OUT, FIG, TAB, LOG): directory.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.sans-serif":["Microsoft YaHei","SimHei","DejaVu Sans"], "axes.unicode_minus":False})
    sim = LocalQ4Simulator(seed=seed, source_count=12, directional_ratio=.5)
    beliefs = {channel: DirectionalBelief(channel) for channel in range(1, 21)}
    cleared, first_positive, clear_time, trace, action_no = set(), {}, {}, [(0.0,0.0)], 0

    def rid(prefix: str) -> str:
        nonlocal action_no
        action_no += 1; return f"{prefix}-{action_no}"

    def observe(channel: int, point: tuple[float,float]) -> None:
        response = sim.measure(point, channel, rid("measure")); trace.append(point)
        if response["measure_result"] == "direction":
            beliefs[channel].update_direction(point, response["svd_deg"]); first_positive.setdefault(channel, response["virtual_time_s"])
        elif response["measure_result"] == "near":
            first_positive.setdefault(channel, response["virtual_time_s"]); attempt_clear(channel, point)
        else:
            beliefs[channel].update_no_signal(point)

    def attempt_clear(channel: int, point: tuple[float,float]) -> bool:
        response = sim.clear(point, channel, rid("clear")); trace.append(point)
        if response["clear_result"] == "success":
            cleared.add(channel); clear_time[channel] = response["virtual_time_s"]; return True
        return False

    def probe_two_bearing_neighbourhood(channel: int, estimate: tuple[float, float]) -> bool:
        """以交会估计点为中心做小尺度、中心优先的安全试清除。

        只在双测向已经得到且中心点失败时启用。每次 /clear 仍由模拟器的
        20m 距离判定把关；半径为 0 时关闭该可选加速层。
        """
        radius = TWO_BEARING_PROBE_RADIUS_M
        if radius <= 0:
            return False
        step = 20.0
        offsets = [(dx, dy) for dx in range(-int(radius), int(radius) + 1, int(step))
                   for dy in range(-int(radius), int(radius) + 1, int(step))]
        # 先试交会中心，再按到中心的距离由近及远扩展，避免无目的的大范围扫描。
        offsets.sort(key=lambda item: (item[0] * item[0] + item[1] * item[1], item[0], item[1]))
        for dx, dy in offsets:
            if dx == 0 and dy == 0:
                continue  # 中心点已在调用处尝试过。
            if attempt_clear(channel, (estimate[0] + dx, estimate[1] + dy)):
                return True
        return False

    def optical_strip_fallback(channel: int) -> bool:
        """单条正测向仍无法获得第二方向时的有限光学兜底。

        首次 direction 将源限制在长度 1500m、半宽至多 1500sin(1°)<27m 的局部条带。
        使用 25m 正方形中心网格覆盖该条带，任意可能源位置距最近清除点不超过
        25/sqrt(2)<20m。该过程与发射朝向无关，只在 Q2 二测失败的终阶段调用。
        """
        x, y, deg = beliefs[channel].directions[0]
        ux, uy = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        vx, vy = -uy, ux
        # 三行横向中心覆盖 ±27m；每行 60 个纵向中心覆盖 [0,1500]m。
        points: list[tuple[float, float]] = []
        for row, lateral in enumerate((-25.0, 0.0, 25.0)):
            longitudinals = range(60) if row % 2 == 0 else range(59, -1, -1)
            for index in longitudinals:
                forward = 12.5 + 25.0 * index
                points.append((x + forward * ux + lateral * vx, y + forward * uy + lateral * vy))
        # 仅改变访问起点而不改变条带覆盖：从当前位置最近的格点开始循环访问。
        start = min(range(len(points)), key=lambda idx: math.dist(sim.position, points[idx]))
        ordered = points[start:] + points[:start]
        for point in ordered:
            if attempt_clear(channel, point):
                return True
        return False

    def refine(channel: int, remaining_stations: int = 0, total_stations: int = 1,
               force_second_measure: bool = False) -> None:
        """以 Q2 主动补测为核心；角度带包含圆收敛后清除，失败再局部回补。"""
        belief = beliefs[channel]
        # Q2 的核心入口：首次测向立即选二测点，而不是被动等待下一处巡检站。
        if len(belief.directions) == 1 and (not belief.q2_second_decided or force_second_measure):
            if force_second_measure:
                # 巡检结束时，已发现频道不能因阈值策略而停在“一条测向”的非终止状态。
                belief.q2_second_decided = False
            second_point = belief.q2_second_point(sim.position)
            belief.q2_second_decided = True
            # 分数低时继续三环巡检以换取更低的总移动代价；频道并不被丢弃。
            threshold = belief.early_second_threshold(remaining_stations, total_stations)
            if second_point is not None and (force_second_measure or (belief.q2_second_score or 0.0) >= threshold):
                belief.q2_second_attempted = True
                observe(channel, second_point)
                if (channel not in cleared and len(belief.directions) == 1
                        and SYMMETRIC_Q2_PROBE and belief.q2_symmetric_location is not None):
                    observe(channel, belief.q2_symmetric_location)
            if channel in cleared:
                return
            if len(belief.directions) < 2:
                if force_second_measure:
                    optical_strip_fallback(channel)
                return
        for _ in range(3):
            estimate = bearing_line_estimate(belief.directions)
            if estimate is None: return
            # Q2 二测后若预测误差已足够小，先做一次低成本提前清除；失败不改变稳健链路。
            if len(belief.directions) == 2:
                # 保守误差界用于“已认证”的解释；但 /clear 自带 20m 成功校验。
                # 因而可先以 Q2 双线交会点做一次零风险试清除：失败后完整回退至
                # 三测向与信念地图链路，既不误清，也避免保守上界过大时的无谓加测。
                certified_by_bound = two_bearing_error_bound(estimate, belief.directions) <= TWO_BEARING_CLEAR_BOUND_M
                if certified_by_bound or TRY_TWO_BEARING_CLEAR:
                    if attempt_clear(channel, estimate):
                        return
                if probe_two_bearing_neighbourhood(channel, estimate):
                    return
            # 优先采用所有 ±1° 角带的保守认证；若角度带尚未收敛，
            # 则由三测向一致性触发 Q2 中心线候选，失败时仍由局部回补兜底。
            certified = belief.certified_clear_circle()
            if certified is not None and certified[1] <= 20.0:
                if attempt_clear(channel, certified[0]): return
            elif len(belief.directions) >= 3 and max_bearing_residual(estimate, belief.directions) <= 2.0:
                if attempt_clear(channel, estimate): return
            next_point = belief.active_point(sim.position)
            if next_point is None: return
            observe(channel, next_point)
            if channel in cleared: return
        estimate = bearing_line_estimate(belief.directions)
        if estimate is None: return
        # 清除失败后的20m半径局部回补：28m网格保证格内最远点距离小于20m。
        for dx in range(-84, 85, 28):
            for dy in range(-84, 85, 28):
                if attempt_clear(channel, (estimate[0]+dx, estimate[1]+dy)):
                    return

    def local_task_order(channels: list[int]) -> list[int]:
        """Q2 评分驱动的局部任务队列，避免按频道编号使已发现源无谓等待。"""
        if LOCAL_TASK_ORDER == "channel":
            return sorted(channels)

        if LOCAL_TASK_ORDER == "q2_lookahead":
            # 所有候选均由同一套 Q2 首测向候选集计算；此处仅作多频道访问次序的
            # 一步前瞻，不改变每个频道的二测点、观测模型或清除判定。
            records: dict[int, tuple[tuple[float, float], tuple[float, float], float]] = {}
            for channel in channels:
                belief = beliefs[channel]
                if len(belief.directions) >= 2:
                    estimate = bearing_line_estimate(belief.directions)
                    if estimate is not None:
                        records[channel] = (estimate, estimate, 0.0)
                    continue
                belief.q2_second_point(sim.position)
                if belief.q2_second_location is not None and belief.q2_predicted_target is not None:
                    records[channel] = (belief.q2_second_location, belief.q2_predicted_target,
                                        belief.q2_second_score or 0.0)
            priorities: list[tuple[float, float, int]] = []
            for channel in channels:
                if channel not in records:
                    priorities.append((float("inf"), float("inf"), channel)); continue
                second, target, score = records[channel]
                own = math.dist(sim.position, second) + math.dist(second, target)
                follow = [math.dist(target, other_second) + math.dist(other_second, other_target)
                          for other, (other_second, other_target, _) in records.items() if other != channel]
                next_cost = min(follow) if follow else 0.0
                priorities.append((own + Q2_LOOKAHEAD_WEIGHT * next_cost, -score, channel))
            return [channel for _, _, channel in sorted(priorities)]

        if LOCAL_TASK_ORDER == "q2_beam_route":
            # 以 Q2 二测点和对应源距先验中心构成“服务节点”，束搜索近似最小化
            # 全部已发现频道的完成时间之和。每轮只采用首节点，随后重新观测、重算，
            # 因而不把先验路线当作真实源位置。
            records: dict[int, tuple[tuple[float, float], tuple[float, float]]] = {}
            for channel in channels:
                belief = beliefs[channel]
                if len(belief.directions) >= 2:
                    estimate = bearing_line_estimate(belief.directions)
                    if estimate is not None:
                        records[channel] = (estimate, estimate)
                    continue
                belief.q2_second_point(sim.position)
                if belief.q2_second_location is not None and belief.q2_predicted_target is not None:
                    records[channel] = (belief.q2_second_location, belief.q2_predicted_target)
            if not records:
                return sorted(channels)
            # (加权完成时间和, 当前累计路程, 路径, 剩余频道, 当前预测终点)
            beam = [(0.0, 0.0, tuple(), tuple(records), sim.position)]
            total = len(records)
            while beam and len(beam[0][2]) < total:
                expanded = []
                for weighted, elapsed, route, remaining, endpoint in beam:
                    for channel in remaining:
                        second, target = records[channel]
                        service = math.dist(endpoint, second) + math.dist(second, target)
                        elapsed_next = elapsed + service
                        # 每多完成一个频道，其等待时间都会贡献一次，故累计完成时间作目标。
                        expanded.append((weighted + elapsed_next, elapsed_next, route + (channel,),
                                         tuple(item for item in remaining if item != channel), target))
                expanded.sort(key=lambda item: (item[0], item[1], item[2]))
                beam = expanded[:Q2_ROUTE_BEAM_WIDTH]
            best_route = beam[0][2] if beam else tuple(records)
            return list(best_route) + [channel for channel in channels if channel not in records]

        if LOCAL_TASK_ORDER == "alternating_score":
            # 低分任务先消除定向失联风险，高分任务穿插执行以避免短任务长期等待。
            scored = []
            for channel in channels:
                belief = beliefs[channel]
                if len(belief.directions) >= 2:
                    score = 2.0
                else:
                    if not belief.q2_second_decided:
                        belief.q2_second_point(sim.position)
                    score = belief.q2_second_score or 0.0
                scored.append((score, channel))
            scored.sort()
            order = []
            left, right = 0, len(scored) - 1
            while left <= right:
                order.append(scored[left][1]); left += 1
                if left <= right:
                    order.append(scored[right][1]); right -= 1
            return order

        if LOCAL_TASK_ORDER == "alternating_high":
            scored = []
            for channel in channels:
                belief = beliefs[channel]
                if len(belief.directions) >= 2:
                    score = 2.0
                else:
                    if not belief.q2_second_decided:
                        belief.q2_second_point(sim.position)
                    score = belief.q2_second_score or 0.0
                scored.append((score, channel))
            scored.sort()
            order = []
            left, right = 0, len(scored) - 1
            while left <= right:
                order.append(scored[right][1]); right -= 1
                if left <= right:
                    order.append(scored[left][1]); left += 1
            return order

        def key(channel: int) -> tuple[int, float, float]:
            belief = beliefs[channel]
            # 已有两条正测向的频道接近可靠清除，优先完成以立即退出后续扫描。
            if len(belief.directions) >= 2:
                estimate = bearing_line_estimate(belief.directions)
                distance = math.dist(sim.position, estimate) if estimate is not None else float("inf")
                return (0, 0.0, distance)
            # 首测频道先预评估 Q2 二测分数；分数越高，越值得优先投入移动时间。
            if not belief.q2_second_decided:
                belief.q2_second_point(sim.position)
            if LOCAL_TASK_ORDER == "nearest_q2":
                distance = (math.dist(sim.position, belief.q2_second_location)
                            if belief.q2_second_location is not None else float("inf"))
                return (1, distance, -(belief.q2_second_score or 0.0))
            if LOCAL_TASK_ORDER == "balanced_q2":
                distance = (math.dist(sim.position, belief.q2_second_location)
                            if belief.q2_second_location is not None else float("inf"))
                # 任务层只做排序：距离降低平均完成时间，Q2 分数保留几何和可见性收益。
                priority = distance / 1800.0 - TASK_SCORE_WEIGHT * (belief.q2_second_score or 0.0)
                return (1, priority, distance)
            if LOCAL_TASK_ORDER == "q2_service_time":
                if belief.q2_second_location is None or belief.q2_predicted_target is None:
                    return (1, float("inf"), float("inf"))
                # 预测一次 Q2 闭环的服务路程：当前点→二测点→交会源距先验中心。
                # 其只参与频道排队，不参与真正的定位或 /clear 判定。
                service_distance = (math.dist(sim.position, belief.q2_second_location)
                                    + math.dist(belief.q2_second_location, belief.q2_predicted_target))
                return (1, service_distance, -(belief.q2_second_score or 0.0))
            if LOCAL_TASK_ORDER == "low_score":
                return (1, belief.q2_second_score or 0.0, 0.0)
            return (1, -(belief.q2_second_score or 0.0), 0.0)

        return sorted(channels, key=key)

    def process_pending(pending: list[int], remaining_stations: int, total_stations: int) -> None:
        """滚动重规划：每处理一个频道，均从当前位置重算 Q2 候选点与任务次序。"""
        unprocessed = set(pending)
        processed = 0
        while unprocessed and (MAX_Q2_TASKS_PER_STATION <= 0 or processed < MAX_Q2_TASKS_PER_STATION):
            candidates = [channel for channel in unprocessed if channel not in cleared]
            if not candidates:
                return
            channel = local_task_order(candidates)[0]
            refine(channel, remaining_stations=remaining_stations, total_stations=total_stations)
            unprocessed.remove(channel)
            processed += 1

    sim.enter(rid("enter"))
    # 三环巡检中事件触发局部定位：成功清除的频道立即退出后续扫描，
    # 相比“扫完全部频道再定位”，可节省已清除频道的大量 5 s 检测时间。
    stations = survey_stations()
    unvisited_stations = list(stations)
    for station_index in range(len(stations)):
        # Q2 局部任务会改变当前位置；动态访问顺序只缩短回到发现层的空驶距离，
        # 不删除任何巡检点，因此完整布局的发现覆盖集合保持不变。
        if DYNAMIC_SURVEY_ORDER:
            station = min(unvisited_stations, key=lambda point: math.dist(sim.position, point))
            unvisited_stations.remove(station)
        else:
            station = stations[station_index]
            unvisited_stations.remove(station)
        for channel in range(1, 21):
            if channel not in cleared: observe(channel, station)
        # 事件触发：首次 direction 就调用 Q2 二测；后续由第二/第三测向收敛。单轮内按频道顺序执行，
        # 以保持频道切换与当前成功清除早停的时间账本稳定。
        pending = [channel for channel in range(1, 21)
                   if channel not in cleared and len(beliefs[channel].directions) >= 1]
        process_pending(pending, remaining_stations=len(unvisited_stations), total_stations=len(stations))
    # 严格模式只为从未发现的频道追加三角格点扫描。它提供定向朝向无关的发现证书，
    # 但不替代已发现频道的 Q2 主动定位，也不在默认效率模式中强制执行。
    if STRICT_DIRECTIONAL_COVERAGE:
        fallback_stations = triangular_cover_stations()
        for station_index, station in enumerate(fallback_stations):
            unseen = [channel for channel in range(1, 21) if channel not in first_positive]
            if not unseen:
                break
            for channel in unseen:
                observe(channel, station)
            pending = [channel for channel in range(1, 21)
                       if channel not in cleared and len(beliefs[channel].directions) >= 1]
            process_pending(pending, remaining_stations=len(fallback_stations)-station_index-1,
                            total_stations=len(fallback_stations))
    # 终阶段不把 no_signal 当作不存在：对仅有一次正测向的频道强制补一次 Q2 二测，
    # 对已有两次测向的频道继续局部恢复，避免任何已发现频道停留在未完成状态。
    for channel in range(1, 21):
        if channel not in cleared and len(beliefs[channel].directions) == 1:
            refine(channel, force_second_measure=True)
        elif channel not in cleared and len(beliefs[channel].directions) >= 2:
            refine(channel)
    mode_suffix = "_strict" if STRICT_DIRECTIONAL_COVERAGE else ""
    exit_response = sim.exit(rid("exit")); sim.export_log(LOG / f"q4_risk_belief_seed{seed}{mode_suffix}.json")

    source_rows = [{"频道": c, "首次正观测虚拟时间(s)": first_positive[c], "清除成功虚拟时间(s)": clear_time[c],
                    "定位清除耗时(s)": clear_time[c]-first_positive[c], "正测向次数": len(beliefs[c].directions),
                    "Q2首次主动二测评分": beliefs[c].q2_second_score,
                    "Q2首次主动二测阈值": beliefs[c].q2_second_threshold,
                    "Q2几何质量": beliefs[c].q2_selected_geometry,
                    "Q2接收保障": beliefs[c].q2_selected_receive,
                    "Q2归一化移动代价": beliefs[c].q2_selected_move,
                    "Q2源距四分位距(m)": beliefs[c].q2_range_iqr_m,
                    "Q2不确定性分级": beliefs[c].q2_uncertainty_band,
                    "最终信念状态数": len(beliefs[c].states)} for c in sorted(clear_time)]
    durations = [r["定位清除耗时(s)"] for r in source_rows]
    summary = exit_response["summary"]
    report = {"随机种子":seed, "Q2早触发评分阈值下限":EARLY_Q2_SCORE_MIN, "Q2早触发评分阈值上限":EARLY_Q2_SCORE_MAX,
              "Q2几何权重":Q2_W_GEO, "Q2接收保障权重":Q2_W_RECEIVE, "Q2移动代价权重":Q2_W_MOVE,
              "二测提前清除误差界(m)":TWO_BEARING_CLEAR_BOUND_M, "局部任务排序":LOCAL_TASK_ORDER,
              "二测交会点试清除":TRY_TWO_BEARING_CLEAR,
              "二测局部试清除半径(m)":TWO_BEARING_PROBE_RADIUS_M,
              "Q2镜像补测":SYMMETRIC_Q2_PROBE,
              "发现巡检布局":SURVEY_LAYOUT,
              "发现层动态访问":DYNAMIC_SURVEY_ORDER,
              "软接收概率":SOFT_RECEIVE_PROBABILITY,
              "每巡检点Q2任务上限":MAX_Q2_TASKS_PER_STATION,
              "接收先验加权信念图":WEIGHTED_BELIEF,
              "严格定向覆盖兜底":STRICT_DIRECTIONAL_COVERAGE,
              "源总数":summary["source_count"], "已清除数":summary["cleared_count"], "清除比例":summary["clear_rate"],
              "虚拟时间(s)":summary["virtual_time_s"], "检测次数":sum(e["action"]=="measure" for e in sim.log), "清除尝试次数":sum(e["action"]=="clear" for e in sim.log),
              "Q2首次主动二测次数":sum(b.q2_second_attempted for b in beliefs.values()),
              "最快单源定位清除时间(s)":min(durations), "平均单源定位清除时间(s)":sum(durations)/len(durations), "最慢单源全流程时间(s)":max(durations)}
    for filename, rows in (("Q4风险信念闭环测试.csv", [report]), ("Q4风险信念单源时间明细.csv", source_rows)):
        with (TAB/filename).open("w", newline="", encoding="utf-8-sig") as file:
            writer=csv.DictWriter(file, list(rows[0])); writer.writeheader(); writer.writerows(rows)

    fig, ax = plt.subplots(figsize=(7.2,7.0)); ax.add_patch(plt.Circle((0,0),1800,fill=False,ec=GRAY,ls="--",lw=1.4,label="1800 m 源分布圆"))
    points=survey_stations(); ax.scatter(*zip(*points),c=GRAY,s=20,label="多方位风险覆盖点"); ax.plot(*zip(*trace),c=BLUE,lw=.7,alpha=.65,label="策略动作轨迹"); ax.scatter(0,0,c=DARK,s=65,zorder=4,label="起点")
    ax.set(aspect="equal",xlabel="东向坐标 x / m",ylabel="北向坐标 y / m",title="Q4 风险信念地图与主动回补闭环测试"); ax.grid(alpha=.2); ax.legend(fontsize=8); fig.tight_layout()
    for suffix in ("png","pdf"): fig.savefig(FIG/f"q4_risk_belief_seed{seed}{mode_suffix}.{suffix}",dpi=300,bbox_inches="tight",facecolor="white")
    plt.close(fig); print(report)
    return report


if __name__ == "__main__": main()

