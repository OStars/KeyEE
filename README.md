# KeyEE: Enhancing Low-resource Generative Event Extraction with Auxiliary Keyword Sub-Prompt
Code repository for paper "KeyEE: Enhancing Low-resource Generative Event Extraction with Auxiliary Keyword Sub-Prompt".

Our code is mainly based on [DEGREE](https://github.com/PlusLabNLP/DEGREE). We deeply thank the contribution from the authors of the paper.

## Environment
- torch==1.8.0
- transformers==4.25.1
- protobuf==3.20.3
- tensorboardx==2.6
- lxml==4.9.2
- beautifulsoup4==4.11.2
- bs4==0.0.1
- stanza==1.4.2
- ipdb==0.13.11

```bash
conda create -n keyee python=3.8
conda activate keyee
python -m pip install -r requirements.txt
```

## Datasets

We support `ace05e`, `ace05ep`, and `ere`. 

### Preprocessing
Our preprocessing mainly adapts [DEGREE's](https://github.com/PlusLabNLP/DEGREE) and [OneIE's](https://blender.cs.illinois.edu/software/oneie/) released scripts with minor modifications. We deeply thank the contribution from the authors of the paper. We propose to create a new virtual environment to complete the data preprocessing.

#### `ace05e`
1. Prepare data processed from [DyGIE++](https://github.com/dwadden/dygiepp#ace05-event)
2. Put the processed data into the folder `processed_data/ace05e_dygieppformat`
3. Run `./scripts/process_ace05e.sh`

#### `ace05ep`
1. Download ACE data from [LDC](https://catalog.ldc.upenn.edu/LDC2006T06)
2. Run `./scripts/process_ace05ep.sh`

#### `ere`
1. Download ERE English data from LDC, specifically, "LDC2015E29_DEFT_Rich_ERE_English_Training_Annotation_V2", "LDC2015E68_DEFT_Rich_ERE_English_Training_Annotation_R2_V2", "LDC2015E78_DEFT_Rich_ERE_Chinese_and_English_Parallel_Annotation_V2"
2. Collect all these data under a directory with such setup:
```
ERE
├── LDC2015E29_DEFT_Rich_ERE_English_Training_Annotation_V2
│     ├── data
│     ├── docs
│     └── ...
├── LDC2015E68_DEFT_Rich_ERE_English_Training_Annotation_R2_V2
│     ├── data
│     ├── docs
│     └── ...
└── LDC2015E78_DEFT_Rich_ERE_Chinese_and_English_Parallel_Annotation_V2
      ├── data
      ├── docs
      └── ...
```
3. Run `./scripts/process_ere.sh`

The above scripts will generate processed data (including the full training set and the low-resourece sets) in `./process_data`.


## Training

All training configurations are listed in `config` directory, you should check your configurations before experiments.

Run `./scripts/train.sh` or use the following commands:

Generate data
```bash
python keyee/generate_data.py -c config/config_keyee_ace05e.json
```

Train
```bash
python keyee/train.py -c config/config_keyee_ace05e.json
```

## Evaluation

We negatively sampled those sentences that were missing a certain event type during the training phase to reduce training time, which means we did not retrain full dev and test dataset in training stage. So it is important to do extra evaluation on the whole test datset. 

To do this, you can run `./scripts/eval.sh` or use the following commands:

```bash
python keyee/eval.py \
    -c config/config_keyee_ace05e.json \
    -e $OUTPUT_DIR/best_model.mdl \
    --eval_batch_size 16 \
    --write_file $OUTPUT_DIR/eval_result.json \
    --no_dev
```

## Citation

If you find that the code is useful in your research, please consider citing our paper.

    @ARTICLE{BDMA2024_KeyEE,
        author  = {Duan, Junwen and Liao, Xincheng and An, Ying and Wang, Jianxin},
        journal = {Big Data Mining and Analytics}, 
        title   = {KeyEE: Enhancing Low-Resource Generative Event Extraction with Auxiliary Keyword Sub-Prompt}, 
        year    = {2024},
        volume  = {7},
        number  = {2},
        pages   = {547-560},,
        doi     = {10.26599/BDMA.2023.9020036}
    }


## Contact

If you have any issue, please contact Xincheng Liao at (ostars@csu.edu.cn)