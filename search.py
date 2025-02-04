import torch
from util import use_cuda
beam_size = 5
MAX_DECODING_STEPS = 12
EPS = 1e-8

# Beam 搜索类
class Beam(object):
  def __init__(self, word2idx, h_t, c_t):
    self.word2idx = word2idx
    # (beam_size, t) 1步以后的tokens
    self.tokens = torch.LongTensor(beam_size, 1).fill_(self.word2idx['<SOS>'])
    # (beam_size, 1) 初始化的分数= -30
    self.scores = torch.FloatTensor(beam_size, 1).fill_(-30)

    self.tokens = use_cuda(self.tokens)
    self.scores = use_cuda(self.scores)

    # 在第一步，所有的beam都是从一个beam开始的，所以给第一个beam初始化得分
    self.scores[0][0] = 0
    self.h_t = h_t.unsqueeze(0).repeat(beam_size, 1)
    self.c_t = c_t.unsqueeze(0).repeat(beam_size, 1)
    self.et_sum = None
    self.dec_out = None
    self.done = False

  # 得到当前状态
  def get_current_state(self):
    tokens = self.tokens[:,-1].clone()
    for i in range(len(tokens)):
      if tokens[i].item() >= len(self.word2idx):
        tokens[i] = self.word2idx['<UNK>']
    return tokens

  # 更新分数
  def advance(self, prob_dist, h_t, c_t, et_sum, dec_out):
    '''
    :param prob_dist: (beam, n_extended_vocab)
    :param h_t: (beam, hidden_dim)
    :param c_t: (beam, hidden_dim)
    :param et_sum:   (beam, n_seq)
    :param dec_out:  (beam, t, n_hid)
    '''
    n_extended_vocab = prob_dist.size(1)
    log_probs = torch.log(prob_dist + EPS)
    # 维护每个beam的总得分
    scores = log_probs + self.scores
    # 取出beam_size个最大的得分   
    scores_t = scores.view(-1,1)
    # 按照得分从大到小排序                           
    best_scores, best_scores_id = torch.topk(input=scores_t, k=beam_size, dim=0)
    self.scores = best_scores
    beams_order = best_scores_id.squeeze(1) // n_extended_vocab
    best_words = best_scores_id % n_extended_vocab
    self.h_t = h_t[beams_order]
    self.c_t = c_t[beams_order]
    if et_sum is not None:
      self.et_sum = et_sum[beams_order]
    if dec_out is not None:
      self.dec_out = dec_out[beams_order]
    self.tokens = self.tokens[beams_order]
    self.tokens = torch.cat([self.tokens, best_words], dim=1)

    # 如果当前beam中最后一个token是EOS，则结束
    if best_words[0][0] == self.word2idx['<EOS>']:
      self.done = True

  def get_best(self):
    # 因为beam是按照得分从大到小排序的，所以第一个beam是最好的beam
    best_token = self.tokens[0].cpu().numpy().tolist()
    try:
      end_idx = best_token.index(self.word2idx['<EOS>'])
    except ValueError:
      end_idx = len(best_token)
    best_token = best_token[1:end_idx]
    return best_token

  def get_all(self):
    all_tokens = []
    for i in range(len(self.tokens)):
      all_tokens.append(self.tokens[i].cpu().numpy())
    return all_tokens

def beam_search(h_t, c_t, enc_out, dec_tar, enc_padding_mask, enc_ext_vocab, 
                max_zeros_ext_vocab, model, word2idx, hidden_dim, evaluation='val'):

  batch_size = len(h_t)
  beam_idx = torch.LongTensor(list(range(batch_size)))
  # 给每个batch中的每个example创建一个beam对象
  beams = [Beam(word2idx, h_t[i], c_t[i]) for i in range(batch_size)]
  # 索引活跃的beam，即没有生成[STOP]
  n_rem = batch_size
  et_sum = None
  dec_out = None

  # 设置限制为beam search的最大长度
  max_dec_steps = dec_tar.shape[1] if evaluation == 'val' else MAX_DECODING_STEPS
  for t in range(max_dec_steps):
    inputs = torch.stack(
        [beam.get_current_state() for beam in beams if beam.done == False]
    ).contiguous().view(-1)

    dec_h = torch.stack(
        [beam.h_t for beam in beams if beam.done == False]
    ).contiguous().view(-1, hidden_dim)
    dec_c = torch.stack(
        [beam.c_t for beam in beams if beam.done == False]
    ).contiguous().view(-1, hidden_dim)

    if et_sum is not None:
      # rem*beam_size, n_seq
      et_sum = torch.stack(
          [beam.et_sum for beam in beams if beam.done == False]
      ).contiguous().view(-1, enc_out.size(1))

    if dec_out is not None:
      # rem*beam_size, t-1, n_hid
      dec_out = torch.stack(
          [beam.dec_out for beam in beams if beam.done == False]
      ).contiguous().view(-1, t, hidden_dim)


    # 将beam_size和batch_size相乘，得到一个大的batch_size
    enc_out_beam = enc_out[beam_idx].view(n_rem, -1).repeat(1, beam_size).view(-1, enc_out.size(1), enc_out.size(2))
    enc_pad_mask_beam = enc_padding_mask[beam_idx].repeat(1, beam_size).view(-1, enc_padding_mask.size(1))

    max_zeros_ext_vocab_beam = None
    if max_zeros_ext_vocab is not None:
      max_zeros_ext_vocab_beam = max_zeros_ext_vocab[beam_idx].repeat(1, beam_size).view(-1, max_zeros_ext_vocab.size(1))
    enc_ext_vocab_beam = enc_ext_vocab[beam_idx].repeat(1, beam_size).view(-1, enc_ext_vocab.size(1))

    inputs = model.embedding_matrix(inputs)
    p_y, dec_h, dec_c, et_sum, dec_out = model.decoder(t, dec_h, dec_c, enc_out_beam, dec_out,
                                                 et_sum, enc_pad_mask_beam, enc_ext_vocab_beam, 
                                                 max_zeros_ext_vocab_beam, inputs)

    # 接下来的步骤将分离（剩余）批量大小维度和beam宽度维度
    p_y = p_y.view(n_rem, beam_size, -1)
    dec_h = dec_h.view(n_rem, beam_size, -1)
    dec_c = dec_c.view(n_rem, beam_size, -1)

    if et_sum is not None:
      # rem, beam_size, n_seq
      et_sum = et_sum.view(n_rem, beam_size, -1)

    if dec_out is not None:
      # rem, beam_size, t, hidden_dim
      dec_out = dec_out.view(n_rem, beam_size, -1, hidden_dim)   

    # 对于每个活跃的beam，执行beam search
    # 在beam search之后，活跃的beam的索引
    active = []         

    for i in range(n_rem):
      # 这里beam平均batch
      b = beam_idx[i].item()
      beam = beams[b]
      if beam.done:
        continue

      et_sum_i = prev_s_i = None
      if et_sum is not None:
        et_sum_i = et_sum[i]
      if dec_out is not None:
        dec_out_i = dec_out[i]
      beam.advance(p_y[i], dec_h[i], dec_c[i], et_sum_i, dec_out_i)
      if beam.done == False:
        active.append(b)

    if len(active) == 0:
      break

    beam_idx = torch.LongTensor(active)
    n_rem = len(beam_idx)

  predicted_words = []
  for beam in beams:
    predicted_words.append(beam.get_best())

  return predicted_words

def search(h_t, c_t, enc_out, enc_inp_len, dec_tar, enc_padding_mask, enc_ext_vocab, 
           max_zeros_ext_vocab, model, word2idx, greedy=True, evaluation='val'):

  et_sum = None
  dec_out = None
  inputs =  torch.zeros_like(enc_inp_len).fill_(word2idx['<SOS>'])
  outputs = []
  max_dec_steps = dec_tar.shape[1] if evaluation == 'val' else MAX_DECODING_STEPS
  for t in range(max_dec_steps):
    inputs = model.embedding_matrix(inputs)
    p_y, h_t, c_t, et_sum, dec_out = model.decoder(t, h_t, c_t, enc_out, dec_out, et_sum, 
                                             enc_padding_mask, enc_ext_vocab, 
                                             max_zeros_ext_vocab, inputs)
    if greedy:
      _, inputs = torch.max(p_y, dim=1)
    else:
      inputs = torch.multinomial(p_y, 1).squeeze(1)
    outputs.append(inputs)
    is_oov = (inputs >= len(word2idx)).type(torch.LongTensor)
    is_oov = use_cuda(is_oov)
    inputs = is_oov * word2idx['<UNK>'] + (1 - is_oov) * inputs

  outputs = torch.stack(outputs, dim=1).cpu().numpy()

  return outputs
