import os, sys, json, logging, time, pprint, tqdm
import numpy as np
import torch
from torch.utils.data import DataLoader
from transformers import AutoTokenizer, AdamW, get_linear_schedule_with_warmup
from model import GenerativeModel
from dataset import GenDataset
from utils import Summarizer, compute_f1
from argparse import ArgumentParser, Namespace
import ipdb

# configuration
parser = ArgumentParser()
parser.add_argument('-c', '--config', required=True)
args = parser.parse_args()
with open(args.config) as fp:
    config = json.load(fp)
config.update(args.__dict__)
config = Namespace(**config)

# fix random seed
np.random.seed(config.seed)
torch.manual_seed(config.seed)
torch.backends.cudnn.enabled = False

# logger and summarizer
timestamp = time.strftime('%Y%m%d_%H%M%S', time.localtime())
output_dir = os.path.join(config.output_dir, timestamp)
if not os.path.exists(output_dir):
    os.makedirs(output_dir)
log_path = os.path.join(output_dir, "train.log")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(message)s', datefmt='[%Y-%m-%d %H:%M:%S]', 
                    handlers=[logging.FileHandler(os.path.join(output_dir, "train.log")), logging.StreamHandler()])
logger = logging.getLogger(__name__)
logger.info(f"\n{pprint.pformat(vars(config), indent=4)}")
summarizer = Summarizer(output_dir)

# set GPU device
torch.cuda.set_device(config.gpu_device)

# check valid styles
assert np.all([style in ['event_type', 'event_type_sent', 'static_keywords', 'template'] for style in config.input_style])
assert np.all([style in ['trigger:sentence', 'argument:sentence'] for style in config.output_style])

# output
with open(os.path.join(output_dir, 'config.json'), 'w') as fp:
    json.dump(vars(config), fp, indent=4)
best_model_path = os.path.join(output_dir, 'best_model.mdl')
dev_prediction_path = os.path.join(output_dir, 'pred.dev.json')
test_prediction_path = os.path.join(output_dir, 'pred.test.json')
dev_keyword_prediction_path = os.path.join(output_dir, 'pred.keyword.dev.json')
test_keyword_prediction_path = os.path.join(output_dir, 'pred.keyword.test.json')

# tokenizer
tokenizer = AutoTokenizer.from_pretrained(config.model_name, cache_dir=config.cache_dir)
special_tokens = ['<Trigger>', '<sep>', '<and>', '<Keyword>', '</Keyword>']
tokenizer.add_tokens(special_tokens)

# load data
train_set = GenDataset(tokenizer, config.max_length, config.train_finetune_file, config.max_output_length)
dev_set = GenDataset(tokenizer, config.max_length, config.dev_finetune_file, config.max_output_length)
test_set = GenDataset(tokenizer, config.max_length, config.test_finetune_file, config.max_output_length)
keyword_train_set = GenDataset(tokenizer, config.max_length, config.keyword_train_finetune_file, config.max_output_length)
keyword_dev_set = GenDataset(tokenizer, config.max_length, config.keyword_dev_finetune_file, config.max_output_length)
keyword_test_set = GenDataset(tokenizer, config.max_length, config.keyword_test_finetune_file, config.max_output_length)
train_batch_num = len(train_set) // config.train_batch_size + (len(train_set) % config.train_batch_size != 0)
dev_batch_num = len(dev_set) // config.eval_batch_size + (len(dev_set) % config.eval_batch_size != 0)
test_batch_num = len(test_set) // config.eval_batch_size + (len(test_set) % config.eval_batch_size != 0)

# initialize the model
model = GenerativeModel(config, tokenizer)
model.cuda(device=config.gpu_device)

# optimizer
param_groups = [{'params': model.parameters(), 'lr': config.learning_rate, 'weight_decay': config.weight_decay}]
optimizer = AdamW(params=param_groups)
schedule = get_linear_schedule_with_warmup(optimizer,
                                           num_warmup_steps=train_batch_num*config.warmup_epoch,
                                           num_training_steps=train_batch_num*config.max_epoch)


def evaluation(model, dataset, keyword_dataset, config, progress):
    if config.dataset == "ace05e" or config.dataset == "ace05ep":
        import template_ace
        template_file = "template_ace"
    elif config.dataset == "ere":
        import template_ere
        template_file = "template_ere"

    model.eval()
    write_output = []
    keyword_write_output = []
    eval_gold_key_num, eval_pred_key_num, eval_match_key_num = 0, 0, 0
    eval_gold_tri_num, eval_pred_tri_num, eval_match_tri_num = 0, 0, 0
    eval_gold_arg_num, eval_pred_arg_num, eval_match_arg_id, eval_match_arg_cls = 0, 0, 0, 0
    
    for batch_idx, (batch, keyword_batch) in enumerate(zip(DataLoader(dataset, batch_size=config.eval_batch_size, 
                                                shuffle=False, collate_fn=dataset.collate_fn),
                                            DataLoader(keyword_dataset, batch_size=config.eval_batch_size, 
                                                shuffle=False, collate_fn=keyword_dataset.collate_fn))):
        progress.update(1)
        keyword_pred_text = model.predict(keyword_batch, num_beams=config.beam_size, max_length=config.max_output_length)
        keyword_gold_text = keyword_batch.target_text
        keyword_input_text = keyword_batch.input_text
        keyword_pred_objects = []
        for i_text, g_text, p_text, info, keyword_info in zip(keyword_input_text, keyword_gold_text, keyword_pred_text, batch.infos, keyword_batch.infos):
            theclass = getattr(sys.modules[template_file], info[1].replace(':', '_').replace('-', '_'), False)
            assert theclass
            template = theclass(config.input_style, config.output_style, info[2], info[1], info[0])
            
            # decode predictions
            pred_object = template.decode_keywords(p_text)
            keyword_pred_objects.append(pred_object)
            
            # calculate scores
            sub_scores = template.evaluate_keywords(pred_object)
            eval_gold_key_num += sub_scores['gold_num']
            eval_pred_key_num += sub_scores['pred_num']
            eval_match_key_num += sub_scores['match_num']
            keyword_write_output.append({
                'input text': i_text,
                'gold text': g_text,
                'pred text': p_text,
                'gold keyword spans': template.get_keyword_spans(),
                'pred keyword spans': pred_object,
                'score': sub_scores,
                # 'gold info': keyword_info
            })

        pred_text = model.predict(batch, num_beams=config.beam_size, max_length=config.max_output_length)
        gold_text = batch.target_text
        input_text = batch.input_text
        for i_text, g_text, p_text, info in zip(input_text, gold_text, pred_text, batch.infos):
            theclass = getattr(sys.modules[template_file], info[1].replace(':', '_').replace('-', '_'), False)
            assert theclass
            template = theclass(config.input_style, config.output_style, info[2], info[1], info[0])
            
            # decode predictions
            pred_object = template.decode(p_text)
            gold_object = template.trigger_span + [_ for _ in template.get_converted_gold()]
            
            # calculate scores
            sub_scores = template.evaluate(pred_object)
            eval_gold_tri_num += sub_scores['gold_tri_num']
            eval_pred_tri_num += sub_scores['pred_tri_num']
            eval_match_tri_num += sub_scores['match_tri_num']
            eval_gold_arg_num += sub_scores['gold_arg_num']
            eval_pred_arg_num += sub_scores['pred_arg_num']
            eval_match_arg_id += sub_scores['match_arg_id']
            eval_match_arg_cls += sub_scores['match_arg_cls']
            write_output.append({
                'input text': i_text,
                'gold text': g_text,
                'pred text': p_text,
                'gold triggers': gold_object,
                'pred triggers': pred_object,
                'score': sub_scores,
                'gold events': info[0]
            })
    
    eval_scores = {
        'keyword_id': compute_f1(eval_pred_key_num, eval_gold_key_num, eval_match_key_num),
        'tri_id': compute_f1(eval_pred_tri_num, eval_gold_tri_num, eval_match_tri_num),
        'arg_id': compute_f1(eval_pred_arg_num, eval_gold_arg_num, eval_match_arg_id),
        'arg_cls': compute_f1(eval_pred_arg_num, eval_gold_arg_num, eval_match_arg_cls)
    }

    # print scores
    logger.info("---------------------------------------------------------------------")
    logger.info('Keyword I  - P: {:5.2f} ({:4d}/{:4d}), R: {:5.2f} ({:4d}/{:4d}), F: {:5.2f}'.format(
        eval_scores['keyword_id'][0] * 100.0, eval_match_key_num, eval_pred_key_num, 
        eval_scores['keyword_id'][1] * 100.0, eval_match_key_num, eval_gold_key_num, eval_scores['keyword_id'][2] * 100.0))
    logger.info("---------------------------------------------------------------------")
    logger.info('Trigger I  - P: {:5.2f} ({:4d}/{:4d}), R: {:5.2f} ({:4d}/{:4d}), F: {:5.2f}'.format(
        eval_scores['tri_id'][0] * 100.0, eval_match_tri_num, eval_pred_tri_num, 
        eval_scores['tri_id'][1] * 100.0, eval_match_tri_num, eval_gold_tri_num, eval_scores['tri_id'][2] * 100.0))
    logger.info("---------------------------------------------------------------------")
    logger.info('Role I     - P: {:5.2f} ({:4d}/{:4d}), R: {:5.2f} ({:4d}/{:4d}), F: {:5.2f}'.format(
        eval_scores['arg_id'][0] * 100.0, eval_match_arg_id, eval_pred_arg_num, 
        eval_scores['arg_id'][1] * 100.0, eval_match_arg_id, eval_gold_arg_num, eval_scores['arg_id'][2] * 100.0))
    logger.info('Role C     - P: {:5.2f} ({:4d}/{:4d}), R: {:5.2f} ({:4d}/{:4d}), F: {:5.2f}'.format(
        eval_scores['arg_cls'][0] * 100.0, eval_match_arg_cls, eval_pred_arg_num, 
        eval_scores['arg_cls'][1] * 100.0, eval_match_arg_cls, eval_gold_arg_num, eval_scores['arg_cls'][2] * 100.0))
    logger.info("---------------------------------------------------------------------")

    return eval_scores, write_output, keyword_write_output



# start training
logger.info("Start training ...")
summarizer_step = 0
best_dev_epoch = -1
best_dev_scores = {
    'tri_id': (0.0, 0.0, 0.0),
    'arg_id': (0.0, 0.0, 0.0),
    'arg_cls': (0.0, 0.0, 0.0)
}
for epoch in range(1, config.max_epoch+1):
    logger.info(log_path)
    logger.info(f"Epoch {epoch}")
    
    # training
    progress = tqdm.tqdm(total=train_batch_num, ncols=75, desc='Train {}'.format(epoch))
    model.train()
    optimizer.zero_grad()
    for batch_idx, (batch, keyword_batch) in enumerate(zip(DataLoader(train_set, batch_size=config.train_batch_size // config.accumulate_step, 
                                                 shuffle=True, drop_last=False, collate_fn=train_set.collate_fn), 
                                          DataLoader(keyword_train_set, batch_size=config.train_batch_size // config.accumulate_step, 
                                                 shuffle=True, drop_last=False, collate_fn=keyword_train_set.collate_fn))):        
        # forard model        
        ee_loss = model(batch)
        keyword_loss = model(keyword_batch)
        loss = ee_loss + keyword_loss
        
        # record loss
        summarizer.scalar_summary('train/loss', loss, summarizer_step)
        summarizer_step += 1
        
        loss = loss * (1 / config.accumulate_step)
        loss.backward()

        if (batch_idx + 1) % config.accumulate_step == 0:
            progress.update(1)
            torch.nn.utils.clip_grad_norm_(model.parameters(), config.grad_clipping)
            optimizer.step()
            schedule.step()
            optimizer.zero_grad()
    progress.close()

    # eval dev set
    best_dev_flag = False
    progress = tqdm.tqdm(total=dev_batch_num, ncols=75, desc='Dev {}'.format(epoch))
    dev_scores, write_output, keyword_write_output = evaluation(model, dev_set, keyword_dev_set, config, progress)
    progress.close()
        
    # check best dev model
    if dev_scores['arg_cls'][2] > best_dev_scores['arg_cls'][2]:
        best_dev_flag = True
        
    # if best dev, save model and evaluate test set
    # if best_dev_flag:    
    if True:    
        best_dev_scores = dev_scores
        best_dev_epoch = epoch
        
        # save best model
        logger.info('Saving best model')
        torch.save(model.state_dict(), best_model_path)
        
        # save dev result
        with open(dev_prediction_path, 'w') as fp:
            json.dump(write_output, fp, indent=4)
        with open(dev_keyword_prediction_path, 'w') as fp:
            json.dump(keyword_write_output, fp, indent=4)

        # eval test set
        progress = tqdm.tqdm(total=test_batch_num, ncols=75, desc='Test {}'.format(epoch))
        test_scores, write_output, keyword_write_output = evaluation(model, test_set, keyword_test_set, config, progress)
        progress.close()
        
        # save test result
        with open(test_prediction_path, 'w') as fp:
            json.dump(write_output, fp, indent=4)
        with open(test_keyword_prediction_path, 'w') as fp:
            json.dump(keyword_write_output, fp, indent=4)
            
    logger.info({"epoch": epoch, "dev_scores": dev_scores})
    if best_dev_flag:
        logger.info({"epoch": epoch, "test_scores": test_scores})
    logger.info("Current best")
    logger.info({"best_epoch": best_dev_epoch, "best_scores": best_dev_scores})
        
logger.info(log_path)
logger.info("Done!")