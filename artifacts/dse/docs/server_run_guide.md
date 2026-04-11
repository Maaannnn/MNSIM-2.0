# MNSIM DSE 服务器运行说明

本文档面向你当前这套 `MNSIM-2.0 + DSE + RRAM` 实验。

目标是把这几件事一次讲清楚：

- 怎么把代码和关键文件放到服务器
- 怎么在服务器上创建环境
- 怎么运行 `guidance_v4` / `formal_v3`
- 怎么后台跑、断线不断、查看日志
- 怎么看 CPU / 内存 / GPU 占用
- 怎么判断任务跑完没、结果在哪
- 怎么把结果拉回本地

---

## 1. 建议的目录结构

在服务器上建议统一放到：

```text
~/workspace/MNSIM-2.0
```

这样后续命令都更统一。

---

## 2. 需要上传哪些文件

最少需要这些：

```text
MNSIM-2.0/
  MNSIM/
  dse/
  artifacts/
  SimConfig.ini
  cifar10_vgg8_params.pth
  requirements.txt   # 如果你仓库里有
  pyproject.toml     # 如果你仓库里有
```

如果你已经把虚拟环境 `.venv` 配好了，不建议直接拷贝 `.venv`，因为：

- 本地和服务器的 Python 版本可能不同
- 本地是 macOS，服务器通常是 Linux
- 二进制依赖很容易失效

所以推荐：

- **代码上传**
- **服务器上重新建 `.venv`**

---

## 3. 怎么把文件放上服务器

有 3 种常见方式。

### 方式 A：`rsync`，最推荐

优点：

- 增量同步
- 速度比 `scp` 更好
- 适合反复更新代码

本地执行：

```bash
rsync -avhz --progress \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '.DS_Store' \
  ~/workspace/MNSIM-2.0/ \
  <user>@<server>:~/workspace/MNSIM-2.0/
```

如果只想同步关键文件：

```bash
rsync -avhz --progress \
  ~/workspace/MNSIM-2.0/MNSIM \
  ~/workspace/MNSIM-2.0/dse \
  ~/workspace/MNSIM-2.0/artifacts \
  ~/workspace/MNSIM-2.0/SimConfig.ini \
  ~/workspace/MNSIM-2.0/cifar10_vgg8_params.pth \
  <user>@<server>:~/workspace/MNSIM-2.0/
```

### 方式 B：`scp`

适合一次性复制。

```bash
scp -r ~/workspace/MNSIM-2.0 <user>@<server>:~/workspace/
```

### 方式 C：`git clone`

如果代码已经在远端 Git 仓库里：

```bash
ssh <user>@<server>
mkdir -p ~/workspace
cd ~/workspace
git clone <repo-url> MNSIM-2.0
```

然后再单独上传大文件，例如权重：

```bash
scp ~/workspace/MNSIM-2.0/cifar10_vgg8_params.pth <user>@<server>:~/workspace/MNSIM-2.0/
```

---

## 4. 登录服务器后先做什么

```bash
ssh <user>@<server>
cd ~/workspace/MNSIM-2.0
pwd
ls
```

先确认这些文件在：

```bash
ls SimConfig.ini
ls cifar10_vgg8_params.pth
ls dse/run_dse.py
ls artifacts/dse/scripts
```

---

## 5. 创建 Python 环境

### 5.1 查看 Python 版本

```bash
python3 --version
which python3
```

建议：

- Python 3.10 / 3.11 / 3.12 更稳

### 5.2 创建虚拟环境

```bash
cd ~/workspace/MNSIM-2.0
python3 -m venv .venv
source .venv/bin/activate
python -V
```

### 5.3 安装依赖

如果仓库里有 `requirements.txt`：

```bash
pip install -U pip
pip install -r requirements.txt
```

如果没有，你至少要保证这些装上：

```bash
pip install numpy scipy pandas matplotlib tqdm torch torchvision
```

如果服务器是 NVIDIA GPU，且你需要 CUDA 版 PyTorch，请按服务器 CUDA 版本安装。

例如：

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

注意：

- 这里的 `cu121` 只是例子
- 要先看服务器到底是什么 CUDA 版本

---

## 6. 怎么检查服务器配置

### 6.1 CPU 信息

```bash
lscpu
```

### 6.2 内存信息

```bash
free -h
```

### 6.3 磁盘空间

```bash
df -h
```

### 6.4 GPU 信息

```bash
nvidia-smi
```

你重点看：

- GPU 型号
- 显存总量
- 驱动版本
- CUDA version

如果没有 `nvidia-smi`，说明：

- 可能没有 NVIDIA GPU
- 或你没有驱动环境

---

## 7. 怎么检查 Python 能不能看到 GPU

进入虚拟环境后：

```bash
source .venv/bin/activate
python - <<'PY'
import torch
print("torch:", torch.__version__)
print("cuda available:", torch.cuda.is_available())
print("cuda count:", torch.cuda.device_count())
if torch.cuda.is_available():
    for i in range(torch.cuda.device_count()):
        print(i, torch.cuda.get_device_name(i))
PY
```

如果看到：

- `cuda available: True`

说明可以用：

- `--device cuda:0`

---

## 8. 先做一次最小检查

### 8.1 检查正式搜索空间是否可用

```bash
source .venv/bin/activate
python - <<'PY'
from dse.core import available_space_profiles, apply_space_profile, space_size
print(available_space_profiles())
apply_space_profile("rram_guidance_v4")
print("guidance_v4 size =", space_size())
apply_space_profile("rram_formal_v3")
print("formal_v3 size =", space_size())
PY
```

### 8.2 小规模试跑

先不要直接上大预算，先试运行一轮。

```bash
source .venv/bin/activate
python dse/run_dse.py \
  --algos random \
  --seeds 42 \
  --budget 4 \
  --init-evals 2 \
  --workers 1 \
  --nn vgg8 \
  --weights cifar10_vgg8_params.pth \
  --base-config SimConfig.ini \
  --space-profile rram_formal_v3 \
  --run-accuracy \
  --max-acc-batches 2 \
  --accuracy-target 0.88 \
  --enable-saf \
  --enable-variation \
  --device cuda:0 \
  --output-root artifacts/dse/search_runs/smoke_test
```

如果这条能通，再上正式任务。

---

## 9. 服务器上跑哪些正式任务

你当前建议跑两类：

### 9.1 设计指导版：`rram_guidance_v4`

用途：

- 看更大空间下的设计趋势
- 用来回答“怎么指导设计”

推荐启动命令：

```bash
cd ~/workspace/MNSIM-2.0
source .venv/bin/activate

python dse/run_dse.py \
  --algos random nsga2 mobo \
  --seeds 42 43 44 \
  --budget 48 \
  --init-evals 8 \
  --population 16 \
  --evals-per-gen 4 \
  --workers 1 \
  --nn vgg8 \
  --weights cifar10_vgg8_params.pth \
  --base-config SimConfig.ini \
  --space-profile rram_guidance_v4 \
  --run-accuracy \
  --max-acc-batches 4 \
  --accuracy-target 0.88 \
  --enable-saf \
  --enable-variation \
  --device cuda:0 \
  --output-root artifacts/dse/search_runs/rram_guidance_v4_server \
  --plots
```

### 9.2 正式论文版：`rram_formal_v3`

用途：

- 做最终方法对比
- 输出论文主结果

推荐启动命令：

```bash
cd ~/workspace/MNSIM-2.0
source .venv/bin/activate

python dse/run_dse.py \
  --algos random nsga2 mobo \
  --seeds 42 43 44 \
  --budget 24 \
  --init-evals 6 \
  --population 12 \
  --evals-per-gen 4 \
  --workers 1 \
  --nn vgg8 \
  --weights cifar10_vgg8_params.pth \
  --base-config SimConfig.ini \
  --space-profile rram_formal_v3 \
  --run-accuracy \
  --max-acc-batches 4 \
  --accuracy-target 0.88 \
  --enable-saf \
  --enable-variation \
  --device cuda:0 \
  --output-root artifacts/dse/search_runs/rram_formal_v3_server \
  --plots
```

---

## 10. 为什么服务器上推荐 `workers=1`

如果你在：

- `--run-accuracy`
- `--device cuda:0`

的情况下把 `workers` 开太大，
通常会变成：

- 多个 Python 进程同时抢一张 GPU

结果往往是：

- 显存抖动
- GPU 上下文切换频繁
- 速度反而变慢

所以：

- **单卡服务器**：优先 `workers=1`
- **多卡服务器**：每张卡开一个独立任务，比一个任务里开很多 worker 更好

---

## 11. 怎么后台跑

你有 3 种常见方式。

### 11.1 `nohup`

最简单：

```bash
cd ~/workspace/MNSIM-2.0
source .venv/bin/activate

nohup python dse/run_dse.py \
  --algos random nsga2 mobo \
  --seeds 42 43 44 \
  --budget 24 \
  --init-evals 6 \
  --population 12 \
  --evals-per-gen 4 \
  --workers 1 \
  --nn vgg8 \
  --weights cifar10_vgg8_params.pth \
  --base-config SimConfig.ini \
  --space-profile rram_formal_v3 \
  --run-accuracy \
  --max-acc-batches 4 \
  --accuracy-target 0.88 \
  --enable-saf \
  --enable-variation \
  --device cuda:0 \
  --output-root artifacts/dse/search_runs/rram_formal_v3_server \
  --plots \
  > artifacts/dse/search_runs/rram_formal_v3_server.log 2>&1 &
```

查看日志：

```bash
tail -f artifacts/dse/search_runs/rram_formal_v3_server.log
```

### 11.2 `tmux`

更推荐，适合长期实验。

创建会话：

```bash
tmux new -s mnsim_dse
```

在 `tmux` 里跑命令。

退出但不断开任务：

```bash
Ctrl-b d
```

重新进入：

```bash
tmux attach -t mnsim_dse
```

列出会话：

```bash
tmux ls
```

### 11.3 `screen`

如果服务器没有 `tmux`，可以用：

```bash
screen -S mnsim_dse
```

断开：

```bash
Ctrl-a d
```

恢复：

```bash
screen -r mnsim_dse
```

---

## 12. 多卡服务器怎么跑

假设你有两张卡：

- GPU0 跑 `guidance_v4`
- GPU1 跑 `formal_v3`

### GPU0

```bash
cd ~/workspace/MNSIM-2.0
source .venv/bin/activate

nohup env CUDA_VISIBLE_DEVICES=0 python dse/run_dse.py \
  --algos random nsga2 mobo \
  --seeds 42 43 44 \
  --budget 48 \
  --init-evals 8 \
  --population 16 \
  --evals-per-gen 4 \
  --workers 1 \
  --nn vgg8 \
  --weights cifar10_vgg8_params.pth \
  --base-config SimConfig.ini \
  --space-profile rram_guidance_v4 \
  --run-accuracy \
  --max-acc-batches 4 \
  --accuracy-target 0.88 \
  --enable-saf \
  --enable-variation \
  --device cuda:0 \
  --output-root artifacts/dse/search_runs/rram_guidance_v4_gpu0 \
  --plots \
  > artifacts/dse/search_runs/rram_guidance_v4_gpu0.log 2>&1 &
```

### GPU1

```bash
cd ~/workspace/MNSIM-2.0
source .venv/bin/activate

nohup env CUDA_VISIBLE_DEVICES=1 python dse/run_dse.py \
  --algos random nsga2 mobo \
  --seeds 42 43 44 \
  --budget 24 \
  --init-evals 6 \
  --population 12 \
  --evals-per-gen 4 \
  --workers 1 \
  --nn vgg8 \
  --weights cifar10_vgg8_params.pth \
  --base-config SimConfig.ini \
  --space-profile rram_formal_v3 \
  --run-accuracy \
  --max-acc-batches 4 \
  --accuracy-target 0.88 \
  --enable-saf \
  --enable-variation \
  --device cuda:0 \
  --output-root artifacts/dse/search_runs/rram_formal_v3_gpu1 \
  --plots \
  > artifacts/dse/search_runs/rram_formal_v3_gpu1.log 2>&1 &
```

注意：

- `CUDA_VISIBLE_DEVICES=1` 之后，进程内部看到的那张卡仍然叫 `cuda:0`

---

## 13. 怎么看任务有没有在跑

### 13.1 看 Python 进程

```bash
ps -ef | grep run_dse.py
```

### 13.2 看某个用户的 Python 进程

```bash
ps -u $USER -f | grep python
```

### 13.3 看日志是否在持续更新

```bash
tail -f artifacts/dse/search_runs/rram_formal_v3_server.log
```

如果日志持续出现：

- `lat=... en=... area=... acc=...`

说明任务还在跑。

---

## 14. 怎么看资源占用

### 14.1 看 CPU / 内存

```bash
htop
```

如果没有 `htop`：

```bash
top
```

### 14.2 看 GPU

```bash
nvidia-smi
```

实时刷新：

```bash
watch -n 1 nvidia-smi
```

你重点看：

- GPU Util
- Memory Usage
- 哪个 PID 在占卡

### 14.3 看某个进程资源

先查 PID：

```bash
ps -ef | grep run_dse.py
```

再看：

```bash
top -p <PID>
```

---

## 15. 怎么看服务器硬件配置

### CPU 型号

```bash
lscpu
```

### 内存大小

```bash
free -h
```

### GPU 型号与显存

```bash
nvidia-smi
```

### PyTorch 能识别到的 GPU

```bash
source .venv/bin/activate
python - <<'PY'
import torch
print("cuda available:", torch.cuda.is_available())
print("gpu count:", torch.cuda.device_count())
for i in range(torch.cuda.device_count()):
    print(i, torch.cuda.get_device_name(i))
PY
```

---

## 16. 跑完后结果在哪里

例如你跑：

- `artifacts/dse/search_runs/rram_formal_v3_server`

那么结果会在这里：

```text
artifacts/dse/search_runs/rram_formal_v3_server/
  random_seed42/
  random_seed43/
  random_seed44/
  nsga2_seed42/
  ...
  comparison/
```

重点看：

- 每个 trial 下的 `result.json`
- `comparison/`
- `comparison` 里的图和汇总 CSV

查看目录：

```bash
find artifacts/dse/search_runs/rram_formal_v3_server -maxdepth 2 | sort
```

---

## 17. 如果只想重做 comparison / plot

### 只重做比较

```bash
source .venv/bin/activate
python dse/run_dse.py \
  --compare-only \
  --output-root artifacts/dse/search_runs/rram_formal_v3_server
```

### 重做比较并补图

```bash
source .venv/bin/activate
python dse/run_dse.py \
  --compare-only \
  --plots \
  --output-root artifacts/dse/search_runs/rram_formal_v3_server
```

### 只补图

```bash
source .venv/bin/activate
python dse/run_dse.py \
  --plot-only \
  --output-root artifacts/dse/search_runs/rram_formal_v3_server
```

---

## 18. 怎么把结果拉回本地

最推荐还是 `rsync`。

### 拉整个搜索结果目录

本地执行：

```bash
rsync -avhz --progress \
  <user>@<server>:~/workspace/MNSIM-2.0/artifacts/dse/search_runs/rram_formal_v3_server/ \
  ~/workspace/MNSIM-2.0/artifacts/dse/search_runs/rram_formal_v3_server/
```

### 只拉日志

```bash
scp <user>@<server>:~/workspace/MNSIM-2.0/artifacts/dse/search_runs/rram_formal_v3_server.log .
```

### 只拉 comparison

```bash
rsync -avhz --progress \
  <user>@<server>:~/workspace/MNSIM-2.0/artifacts/dse/search_runs/rram_formal_v3_server/comparison/ \
  ~/workspace/MNSIM-2.0/artifacts/dse/search_runs/rram_formal_v3_server/comparison/
```

---

## 19. 常见问题

### 问题 1：为什么 GPU 很闲但任务还慢

常见原因：

- `run_accuracy` 里数据加载和前处理占了不少时间
- MNSIM 本身很多部分仍是 CPU 逻辑
- 多进程抢一张卡导致反而更慢

建议：

- 单卡先用 `workers=1`
- 先用 `max_acc_batches=4`

### 问题 2：为什么开更多 worker 没更快

因为：

- 每个 worker 都可能拉起完整推理流程
- GPU 只有一张时，worker 太多会相互争抢

### 问题 3：如何先试再正式跑

先把：

- `budget` 改小
- `seeds` 只留一个
- `algos` 先只跑 `random`

例如：

```bash
source .venv/bin/activate
python dse/run_dse.py \
  --algos random \
  --seeds 42 \
  --budget 6 \
  --init-evals 2 \
  --workers 1 \
  --nn vgg8 \
  --weights cifar10_vgg8_params.pth \
  --base-config SimConfig.ini \
  --space-profile rram_formal_v3 \
  --run-accuracy \
  --max-acc-batches 2 \
  --accuracy-target 0.88 \
  --enable-saf \
  --enable-variation \
  --device cuda:0 \
  --output-root artifacts/dse/search_runs/test_quick
```

---

## 20. 推荐你的实际执行顺序

### 本地

1. 用 `rsync` 把代码传上去
2. 服务器上重建 `.venv`
3. 做一次 `smoke_test`

### 服务器

1. 先跑 `rram_guidance_v4` 小预算版
2. 确认能稳定跑完后，再跑完整预算
3. 再跑 `rram_formal_v3`
4. 最后拉回 `comparison/` 和日志

---

## 21. 一条最省事的服务器命令

如果你已经配好环境，直接用这一条启动正式论文版：

```bash
cd ~/workspace/MNSIM-2.0 && \
source .venv/bin/activate && \
nohup python dse/run_dse.py \
  --algos random nsga2 mobo \
  --seeds 42 43 44 \
  --budget 24 \
  --init-evals 6 \
  --population 12 \
  --evals-per-gen 4 \
  --workers 1 \
  --nn vgg8 \
  --weights cifar10_vgg8_params.pth \
  --base-config SimConfig.ini \
  --space-profile rram_formal_v3 \
  --run-accuracy \
  --max-acc-batches 4 \
  --accuracy-target 0.88 \
  --enable-saf \
  --enable-variation \
  --device cuda:0 \
  --output-root artifacts/dse/search_runs/rram_formal_v3_server \
  --plots \
  > artifacts/dse/search_runs/rram_formal_v3_server.log 2>&1 &
```

---

## 22. 相关文件

- 设计指导空间说明：`artifacts/dse/docs/rram_guidance_v4.md`
- 正式论文空间说明：`artifacts/dse/docs/rram_formal_v3.md`
- 设计指导脚本：`artifacts/dse/scripts/run_guidance_v4_search.sh`
- 正式论文脚本：`artifacts/dse/scripts/run_formal_v3_search.sh`

