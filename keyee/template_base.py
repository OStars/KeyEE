import sys
from utils import BasicTokenizer

BASIC_TOKENIZER = BasicTokenizer(do_lower_case=False, never_split=["<Keyword>", "</Keyword>"])

class event_template_generator():
    def __init__(self, template_file, passage, triggers, roles, input_style, output_style, vocab, instance_base=False):
        """
        generate strctured information for events
        
        args:
            passage(List): a list of tokens
            triggers(List): a list of triggers
            roles(List): a list of Roles
            input_style(List): List of elements; elements belongs to INPUT_STYLE_SET
            input_style(List): List of elements; elements belongs to OUTPUT_STYLE_SET
            instance_base(Bool): if instance_base, we generate only one pair (use for trigger generation), else, we generate trigger_base (use for argument generation)
        """
        self.raw_passage = passage
        self.triggers = triggers
        self.roles = roles
        self.events = self.process_events(passage, triggers, roles)
        self.input_style = input_style
        self.output_style = output_style
        self.vocab = vocab
        self.event_templates = []
        if instance_base:
            for e_type in self.vocab['event_type_itos']:
                theclass = getattr(sys.modules[template_file], e_type.replace(':', '_').replace('-', '_'), False)
                if theclass:
                    self.event_templates.append(theclass(self.input_style, self.output_style, passage, e_type, self.events))
                else:
                    print(e_type)

        else:
            for event in self.events:
                theclass = getattr(sys.modules[template_file], event['event type'].replace(':', '_').replace('-', '_'), False)
                assert theclass
                self.event_templates.append(theclass(self.input_style, self.output_style, event['tokens'], event['event type'], event))
        self.data = [x.generate_pair(x.trigger_text) for x in self.event_templates]
        self.data = [x for x in self.data if x]
        self.keyword_data = [x.generate_keyword_pair() for x in self.event_templates]
        self.keyword_data = [x for x in self.keyword_data if x]

    def get_training_data(self):
        return self.data, self.keyword_data

    def process_events(self, passage, triggers, roles):
        """
        Given a list of token and event annotation, return a list of structured event

        structured_event:
        {
            'trigger text': str,
            'trigger span': (start, end),
            'event type': EVENT_TYPE(str),
            'arguments':{
                ROLE_TYPE(str):[{
                    'argument text': str,
                    'argument span': (start, end)
                }],
                ROLE_TYPE(str):...,
                ROLE_TYPE(str):....
            }
            'passage': PASSAGE
        }
        """
        
        events = {trigger: [] for trigger in triggers}

        for argument in roles:
            trigger = argument[0]
            events[trigger].append(argument)
        
        event_structures = []
        for trigger, arguments in events.items():
            eve_type = trigger[2]
            eve_text = ' '.join(passage[trigger[0]:trigger[1]])
            eve_span = (trigger[0], trigger[1])
            argus = {}
            for argument in arguments:
                role_type = argument[1][2]
                if role_type not in argus.keys():
                    argus[role_type] = []
                argus[role_type].append({
                    'argument text': ' '.join(passage[argument[1][0]:argument[1][1]]),
                    'argument span': (argument[1][0], argument[1][1]),
                })
            event_structures.append({
                'trigger text': eve_text,
                'trigger span': eve_span,
                'event type': eve_type,
                'arguments': argus,
                'passage': ' '.join(passage),
                'tokens': passage
            })
        return event_structures


class event_template():
    def __init__(self, input_style, output_style, passage, event_type, gold_event=None):
        self.input_style = input_style
        self.output_style = output_style
        self.output_template = self.get_output_template()
        self.passage = ' '.join(passage)
        self.tokens = passage
        self.event_type = event_type
        if gold_event is not None:
            self.gold_event = gold_event
            if isinstance(gold_event, list):
                # instance base
                self.trigger_text = " and ".join([x['trigger text'] for x in gold_event if x['event type']==event_type])
                self.trigger_span = [x['trigger span'] for x in gold_event if x['event type']==event_type]
                self.arguments = [x['arguments'] for x in gold_event if x['event type']==event_type]
            else:
                # trigger base
                self.trigger_text = gold_event['trigger text']
                self.trigger_span = [gold_event['trigger span']]
                self.arguments = [gold_event['arguments']]         
        else:
            self.gold_event = None
        
    @classmethod
    def get_keywords(self):
        pass

    def get_keywords_text_span(self):
        keywords = []
        if self.gold_event:
            keywords.extend([x['trigger text'] for x in self.gold_event if x['event type']==self.event_type])
            keywords.extend(info['argument text'] for argument in self.arguments 
                                for _, infos in argument.items() for info in infos)

        return list(set(keywords))

    def get_keyword_spans(self):
        keyword_spans = []
        if self.gold_event:
            keyword_spans.extend([x['trigger span'] for x in self.gold_event if x['event type']==self.event_type])
            keyword_spans.extend(info['argument span'] for argument in self.arguments 
                                for _, infos in argument.items() for info in infos)

        return list(set(keyword_spans))

    def generate_pair(self, query_trigger, tokenizer=None):
        """
        Generate model input sentence and output sentence pair
        """
        input_str = self.generate_input_str(query_trigger)
        output_str, gold_sample = self.generate_output_str(query_trigger)

        return (input_str, output_str, self.gold_event, gold_sample, self.event_type, self.tokens)

    def generate_input_str(self, query_trigger):
        return None

    def generate_output_str(self, query_trigger):
        return (None, False)

    def generate_keyword_pair(self):
        """
        Generate model input sentence and output sentence pair
        """
        input_str = self.generate_keywords_input_str()
        output_str, output_tokens, gold_keywords_spans, gold_sample = self.generate_keywords_output_str()
        # output_str, output_tokens, gold_keywords_spans, gold_sample = self.generate_natural_keywords_output_str()
        return (input_str, output_str, gold_keywords_spans, gold_sample, self.event_type, self.tokens)

    def generate_keywords_input_str(self):
        # input_str = self.passage
        # input_str += ' \n {}'.format("Extract keywords for " + self.event_type + " event")
        # return input_str
        return None
    
    # 在原句子中插入 <keyword></keyword> 标签把关键词特别标注出来
    def generate_keywords_output_str(self):
        keyword_spans = self.get_keyword_spans()
        keyword_spans = sorted(list(set(keyword_spans)), key=lambda x: x[0])
        lefts = [span[0] for span in keyword_spans] + [len(self.tokens)]
        rights = [span[1] for span in keyword_spans] + [len(self.tokens)]
        output_tokens = []
        l_index, r_index, t_index = 0, 0, 0
        while(t_index < len(self.tokens)):
            if r_index < len(rights) and l_index < len(lefts):
                if rights[r_index] <= lefts[l_index] and rights[r_index] <= t_index:
                    output_tokens.append('</Keyword>')
                    r_index += 1
                elif lefts[l_index] <= t_index:
                    output_tokens.append('<Keyword>')
                    l_index += 1
                else:
                    output_tokens.append(self.tokens[t_index])
                    t_index += 1
            else:
                output_tokens.append(self.tokens[t_index])
                t_index += 1
        
        return ' '.join(output_tokens), output_tokens, keyword_spans, len(keyword_spans) != 0

    # 直接生成 Event keywords such as ... 这样的输出
    def generate_natural_keywords_output_str(self):
        keywords = self.get_keywords_text_span()
        output = "Event keywords such as " + ", ".join(keywords)
        output = output.strip()
        
        return output, output.split(), keywords, len(keywords) != 0
    
    # # 插入 <keyword></keyword> 标签的解码方式
    def decode_keywords(self, prediction):
        # pred_tokens = prediction.split()
        pred_tokens = BASIC_TOKENIZER.tokenize(prediction)
        special_num = 0
        pos_mapping = {}
        for index, token in enumerate(pred_tokens):
            if token == '<Keyword>':
                special_num += 1
                pos_mapping[index] = -1
            elif token == '</Keyword>':
                pos_mapping[index] = index - special_num
                special_num += 1
            else:
                pos_mapping[index] = index - special_num

        label_stack = []
        index_stack = []
        pred_keyword_spans = []
        # 用 try 包裹防止出现 <Keyword> </Keyword> 嵌套错误的情况
        try:
            for index, token in enumerate(pred_tokens):
                if token == '<Keyword>':
                    label_stack.append('<Keyword>')
                    index_stack.append(index+1)
                elif token == '</Keyword>':
                    if label_stack[-1] == '<Keyword>':
                        label_stack.pop()
                        pred_keyword_spans.append((index_stack.pop(), index))
                    else:
                        break
        except:
            pass
        
        keyword_spans = []
        for span in pred_keyword_spans:
            keyword_spans.append((pos_mapping[span[0]], pos_mapping[span[1]]))
        
        return keyword_spans

    # 直接生成 Event keywords such as ... 的解码
    # def decode_keywords(self, prediction):
    #     pred_keywords = []
    #     try:
    #         pred_keywords = prediction.split("Event keywords such as ")[1]
    #         pred_keywords = pred_keywords.split(",")
    #         pred_keywords = [keyword.strip() for keyword in pred_keywords if keyword.strip()]
    #     except:
    #         pass
        
    #     return pred_keywords
    
    def evaluate_keywords(self, pred_spans):
        pred_spans = list(set(pred_spans))
        # gold_spans = self.get_keywords_text_span()
        gold_spans = self.get_keyword_spans() # <keyword></keyword> 评估
        gold_num = len(gold_spans)
        pred_num = len(pred_spans)
        match_num = 0
        for pred in pred_spans:
            if pred in gold_spans:
                match_num += 1
        
        return {
            'gold_num': gold_num,
            'pred_num': pred_num,
            'match_num': match_num
        }

    def decode(self, prediction):
        pass

    def evaluate(self, predict_output):
        assert self.gold_event is not None
        # categorize prediction
        pred_trigger = []
        pred_argument = []
        for pred in predict_output:
            if pred[1] == self.event_type:
                pred_trigger.append(pred)
            else:
                pred_argument.append(pred)
        # trigger score
        gold_tri_num = len(self.trigger_span)
        pred_tris = []
        for pred in pred_trigger:
            pred_span = self.predstr2span(pred[0])
            if pred_span[0] > -1:
                pred_tris.append((pred_span[0], pred_span[1], pred[1]))
        pred_tri_num = len(pred_tris)
        match_tri = 0
        for pred in pred_tris:
            id_flag = False
            for gold_span in self.trigger_span:
                if gold_span[0] == pred[0] and gold_span[1] == pred[1]:
                    id_flag = True
            match_tri += int(id_flag)

        # argument score
        converted_gold = self.get_converted_gold()
        gold_arg_num = len(converted_gold)
        pred_arg = []
        for pred in pred_argument:
            # find corresponding trigger
            pred_span = None
            if isinstance(self.gold_event, list):
                # end2end case
                try:
                    # we need this ``try'' because we cannot gurantee the model will be bug-free on the matching
                    cor_tri = pred_trigger[pred[2]['cor tri cnt']]
                    cor_tri_span = self.predstr2span(cor_tri[0])[0]
                    if cor_tri_span > -1:
                        pred_span = self.predstr2span(pred[0], cor_tri_span)
                    else:
                        continue
                except Exception as e:
                    print(e)
            else:
                # argument only case
                pred_span = self.predstr2span(pred[0], self.trigger_span[0][0])
            if (pred_span is not None) and (pred_span[0] > -1):
                pred_arg.append((pred_span[0], pred_span[1], pred[1]))
        pred_arg = list(set(pred_arg))
        pred_arg_num = len(pred_arg)
        
        target = converted_gold
        match_id = 0
        match_type = 0
        for pred in pred_arg:
            id_flag = False
            id_type = False
            for gold in target:
                if gold[0]==pred[0] and gold[1]==pred[1]:
                    id_flag = True
                    if gold[2] == pred[2]:
                        id_type = True
                        break
            match_id += int(id_flag)
            match_type += int(id_type)
        return {
            'gold_tri_num': gold_tri_num, 
            'pred_tri_num': pred_tri_num,
            'match_tri_num': match_tri,
            'gold_arg_num': gold_arg_num,
            'pred_arg_num': pred_arg_num,
            'match_arg_id': match_id,
            'match_arg_cls': match_type
        }
    
    def get_converted_gold(self):
        converted_gold = []
        for argu in self.arguments:
            for arg_type, arg_list in argu.items():
                for arg in arg_list:
                    converted_gold.append((arg['argument span'][0], arg['argument span'][1], arg_type))
        return list(set(converted_gold))
    
    def predstr2span(self, pred_str, trigger_idx=None):
        sub_words = [_.strip() for _ in pred_str.strip().lower().split()]
        candidates=[]
        for i in range(len(self.tokens)):
            j = 0
            while j < len(sub_words) and i+j < len(self.tokens):
                if self.tokens[i+j].lower() == sub_words[j]:
                    j += 1
                else:
                    break
            if j == len(sub_words):
                candidates.append((i, i+len(sub_words)))
        if len(candidates) < 1:
            return -1, -1
        else:
            if trigger_idx is not None:
                return sorted(candidates, key=lambda x: abs(trigger_idx-x[0]))[0]
            else:
                return candidates[0]