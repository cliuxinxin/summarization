# 预处理文件
# 文件在data目录下
# 原文在 data/train.txt.src
# 缩写在 data/train.txt.tgt.tagged

import pickle

# 读取原文
with open('./data/train.txt.src', 'r') as f:
    train_src = f.readlines()

# 读取缩写
with open('./data/train.txt.tgt.tagged', 'r') as f:
    train_tgt = f.readlines()

# 原文取 -- 号后的部分,如果没有则取全部
train_src = [line.split(' -- ')[1] if ' -- ' in line else line for line in train_src]

# 将原文保存为abstracts.pkl
with open('./data/abstracts.pkl', 'wb') as f:
    pickle.dump(train_src, f)

# 缩写的部分去掉标签<t>和</t>
train_tgt = [line.replace('<t>', '').replace('</t>', '') for line in train_tgt]

# 将缩写保存为titles.pkl
with open('./data/titles.pkl', 'wb') as f:
    pickle.dump(train_tgt, f)




