import subprocess
import argparse
import re


"""
Matches results print from HF benchmarks script:
--------------------------------------------------------------------------------
          Model Name             Batch Size     Seq Length     Time in s   
--------------------------------------------------------------------------------
      bert-base-uncased              4              128            0.062     
--------------------------------------------------------------------------------
"""
RESULTS_REGEX = "(?<=-{80}\n) *\S+ *\S+ *\S+ *\S+ *(?=\n-{80})"

if __name__ == "__main__":
  parser = argparse.ArgumentParser()
  # parser.add_argument("--use_xla", action='store_true')
  parser.add_argument('-m', '--models', nargs='+', default=["bert-base-uncased", "bert-large-uncased", "/opt/ml/code/hopper/test/files/bart-config.json", "roberta-base", "gpt2"])
  parser.add_argument('-s', '--sequence_lengths', nargs='+', type=int, default=[128, 512])
  parser.add_argument('-b', '--batch_sizes', nargs='+', type=int, default=[1, 2, 4, 8, 12, 16, 20, 24, 28, 32, 64, 96, 128])
  parser.add_argument('-d', '--transformers-dir', default="/opt/ml/code/transformers")
  args = parser.parse_args()

  for model in args.models:
    for seq_len in args.sequence_lengths:
      for batch_size in args.batch_sizes:
        print("running {} batch_size={} sequence_length={} with xla=True".format(model, batch_size, seq_len))
        xla_out = subprocess.run("python3 {}/examples/pytorch/benchmarking/run_benchmark.py --models {} --training yes --batch_sizes {} --sequence_lengths {} --inference no --tpu true --memory false --fp16".format(
            args.transformers_dir, model, batch_size, seq_len
          ),
          stderr=subprocess.STDOUT,
          stdout=subprocess.PIPE,
          shell=True)
        xla_out = xla_out.stdout.decode()
        print(xla_out)

        print("running {} batch_size={} sequence_length={} with xla=False".format(model, batch_size, seq_len))
        native_out = subprocess.run("python3 {}/examples/pytorch/benchmarking/run_benchmark.py --models {} --training yes --batch_sizes {} --sequence_lengths {} --inference no --tpu false --memory false --fp16".format(
            args.transformers_dir, model, batch_size, seq_len
          ),
          stderr=subprocess.STDOUT,
          stdout=subprocess.PIPE,
          shell=True)
        native_out = native_out.stdout.decode()
        print(native_out)
        
        xla_latency, native_latency = "N/A", "N/A"
        match = re.search(RESULTS_REGEX, xla_out)
        if match:
          xla_latency = match.group(0).split()[-1]
        match = re.search(RESULTS_REGEX, native_out)
        if match:
          native_latency = match.group(0).split()[-1]
        model_name = model
        if model_name.endswith(".json"):
          model_name = model_name.split("/")[-1]
        if model_name.endswith("-config"):
          model_name = model_name[:-7]
        print("Columns: model, seq_len, batch_size, xla_latency, native_latency")
        print(f"Aggregate: {model_name} {seq_len} {batch_size} {xla_latency} {native_latency}")
