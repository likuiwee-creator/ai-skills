# 推送指南：把这个 skill 仓库发到远程

## 什么是 remote？

**remote（远程仓库）= 这个本地 git 仓库的"云端备份地址"。**

你现在这个 `code-selfcheck` 是**本地仓库**（在你电脑的 `.git` 文件夹里）。如果电脑坏了、想换台电脑、想给同事用，都需要把它传到 GitLab / GitHub 这类**远程服务器**上。

而 `remote` 就是那个服务器的地址。本质是给本地仓库**存一个地址**，之后 `git push` 就能把内容传上去。

**类比**：
- 本地仓库 = 你电脑上的一个文件夹
- remote = 这个文件夹的"云端地址"
- `git push` = 上传（把本地内容同步到云端）
- `git pull` = 下载（把云端最新内容拉回本地）

---

## 最快的方式（推荐，两条命令）

### 第 1 步：在 GitLab / GitHub 上建一个空仓库

打开你的 GitLab（或 GitHub），点 **New project / 新建项目**：
- 仓库名填 `code-selfcheck`
- **不要勾选** "Initialize with README"（我们本地已有提交，选了会冲突）
- 可见性按需：私有 / 内部 / 公开

建好后页面会给你一个仓库地址。

### 第 2 步：告诉我地址，或自己执行

```bash
cd /d/workbuddy/2026-09-22-21-55-40/tools/code-selfcheck

# 设置远程地址（把 <你的地址> 换成上一步复制的）
git remote add origin <你的仓库地址>

# 推送
git push -u origin main
```

`git push -u` 里的 `-u` 是把本地 `main` 分支和远程绑定，以后直接 `git push` 就行，不用再带参数。

---

## 两种地址格式，选一个

### 方式 A：SSH 地址（推荐，无需每次输密码）

地址长这样：`git@gitlab.com:你的用户名/code-selfcheck.git`

**需要先配 SSH key**（一次性）：

```bash
# 1. 生成 key（一路回车用默认即可）
ssh-keygen -t ed25519 -C "likewei4651208@vip.qq.com"

# 2. 查看生成的公钥，复制内容
cat ~/.ssh/id_ed25519.pub
```

然后把公钥内容粘贴到：
- GitLab：`Settings → SSH Keys → Add new key`
- GitHub：`Settings → SSH and GPG keys → New SSH key`

配好后 `git push` 就不用密码了。

### 方式 B：HTTPS 地址（简单，每次可能要输账号密码/token）

地址长这样：`https://gitlab.com/你的用户名/code-selfcheck.git`

推送时会要账号密码。**GitLab 现在密码要用 Access Token**，不是登录密码：
`Settings → Access Tokens` 生成一个，勾选 `write_repository` 权限。

---

## 推送后，同事怎么用？

告诉同事这两句：

```bash
git clone <仓库地址>          # 1. 下载
cp -r code-selfcheck ~/.workbuddy/skills/    # 2. 放进 skills 目录（Windows 把 ~ 换成 %USERPROFILE%）
```

之后他在对话里说「提交前自检」，AI 就会自动用这个 skill。

想升级版本时，同事再 `git pull` 一次就行。

---

## 常用命令速查

```bash
git remote -v                              # 查看当前配置的远程地址
git remote set-url origin <新地址>          # 改地址（地址填错了用这个）
git remote remove origin                   # 删掉远程配置
git push                                   # 上传（已绑定后直接用）
git pull                                   # 拉取云端最新
```

---

## 常见问题

**Q：报 `Permission denied (publickey)` / `Authentication failed`**
A：SSH/HTTPS 认证没过。SSH 方式 → 检查公钥有没有加到 GitLab；HTTPS 方式 → 密码要填 Access Token 不是登录密码。

**Q：报 `rejected` / `non-fast-forward`**
A：远程有内容但和本地不一致。确认远程仓库是**空的**，或先 `git pull origin main --rebase` 再推。

**Q：想推到公司内网 GitLab / Gitea**
A：一样，把地址换成你们的就行。SSH key 要加到那套系统的账号里。
