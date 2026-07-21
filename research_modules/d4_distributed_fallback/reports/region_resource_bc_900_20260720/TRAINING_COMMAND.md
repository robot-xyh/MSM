# D4 行为克隆训练命令

```bash
PYTHONPATH=research_modules/d4_distributed_fallback python3 -m d4_distributed_fallback.region_resource_training_cli train-bc --dataset research_modules/scalable_3d_simulation/outputs/learning_generation_v1_multibatchfix/learning_dataset/d4_region --output-dir research_modules/d4_distributed_fallback/outputs/region_resource_bc_900_20260720 --seed 20260720 --hidden-dim 64 --message-passing-steps 2 --epochs 80 --batch-size 32 --learning-rate 0.001 --weight-decay 1e-05 --max-grad-norm 1.0 --patience 12 --device cpu --torch-num-threads 1 --model-version d4-region-bc-900-development-v1 --d6-audit-frame-count 1798 --d6-unattributed-transition-frame-count 898 --d6-reward-available-count 0 --d6-causal-label-available-count 0 --d6-counterfactual-available-count 0 --tracked-results-dir research_modules/d4_distributed_fallback/reports/region_resource_bc_900_20260720 --bundle-locator research_modules/d4_distributed_fallback/outputs/region_resource_bc_900_20260720
```
