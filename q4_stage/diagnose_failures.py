"""复现指定案例并输出未清除频道状态，仅用于离线诊断。"""
import argparse
import random

from q4_experiment import DirectionalSimulator, clone_sources, random_mixed_sources
from q4_optimize import STRATEGIES


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--cases", required=True, help="逗号分隔案例编号")
    parser.add_argument("--strategy", default="L950_C2")
    args = parser.parse_args()
    wanted = {int(value) for value in args.cases.split(",")}
    rng = random.Random(args.seed)
    for index in range(1, max(wanted) + 1):
        sources = random_mixed_sources(rng, None, 0.5)
        if index not in wanted:
            continue
        sim = DirectionalSimulator(clone_sources(sources), args.seed * 100000 + index)
        agent = STRATEGIES[args.strategy](sim)
        result = agent.run()
        print("CASE", index, result)
        for source in sources:
            state = agent.state[source.channel]
            if not state.cleared:
                print({
                    "channel": source.channel,
                    "position": source.position,
                    "receive_radius": source.receive_radius,
                    "beam_direction": source.beam_direction,
                    "discovered": state.discovered,
                    "observations": state.observations,
                    "attempts": state.attempts,
                    "no_signal_count": len(state.no_signal_points),
                    "failed_clear_points": state.failed_clear_points,
                    "exhausted": state.exhausted,
                })


if __name__ == "__main__":
    main()
