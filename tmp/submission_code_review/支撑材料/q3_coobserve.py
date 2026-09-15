# 功能：在主动测量停靠点对其它已发现未清除频道做"顺便测量"，按单位时间信息价值筛选前几个。
from __future__ import annotations

import math

MIN_RECEIVE_R = 1000.0        # 保证接收半径下界
MIN_P_REC = 0.60              # 参与共观测的接收概率下限
VALUE_PER_SECOND_MIN = 0.035  # 单位时间价值下限（一次测量 6 s）
MAX_COOBSERVATIONS_CPLUS = 3  # C+~J：环点每站最多 3 个
MAX_COOBSERVATIONS_JPLUS = 5  # J+：预算下限提高到 5（原点仍为 3）
MEASURE_SECONDS = 6.0


def wrap(angle_deg):
    return (angle_deg + 180.0) % 360.0 - 180.0


def bearing(a, b):
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def coobserve(agent, point, primary_channel, max_coobservations=MAX_COOBSERVATIONS_CPLUS):
    """已到达 point 测完主频道后，挑选值得"顺便测量"的其它频道并按价值降序执行。

    不增加任何移动，只花 6 s 测量时间；因此判据是单位时间信息价值
        value = p_rec × 交会质量 / 6 s，
    其中 p_rec 为候选点保证接收的样本占比，交会质量为与历史各站交角 sin² 的最大值均值。
    """
    choices = []
    for channel, st in agent.state.items():
        if channel == primary_channel or st.cleared or st.exhausted or not st.discovered:
            continue
        if len(st.observations) >= 5 or any(math.dist(point, old) <= 1.0 for old in st.probed_points):
            continue
        if agent._clear_decision(st) is not None:
            continue  # 已可清除的源不必再补测
        samples = list(agent._snapshot(st).samples)
        if not samples:
            continue
        receive = [target for target in samples if math.dist(point, target) <= MIN_RECEIVE_R]
        p_rec = len(receive) / len(samples)
        if p_rec < MIN_P_REC:
            continue
        quality = sum(max((math.sin(math.radians(
            wrap(bearing(station, target) - bearing(point, target)))) ** 2
            for station, _ in st.observations), default=0.0)
            for target in receive) / len(receive)
        value_per_second = p_rec * quality / MEASURE_SECONDS
        if value_per_second >= VALUE_PER_SECOND_MIN:
            choices.append((value_per_second, channel))
    for _, channel in sorted(choices, reverse=True)[:max_coobservations]:
        agent.observe(point, channel)
        agent.state[channel].attempts += 1
        agent.co_measurements += 1
