export OMP_NUM_THREADS=4

OUTPUT_DIR="output/ace05e_high_resources/multi-task-Keywords-full"
DATASET="ace05e"
# DATASET="ace05ep"
# DATASET="ere"

python keyee/eval.py \
    -c config/config_keyee_${DATASET}.json \
    -e ${OUTPUT_DIR}/best_model.mdl \
    --eval_batch_size 16 \
    --write_file ${OUTPUT_DIR}/eval_result.json \
    --no_dev