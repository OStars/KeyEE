export OMP_NUM_THREADS=4

DATASET="ace05e"
# DATASET="ace05ep"
# DATASET="ere"

python keyee/generate_data.py -c config/config_keyee_${DATASET}.json
python keyee/train.py -c config/config_keyee_${DATASET}.json