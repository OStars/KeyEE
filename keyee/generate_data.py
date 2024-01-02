import os, json, pickle, logging, pprint, random
import numpy as np
from tqdm import tqdm
from dataset import EEDataset
from argparse import ArgumentParser, Namespace
from utils import generate_vocabs
from transformers import AutoTokenizer
from template_base import event_template_generator
import ipdb

# configuration
parser = ArgumentParser()
parser.add_argument('-c', '--config', required=True)
args = parser.parse_args()
with open(args.config) as fp:
    config = json.load(fp)
config.update(args.__dict__)
config = Namespace(**config)

if config.dataset == "ace05e" or config.dataset == "ace05ep":
    import template_ace
    template_file = "template_ace"
elif config.dataset == "ere":
    import template_ere
    template_file = "template_ere"

# fix random seed
random.seed(config.seed)
np.random.seed(config.seed)

# logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(message)s', datefmt='[%Y-%m-%d %H:%M:%S]')
logger = logging.getLogger(__name__)
logger.info(f"\n{pprint.pformat(vars(config), indent=4)}")

def generate_data(data_set, vocab, config):
    inputs = []
    targets = []
    events = []
    
    keyword_inputs = []
    keyword_targets = []
    keywords = []

    def organize_data(data, config):
        inputs = []
        targets = []
        infos = []

        pos_data_ = [dt for dt in data if dt[3]]
        neg_data_ = [dt for dt in data if not dt[3]]
        np.random.shuffle(neg_data_)
        
        # data => (input_str, output_str, self.gold_event, gold_sample, self.event_type, self.tokens)
        for data_ in pos_data_:
            inputs.append(data_[0])
            targets.append(data_[1])
            infos.append((data_[2], data_[4], data_[5]))
        
        neg_data_ = neg_data_[:config.n_negative]
        for data_ in neg_data_:
            inputs.append(data_[0])
            targets.append(data_[1])
            infos.append((data_[2], data_[4], data_[5]))
        
        return inputs, targets, infos

    for data in tqdm(data_set.data):
        event_template = event_template_generator(template_file, data.tokens, data.triggers, data.roles, config.input_style, config.output_style, vocab, True)
        
        event_data, keyword_data = event_template.get_training_data()
        inputs_, targets_, events_ = organize_data(event_data, config)
        inputs.extend(inputs_)
        targets.extend(targets_)
        events.extend(events_)

        inputs_, targets_, keywords_ = organize_data(keyword_data, config)
        keyword_inputs.extend(inputs_)
        keyword_targets.extend(targets_)
        keywords.extend(keywords_)

    return inputs, targets, events, keyword_inputs, keyword_targets, keywords

# check valid styles
assert np.all([style in ['event_type', 'event_type_sent', 'static_keywords', 'template'] for style in config.input_style])
assert np.all([style in ['trigger:sentence', 'argument:sentence'] for style in config.output_style])

# tokenizer
tokenizer = AutoTokenizer.from_pretrained(config.model_name, cache_dir=config.cache_dir)
special_tokens = ['<Trigger>', '<sep>', '<and>',  '<Keyword>', '</Keyword>']
tokenizer.add_tokens(special_tokens)

if not os.path.exists(config.finetune_dir):
    os.makedirs(config.finetune_dir)

# load data
train_set = EEDataset(tokenizer, config.train_file, max_length=config.max_length)
dev_set = EEDataset(tokenizer, config.dev_file, max_length=config.max_length)
test_set = EEDataset(tokenizer, config.test_file, max_length=config.max_length)
vocab = generate_vocabs([train_set, dev_set, test_set])

# save vocabulary
with open('{}/vocab.json'.format(config.finetune_dir), 'w') as f:
    json.dump(vocab, f, indent=4)    

# generate finetune data
train_inputs, train_targets, train_events, train_k_inputs, train_k_targets, train_keywords = generate_data(train_set, vocab, config)
logger.info(f"Generated {len(train_inputs)} training examples from {len(train_set)} instance")

with open('{}/train_input.json'.format(config.finetune_dir), 'w') as f:
    json.dump(train_inputs, f, indent=4)

with open('{}/train_target.json'.format(config.finetune_dir), 'w') as f:
    json.dump(train_targets, f, indent=4)

with open('{}/train_all.pkl'.format(config.finetune_dir), 'wb') as f:
    pickle.dump({
        'input': train_inputs,
        'target': train_targets,
        'all': train_events
    }, f)

with open(os.path.join(config.finetune_dir, 'train_keywords_input.json'), 'w') as f:
    json.dump(train_k_inputs, f, indent=4)

with open(os.path.join(config.finetune_dir, 'train_keywords_target.json'), 'w') as f:
    json.dump(train_k_targets, f, indent=4)

with open(os.path.join(config.finetune_dir, 'train_keywords_all.pkl'), 'wb') as f:
    pickle.dump({
        'input': train_k_inputs,
        'target': train_k_targets,
        'all': train_keywords
    }, f)
    
dev_inputs, dev_targets, dev_events, dev_k_inputs, dev_k_targets, dev_keywords = generate_data(dev_set, vocab, config)
logger.info(f"Generated {len(dev_inputs)} dev examples from {len(dev_set)} instance")

with open('{}/dev_input.json'.format(config.finetune_dir), 'w') as f:
    json.dump(dev_inputs, f, indent=4)

with open('{}/dev_target.json'.format(config.finetune_dir), 'w') as f:
    json.dump(dev_targets, f, indent=4)

with open('{}/dev_all.pkl'.format(config.finetune_dir), 'wb') as f:
    pickle.dump({
        'input': dev_inputs,
        'target': dev_targets,
        'all': dev_events
    }, f)

with open(os.path.join(config.finetune_dir, 'dev_keywords_input.json'), 'w') as f:
    json.dump(dev_k_inputs, f, indent=4)

with open(os.path.join(config.finetune_dir, 'dev_keywords_target.json'), 'w') as f:
    json.dump(dev_k_targets, f, indent=4)

with open(os.path.join(config.finetune_dir, 'dev_keywords_all.pkl'), 'wb') as f:
    pickle.dump({
        'input': dev_k_inputs,
        'target': dev_k_targets,
        'all': dev_keywords
    }, f)
    
test_inputs, test_targets, test_events, test_k_inputs, test_k_targets, test_keywords = generate_data(test_set, vocab, config)
logger.info(f"Generated {len(test_inputs)} test examples from {len(test_set)} instance")

with open('{}/test_input.json'.format(config.finetune_dir), 'w') as f:
    json.dump(test_inputs, f, indent=4)

with open('{}/test_target.json'.format(config.finetune_dir), 'w') as f:
    json.dump(test_targets, f, indent=4)

with open('{}/test_all.pkl'.format(config.finetune_dir), 'wb') as f:
    pickle.dump({
        'input': test_inputs,
        'target': test_targets,
        'all': test_events
    }, f)

with open(os.path.join(config.finetune_dir, 'test_keywords_input.json'), 'w') as f:
    json.dump(test_k_inputs, f, indent=4)

with open(os.path.join(config.finetune_dir, 'test_keywords_target.json'), 'w') as f:
    json.dump(test_k_targets, f, indent=4)

with open(os.path.join(config.finetune_dir, 'test_keywords_all.pkl'), 'wb') as f:
    pickle.dump({
        'input': test_k_inputs,
        'target': test_k_targets,
        'all': test_keywords
    }, f)