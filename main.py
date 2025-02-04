from util import get_load_path, read_data, split_data, get_vocab, get_word2idx_idx2word, prepare_input_data, prepare_test_data, get_embedding_matrix
from train import Summarization
import sys

# 预处理数据
def preprocess_data(abstracts_path, titles_path):
  print('Reading data ...')
  total_df = read_data(abstracts_path, titles_path)

  train_df, val_df = split_data(total_df)
  print('Preparing vocabulary ...')
  vocab = get_vocab(train_df, size=80000)
  word2idx, idx2word = get_word2idx_idx2word(vocab)
  return train_df, val_df, word2idx, idx2word

# 主要入口
def main():
  # choice 是第一个参数，可以是 train，val, test
  # load_path 是第二个参数，只有在 choice 为 val 或者 test 时才必须，train的时候可以有
  # test_file 是第三个参数，只有在 choice 为 test 时才必须
  # 如果是 train，则会训练模型，并保存模型
  # 如果是 val，则会读取模型，并预测 
  # 如果是 test，则会读取模型，并预测
  choice = sys.argv[1]
  choice = 'train'

  load_path = None
  try:
    load_path = sys.argv[2]
  except:
    if choice in ['val', 'test'] and load_path is None:
      print('Please specify some path to load model weights from.')
      return
  load_path = get_load_path('model')

  test_file = None
  try:
    test_file = sys.argv[3]
    if choice in ['train', 'val']:
      print('This command is not supported.')
      return
  except:
    if choice == 'test':
      print('Please provide path to test csv file containing abstracts only.')
      return

  print('Choice: ', choice)
  if load_path is not None:
    print('Load path: ', load_path)
  if test_file is not None:
    print('Test file: ', test_file)

  train_df, val_df, word2idx, idx2word = preprocess_data('./data/abstracts.pkl', './data/titles.pkl')
  print('Preparing embedding matrix ...')
  emb_matrix = get_embedding_matrix(word2idx, idx2word, './data/glove_vectors.txt', 'glove')
  summarization = Summarization(emb_matrix, emb_dim=200, hidden_dim=128, word2idx=word2idx, idx2word=idx2word)
  print('Preparing Input data ...')
  if choice == 'train':
    train_data = prepare_input_data(train_df, word2idx)
    summarization.train(train_data,train_rl=True, use_prev=load_path)
  elif choice == 'val':
    eval_data = prepare_input_data(val_df, word2idx)
    summarization.eval(eval_data, val_df, load_path=load_path, evaluation='val', print_samples=True)
  elif choice == 'test':
    test_df, eval_data = prepare_test_data(test_file, word2idx)
    summarization.eval(eval_data, test_df, load_path=load_path, evaluation='test', print_samples=True)
  else:
    print('This command is not supported.')
    return

if __name__ == '__main__':
  main()







