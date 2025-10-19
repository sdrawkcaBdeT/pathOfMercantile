import torch
print(f"PyTorch Version: {torch.__version__}")
print(f"Is CUDA available? {torch.cuda.is_available()}")
print(f"CUDA Version PyTorch was built with: {torch.version.cuda}")