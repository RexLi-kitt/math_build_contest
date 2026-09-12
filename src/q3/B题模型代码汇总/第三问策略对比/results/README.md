# results 目录命名说明

- `j_main_1000`、`j_screen20`、`j_smoke3`、`rpred_2x2_1000` 中的 `J_q2_fidelity` 是「第二问候选集口径统一」实验的历史代号；该改动已并入 `Q2FourMetricAgent`（模型 I），与最终模型 J/J+ 无关，详见 `reports/第八轮第二问口径统一.md`。
- 最终模型结果目录：
  - `robustness_jplus/seed_55021`、`seed_24119`：全链 7 模型（C、C+、F、G、I、J、J+）× 1000 局；
  - `jplus_seed90317`：种子 90317 的 J/J+ × 1000 局（该种子的 C..I 见 `robustness/seed_90317`）；
  - `ablation_ring8_200`：8 点环负消融 200 局（种子 314159）；
  - `diagnostics/results/i_to_jplus_metrics_600`：I/J/J+/8 点环的七项指标回测（三种子 × 200 局）。
- `robustness/seed_24119`、`robustness/seed_90317` 与 `faithful_chain_1000` 是 C..I 的历史 1000 局结果，可与上述目录按同种子同局配对（环境只由种子和局号决定）。
