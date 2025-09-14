# import torch, sentencepiece
from transformers import AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained("google/mt5-base", legacy=True, use_fast=False)

def tokenize(line):
    tokens = []
    segments = line.split(" ")
    for segment in segments:
        sws = set(tokenizer.tokenize(segment))
        for sw in sws:
            core_sw = sw.lstrip("\u2581")  # strip subword prifix
            tokens.append(core_sw)
    return tokens

print(tokenize("proposes a method incorporating execution traces into RAG"))
# ['es', 'propos', 'a', '', 'method', 'ting', 'incorpora', 'execution', '', 'es', 'trac', 'into', '', 'RAG']

print(tokenize("ソフトウェアプロダクトの実行行トレースからコールツリーと呼び出された関数のソースコードを抽出してプロンプトに付加する"))
# ['実行', '抽出', 'クト', 'コール', 'ソース', 'する', '加', 'して', '', 'ン', 'ト', 'ツリー', 'ダ', 'コード', '行', 'と', 'プト', 'から', 'レース', 'を', 'の', 'プロ', 'に', 'ソフトウェア', '呼び出', '付', 'された', '関数']
