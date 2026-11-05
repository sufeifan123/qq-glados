# GLaDOS 自动签到

[![GLaDOS Checkin](https://github.com/sufeifan123/qq-glados/actions/workflows/checkin.yml/badge.svg)](https://github.com/sufeifan123/qq-glados/actions/workflows/checkin.yml)

使用 Python 和 GitHub Actions 为 GLaDOS 账号签到，查询积分、剩余天数，并可通过微信公众平台测试号发送通知。无需自备服务器。

**本仓库当前使用 cron-job.org，每天北京时间 09:00 触发一次。** 定时设置在 cron-job.org 后台，不在仓库代码中；Fork 项目不会复制外部定时任务，需要自行配置。

> 当前工作流仅配置了 `workflow_dispatch`，支持手动运行和 API 触发，没有内置 `schedule`。请先完成一次手动验证，再设置定时任务。接口、积分规则和登录会话有效期由 GLaDOS 决定，不承诺固定签到奖励或永久有效。

## 目录

- [功能与运行方式](#功能与运行方式)
- [新手快速部署](#新手快速部署)
- [配置项一览](#配置项一览)
- [微信测试号通知](#微信测试号通知)
- [每天北京时间九点自动触发](#每天北京时间九点自动触发)
- [多账号管理](#多账号管理)
- [旧配置迁移](#旧配置迁移)
- [运行结果与常见问题](#运行结果与常见问题)
- [本地运行与测试](#本地运行与测试)
- [项目文件与参考资料](#项目文件与参考资料)

## 功能与运行方式

| 功能 | 当前实现 |
| --- | --- |
| 单账号与多账号 | 每个账号单独保存 Cookie，使用固定标识和可选备注 |
| 失败重试 | 单个账号首次签到异常后等待 60 秒，再尝试一次 |
| 账号顺序 | 按固定标识排序，正常处理的签到失败不会阻止后续账号 |
| 状态查询 | 查询当前积分和剩余天数；未获取到的数据显示 `?` |
| 域名尝试 | 每次请求依次尝试 cloud、rocks、network，签到 token 随当前域名设置 |
| 微信通知 | 微信测试号模板消息，每条最多两个账号，更多账号分批发送 |
| 执行结果 | 全部账号签到正常时退出码为 0；无账号、账号配置错误或存在签到失败时为 1 |

域名切换发生在 HTTP 非 200 或请求、JSON 解析异常时；HTTP 200 中的业务失败会直接返回给签到重试逻辑，不保证继续尝试其他域名。

当前没有实现 PushPlus、每日积分增量计算、兑换操作或兑换差额提示。积分、剩余天数会截去小数部分后展示。

## 新手快速部署

### 第一步：Fork 并启用 Actions

1. 打开 [本仓库](https://github.com/sufeifan123/qq-glados)，点击右上角 **Fork**，创建自己的副本。
2. 进入自己的仓库，打开 **Actions** 标签页。
3. 如果出现启用提示，按页面提示启用工作流。
4. 后续所有 Secrets、Variables 和运行操作，都在自己的仓库完成。

如果你就是本仓库维护者，可以直接配置当前仓库，无需再次 Fork。

几个常用概念：

| 名称 | 含义 |
| --- | --- |
| Fork | 在自己的 GitHub 账号下创建仓库副本 |
| Cookie | 网站的登录凭证，程序用它代表对应账号请求接口 |
| Secrets | GitHub 存放 Cookie、密钥等敏感配置的位置 |
| Variables | 存放备注、User-Agent 等普通配置的位置 |
| Run workflow | 手动启动一次工作流，用于验证配置 |
| cron-job.org | 按时间表调用 GitHub API，启动签到工作流的外部服务 |

### 第二步：获取 Cookie 和 User-Agent

建议使用电脑上的 Chrome 或 Edge，从实际登录请求中复制，避免手动拼错 Cookie。

1. 打开 [GLaDOS](https://glados.cloud) 并登录自己的账号。
2. 按 **F12** 打开开发者工具，选择 **Network（网络）**，确保网络录制已开启。
3. 刷新页面，或进入控制台签到页面并进行一次正常操作。
4. 找到发往 GLaDOS 的已登录接口请求，例如路径包含 `/api/user/status` 或 `/api/user/checkin` 的请求。
5. 打开该请求的 **Headers（标头）→ Request Headers（请求标头）**。
6. 复制 `Cookie` 的完整值，并从同一请求中复制 `User-Agent` 的值，分别暂存。

当前脚本识别的新版签名会话字段为：

```text
gld:sess=你的会话值; gld:sess.sig=你的签名值
```

上面只是格式示例，不能直接使用。请保留实际请求中的完整值；Cookie 中存在其他字段时可以一起保留。

- Cookie 应是请求头字符串，不是 Cookie-Editor 导出的对象数组。
- 两个会话字段要来自同一次登录，不能混用不同账号或不同会话。
- 如果手动组合，用分号分隔字段，建议写成上面的格式。
- 如果只有旧版 `koa:sess` 字段，脚本可以解析，但服务端可能不再接受；遇到“没有权限”时重新登录并获取新版 Cookie。
- Cookie 和 User-Agent 应来自同一个登录浏览器；重新获取 Cookie 时同步检查 User-Agent。
- 不要把 Cookie、请求截图中的凭证或完整请求导出文件提交到仓库、Issue 或聊天中。

### 第三步：配置一个账号

当前工作流已经映射 `U156`、`U290` 两组账号。**它们只是配置标识，不要求与你的 GLaDOS 用户编号一致。** 新手可以直接复用，只填一组也能运行。

进入自己的仓库 **Settings → Secrets and variables → Actions**。

在 **Secrets** 标签下，点击 **New repository secret**，添加：

| Name | Secret |
| --- | --- |
| `GLADOS_COOKIE_U156` | 第二步复制的一个账号完整 Cookie |

在 **Variables** 标签下，点击 **New repository variable**，添加：

| Name | Value |
| --- | --- |
| `GLADOS_USER_AGENT` | 第二步同一请求中的 User-Agent |
| `GLADOS_NAME_U156` | 可选，例如“主账号”；不填时工作流默认“账号156” |

只有一个账号时，不用添加 `GLADOS_COOKIE_U290`。两个账号都使用同一浏览器 User-Agent 时，可以共用全局值；不同浏览器的配置方法见[多账号管理](#多账号管理)。

> Secret/Variable 名称必须与工作流映射一致。仅新建 `GLADOS_COOKIE`、`GLADOS_COOKIE_MAIN` 或其他未映射名称，不会自动传给当前工作流。

### 第四步：手动验证

1. 打开自己的仓库 **Actions → GLaDOS Checkin**。
2. 点击 **Run workflow**，选择 `main` 分支，再点击运行按钮。
3. 打开新出现的运行记录，展开 **Run GLaDOS Checkin** 步骤查看日志。
4. 确认读取到了预期账号，并出现“全部账号处理正常”。

示例日志如下，数值仅用于说明：

```text
✅ 主账号 [U156] | 用户: u***@example.com | 积分: 169 | 剩余: 266 天 | 结果: Checkin Repeats! Please Try Tomorrow
📊 本次结果：正常 1/1
```

“已经签到”也按正常结果处理，不代表每次运行都会新增积分。未配置微信时，出现“微信测试号参数未配置完整，跳过微信通知”是预期行为，不影响签到。

确认手动运行正常后，再按下面的教程配置微信和定时触发。

## 配置项一览

### 当前工作流已经映射的配置

| 名称 | 存放位置 | 是否需要 | 说明 |
| --- | --- | --- | --- |
| `GLADOS_COOKIE_U156` | Secrets | 两组 Cookie 至少填一组 | 一个账号的完整 Cookie |
| `GLADOS_COOKIE_U290` | Secrets | 可选第二账号 | 另一个账号的完整 Cookie |
| `GLADOS_NAME_U156` | Variables | 可选 | 默认“账号156” |
| `GLADOS_NAME_U290` | Variables | 可选 | 默认“账号290” |
| `GLADOS_USER_AGENT` | Variables | 建议配置 | 全局 User-Agent，来自登录浏览器 |
| `WECHAT_APPID` | Secrets | 微信通知四项须全部填写 | 微信测试号 AppID |
| `WECHAT_APPSECRET` | Secrets | 同上 | 同一测试号的 AppSecret |
| `WECHAT_TEMPLATE_ID` | Secrets | 同上 | 该测试号下的通知模板 ID |
| `WECHAT_OPENID` | Secrets | 同上 | 接收人在该测试号下的 OpenID |

User-Agent 未配置时，脚本使用内置 Windows Chrome 120 字符串；这不保证与当前登录会话匹配，建议填入实际值。

### 脚本支持、但当前工作流没有映射的配置

| 名称 | 用途 | 使用前需要做什么 |
| --- | --- | --- |
| `GLADOS_COOKIE` | 旧版单账号或多账号配置 | 在签到步骤的 `env` 中添加 Secret 映射 |
| `GLADOS_COOKIE_<标识>` | 其他独立账号 | 添加对应的 Secret 和工作流映射 |
| `GLADOS_NAME_<标识>` | 其他账号的备注 | 添加对应 Variable 和工作流映射 |
| `GLADOS_USER_AGENT_<标识>` | 账号专属 User-Agent | 添加对应 Variable 和工作流映射 |

优先级为：**账号专属 User-Agent → 全局 User-Agent → 脚本默认值**。

## 微信测试号通知

微信通知是可选功能。当前程序使用微信公众平台测试号，不使用 PushPlus。

### 1. 获取测试号信息和接收人 OpenID

1. 在电脑上打开 [微信公众平台接口测试号](https://mp.weixin.qq.com/debug/cgi-bin/sandbox?t=sandbox/login)，按页面提示使用微信登录。
2. 在测试号信息区域找到 `appID` 和 `appsecret`。
3. 找到测试号二维码，用接收通知的微信扫码关注该测试号。
4. 在测试号用户列表中，找到接收人的标识，复制其 OpenID。

这里的 OpenID 是接收人在**这个测试号下**的标识，不是微信昵称、微信号或手机号。当前脚本每批消息发送给一个 `WECHAT_OPENID`，不要填多个值或列表。

### 2. 新建通知模板

在测试号后台找到模板消息相关区域，新增测试模板。标题可填“GLaDOS 签到”，内容复制为：

```text
签到结果：{{keyword1.DATA}}
{{keyword2.DATA}}
{{keyword3.DATA}}
```

保存后复制模板 ID。模板字段必须与上面一致，不要把 `keyword2` 写成“执行时间”，它对应第一个账号详情。

### 3. 添加四个 Secrets

回到仓库 **Settings → Secrets and variables → Actions → Secrets**，添加：

- `WECHAT_APPID`
- `WECHAT_APPSECRET`
- `WECHAT_TEMPLATE_ID`
- `WECHAT_OPENID`

四项应来自同一测试号的配置。全部填好后，手动运行一次，检查日志中的“微信测试号通知发送成功”。

### 4. 通知格式

两个账号的示例：

```text
签到结果：正常 2/2
主账号：169分 / 266天
备用账号：191分 / 278天
```

- 每个账号独占一个字段；只有一个账号时，另一个字段显示“无”。
- 失败账号添加“失败”标记，例如 `主账号：失败 / ?分 / ?天`；已查询到的数据仍会保留。
- 三个及以上账号每两个一批，例如 `正常 3/3（1/2）` 和 `正常 3/3（2/2）`。
- 某一批发送失败后，仍会尝试发送剩余批次。
- 通知主要显示备注、积分和天数；固定标识及签到结果消息见 Actions 日志。
- 建议使用简短且不含隐私的备注；微信客户端的卡片显示效果可能不同。

**注意：微信发送失败不会单独让当前工作流变红。** Actions 成功只表示脚本的签到判断正常，通知是否送达还要查看微信发送日志。

## 每天北京时间九点自动触发

本仓库维护者使用 cron-job.org，每天 **09:00（Asia/Shanghai，北京时间）** 调用 GitHub API。新部署用户需要在自己的 cron-job.org 账号中单独创建任务。

### 1. 创建 GitHub 访问令牌

1. 打开 GitHub **Settings → Developer settings → Personal access tokens → Fine-grained tokens**，也可以进入 [令牌设置页](https://github.com/settings/personal-access-tokens)。
2. 新建细粒度令牌，设置便于辨认的名称，例如 `glados-cron`，并选择合适的有效期。
3. **Resource owner** 选择目标仓库所属账号。
4. **Repository access** 选择 **Only select repositories**，只选择你用于签到的仓库。
5. 在 **Repository permissions** 中，为 **Actions** 设置 **Read and write**，其余保持所需的最小权限。
6. 生成并复制令牌，妥善保存。如果目标账号要求审批，先确认令牌已获批准。

这个令牌用于让 cron-job.org 触发你的工作流，不是 GLaDOS Cookie，也不是微信 AppSecret。到期或撤销后，需要在 cron-job.org 中更新。

权限依据见 [GitHub 工作流触发 API 文档](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event)。旧教程中仅勾选 classic token 的 `workflow` 权限，不应作为本教程的配置方法。

### 2. 创建 cron-job.org 任务

登录 [cron-job.org](https://cron-job.org)，新建 Cronjob，按以下内容配置。界面字段名称以服务当前页面为准。

| 项目 | 设置 |
| --- | --- |
| Title | `GLaDOS 每日签到` |
| URL | 下方与你的仓库对应的 dispatch 地址 |
| 执行时间 | 每天 09:00 |
| Time zone | `Asia/Shanghai` |
| Request method | `POST` |
| Request body | 下方 JSON，使用 Raw Body |
| 任务状态 | 启用 |

本仓库地址：

```text
https://api.github.com/repos/sufeifan123/qq-glados/actions/workflows/checkin.yml/dispatches
```

如果你使用 Fork，必须替换为自己的所有者和仓库名：

```text
https://api.github.com/repos/OWNER/REPO/actions/workflows/checkin.yml/dispatches
```

例如 Fork 后改了仓库名，URL 中的 `REPO` 也要跟着修改，不要继续请求本仓库。

添加以下请求头：

| Key | Value |
| --- | --- |
| `Accept` | `application/vnd.github+json` |
| `Authorization` | `Bearer YOUR_GITHUB_TOKEN` |
| `Content-Type` | `application/json` |
| `X-GitHub-Api-Version` | `2022-11-28` |

把 `YOUR_GITHUB_TOKEN` 换成你刚生成的令牌。`Bearer` 后有一个空格，令牌本身不要加入空格、换行或引号。令牌只填入受保护的任务配置，不要公开分享请求头截图。

请求体：

```json
{"ref":"main"}
```

`ref` 指定运行分支；按本教程使用 `main`。保存前检查时间为 **每天 09:00**、时区为 **Asia/Shanghai**，只需一个每日任务。

### 3. 测试与验收

1. 在 cron-job.org 中手动测试一次。
2. 检查 HTTP 响应；上述配置通常返回 `204 No Content`。API 版本或响应选项不同也可能返回带运行信息的成功响应。
3. 打开自己仓库的 **Actions**，确认出现新的 **GLaDOS Checkin** 运行记录。
4. 等待完成，检查签到日志以及可选的微信通知。
5. 次日检查 cron-job.org 执行历史与 Actions 记录，确认定时触发正常。

**HTTP 成功仅说明触发请求被接受，不代表签到完成。** 真正的签到结果以 Actions 日志为准；排队和网络情况也可能让实际执行晚于 09:00。

### 4. 外部触发故障排查

| 现象 | 优先检查 |
| --- | --- |
| 401 | 令牌是否过期、撤销或复制错误；Authorization 是否有正确前缀 |
| 403 | 令牌是否具有目标仓库的 Actions 写权限；是否存在审批或组织策略限制 |
| 404 | OWNER、REPO、工作流文件名是否正确；令牌是否获准访问目标仓库 |
| 422 | JSON 是否有效；是否填写存在的 `ref`；工作流是否支持 `workflow_dispatch` |
| 触发成功但签到失败 | 打开对应 Actions 运行记录，排查 Cookie 和签到结果 |
| 没有按时触发 | 检查任务是否启用、时区与每日时间、外部执行历史及令牌有效期 |

当前没有 GitHub 内置定时配置，也没有 `keep-alive.yml`。仅 Fork、提交文件或手动运行，不会自动创建每日任务。未来若自行增加 `schedule`，请避免与外部触发重复运行，并参考 [GitHub 触发事件文档](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)。

## 多账号管理

### 使用预留的第二账号

添加 Secret `GLADOS_COOKIE_U290`，填第二个账号的完整 Cookie；可选添加 Variable `GLADOS_NAME_U290`。无需修改 Python 或工作流。

每个 Secret 只放一个账号。不要把两个 Cookie 放在同一个独立账号 Secret 中，也不要在其中使用多账号 JSON 数组或 `#` 分隔串。

### 为不同账号设置专属 User-Agent

脚本支持账号专属 User-Agent，但当前工作流还没有映射。需要使用时，在自己仓库的 [.github/workflows/checkin.yml](.github/workflows/checkin.yml) 中，找到 **Run GLaDOS Checkin → env**，按现有缩进加入：

```yaml
          GLADOS_USER_AGENT_U156: ${{ vars.GLADOS_USER_AGENT_U156 }}
          GLADOS_USER_AGENT_U290: ${{ vars.GLADOS_USER_AGENT_U290 }}
```

然后在 GitHub **Variables** 中添加对应值。只为需要的账号加一行也可以；为空时继续使用全局 User-Agent。

这是可选的使用教程，不代表当前仓库已经包含这些映射。

### 新增第三个或更多账号

例如使用标识 `FAMILY`：

1. 新建 Secret `GLADOS_COOKIE_FAMILY`，填写一个账号的完整 Cookie。
2. 可选新建 Variables：`GLADOS_NAME_FAMILY`、`GLADOS_USER_AGENT_FAMILY`。
3. 在自己仓库工作流的签到步骤 `env` 下添加：

```yaml
          GLADOS_COOKIE_FAMILY: ${{ secrets.GLADOS_COOKIE_FAMILY }}
          GLADOS_NAME_FAMILY: ${{ vars.GLADOS_NAME_FAMILY || '家人账号' }}
          GLADOS_USER_AGENT_FAMILY: ${{ vars.GLADOS_USER_AGENT_FAMILY }}
```

4. 保存工作流，再手动运行验证。

固定标识必须以大写字母开头，只包含大写字母、数字和下划线；三行的后缀必须一致。不需要另外维护 Python 账号列表。

### 更新、删除与停止

- **更新 Cookie：**只修改该账号对应的 Secret；必要时同步更新 User-Agent。
- **更新备注：**修改对应 Variable。公开 Actions 日志会显示备注，请使用不含隐私的昵称。
- **停用单个账号：**删除对应 Cookie Secret，映射得到空值后，该账号不会参与签到；也可移除对应工作流映射。
- **清理账号配置：**移除该账号的 Cookie、备注及专属 User-Agent 映射，并删除不再使用的 Secrets/Variables。
- **暂停全部自动签到：**停用 cron-job.org 任务；也可在 GitHub Actions 中禁用该工作流。已经启动的任务需要另行取消。

账号按标识排序，因此 `U156` 在 `U290` 前处理，和 YAML 中的排列顺序无关。新增账号可能改变显示顺序，但不会改变其他账号的固定标识。

## 旧配置迁移

### 从 GLADOS_COOKIE 迁移

旧版单个 `GLADOS_COOKIE` 可以在 Python 中表示单账号、JSON 数组或用 `#` 分隔的多个账号，但**当前工作流没有将它传入程序**。

推荐迁移到独立账号：

1. 从旧配置中取出每个账号的完整 Cookie。
2. 分别存入 `GLADOS_COOKIE_U156` 和 `GLADOS_COOKIE_U290`，更多账号按上文增加映射。
3. 配置备注及 User-Agent，再手动验证。
4. 确认正常后再清理不需要的旧 Secret。

如果确实需要使用旧格式，在自己的工作流签到步骤 `env` 下补上：

```yaml
          GLADOS_COOKIE: ${{ secrets.GLADOS_COOKIE }}
```

此时脚本的规则为：

- 存在任意非空 `GLADOS_COOKIE_<标识>` 环境变量：仅使用独立账号，忽略旧 `GLADOS_COOKIE`。
- 所有独立账号为空：读取已映射的旧 `GLADOS_COOKIE`，按位置显示为“旧账号1 [LEGACY_1]”等。
- 删除最后一个独立账号后，只有旧变量**已映射且非空**才会回退；否则无账号可运行。
- 独立账号配置非法时会报错退出，不会自动回退到旧账号。

### 从 MAIN、BACKUP 或旧微信模板迁移

- 如果以前按旧 README 新建了 `GLADOS_COOKIE_MAIN`、`GLADOS_COOKIE_BACKUP`，可把 Cookie 迁入当前预留的 U156/U290，或自行补齐 MAIN/BACKUP 的工作流映射。
- 仍然有效的 Cookie 不需要为了改标识而重新获取；失效或缺少新版会话字段时再重新登录。
- 当前不读取 `PUSHPLUS_TOKEN`，通知请改为四个微信测试号 Secrets。
- 旧微信模板如果把 `keyword2` 当作执行时间，需要改用本文模板；新建模板后同时更新 `WECHAT_TEMPLATE_ID`。

## 运行结果与常见问题

### Actions 绿色或红色分别代表什么？

| 结果 | 当前含义 |
| --- | --- |
| 绿色 | 脚本判断所有参与账号签到正常，包括重复签到 |
| 红色 | 可能是账号签到失败、无账号、配置错误，或安装依赖、网络、执行超时等运行问题 |
| 微信没收到但 Actions 绿色 | 通知缺配置或发送失败不会单独改变脚本退出码 |
| 积分或天数为 `?` | 该项查询未成功，不能仅据此判定签到失败 |

脚本把响应消息包含 `checkin! got`、`checkin repeats`、`today's observation logged`，或响应 `code == 0` 视为正常。这个判断依赖接口返回约定，必要时请结合日志和官网核实。

### 显示“未配置 GLADOS_COOKIE”，但我已经配置了独立账号？

如果独立账号 Cookie 全部为空，程序会尝试旧变量，因此可能出现这条提示。检查 Secret 名称、是否在正确仓库创建，以及工作流 `env` 是否映射了相同名称。当前默认只映射 U156/U290。

### 显示“没有权限”或反复失败？

先在浏览器确认账号能够正常登录、手动签到，再重新获取同一次登录的完整 Cookie 和 User-Agent。重点检查 `gld:sess`、`gld:sess.sig` 是否齐全，是否误贴为 JSON 导出、其他账号的值或已失效会话。

Cookie 没有可由本项目保证的固定有效期。过期、退出登录或服务端会话策略变化后，需要更新对应 Secret。

### 显示“Checkin Repeats! Please Try Tomorrow”？

表示接口报告已经签到，脚本按正常处理。重复运行不保证重复获得奖励。

### 显示“please checkin via https://glados.cloud”？

核对运行的是否为当前脚本、分支是否正确，并检查登录域名与 Cookie。当前脚本按请求域名设置签到 token，不需要把其他教程中的旧 token 硬编码进去。接口规则仍可能变化，保留不含凭证的错误信息用于排查。

### 没有收到微信通知？

1. 确认四项微信 Secrets 完整，且来自同一测试号。
2. 确认接收人已经关注该测试号，OpenID 属于该测试号。
3. 确认模板 ID 正确，字段使用本文的 `keyword1`、`keyword2`、`keyword3`。
4. 查看“获取微信 access_token 失败”或“微信测试号通知失败”后的错误码和消息，再按微信官方说明排查。
5. 如果没有账号、配置解析失败或任务提前中断，程序可能尚未走到通知步骤。

### 为什么运行较慢或超过十分钟？

账号按顺序处理。每个首次失败账号会等待 60 秒，每次 HTTP 请求超时为 10 秒，还可能依次尝试多个域名。当前工作流整个任务的超时上限为 10 分钟；账号较多且连续失败时可能被中止，无法保证发送最终通知。

### 日志时间与北京时间不同？

脚本使用运行环境的本地时间生成日志，没有单独设置北京时间。cron-job.org 的 `Asia/Shanghai` 控制定时触发时间，不能据日志时间直接认定定时配置错误。

### 如何安全反馈问题？

到 [Issues](https://github.com/sufeifan123/qq-glados/issues) 描述操作步骤、运行时间、是否手动/API 触发及脱敏后的错误信息。不要附上 Cookie、令牌、AppSecret、完整请求头或含这些信息的截图；分享日志前先检查异常详情。

## 本地运行与测试

一般用户使用 GitHub Actions 即可。需要本地调试时，建议使用与工作流一致的 **Python 3.11**。

在项目根目录安装依赖：

```bash
python -m pip install -r requirements.txt
```

作用：使用当前 Python 对应的 pip 安装依赖；`-r requirements.txt` 表示从该文件读取依赖清单。此操作会修改当前 Python 环境中的软件包，建议在虚拟环境中执行。

通过你自己的安全方式将账号 Cookie 等配置注入环境变量，再运行：

```bash
python checkin.py
```

作用：运行签到脚本。**此操作会向 GLaDOS 发送真实请求；微信配置完整时还会发送通知。** 不要把真实密钥写入脚本或命令历史。

本地环境不受 GitHub 工作流映射限制，可以直接设置脚本支持的环境变量。Windows 上若命令名不同，请使用本机 Python 的实际命令。

离线测试：

```bash
python -m unittest discover -s tests -v
```

作用：发现并运行测试；`-s tests` 指定测试目录，`-v` 显示各用例结果。现有测试拦截 HTTP，不会执行真实签到或微信通知。

现有用例覆盖账号读取、旧格式兼容、User-Agent 优先级、请求中的账号隔离、失败账号继续处理及微信分批消息等行为。离线测试通过不代表线上 Cookie 或外部接口一定可用。

## 项目文件与参考资料

| 路径 | 说明 |
| --- | --- |
| [checkin.py](checkin.py) | 账号读取、签到、状态查询和微信通知 |
| [.github/workflows/checkin.yml](.github/workflows/checkin.yml) | Actions 运行环境和变量映射；目前仅手动/API 触发 |
| [requirements.txt](requirements.txt) | Python 依赖，目前为 `requests>=2.28.0` |
| [tests/test_accounts.py](tests/test_accounts.py) | 离线单元测试 |
| [images/](images/) | 仓库保留的历史教程截图，可能与当前界面或配置不同 |
| [README.md](README.md) | 当前使用说明 |

参考资料：

- [GitHub：手动运行工作流](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)
- [GitHub：触发 workflow_dispatch 的 REST API](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event)
- [GitHub：工作流触发事件](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
- [微信公众平台接口测试号](https://mp.weixin.qq.com/debug/cgi-bin/sandbox?t=sandbox/login)
- [微信：模板消息接口](https://developers.weixin.qq.com/doc/offiaccount/Message_Management/Template_Message_Interface.html)
- [cron-job.org](https://cron-job.org)

原 README 提及的上游项目：[lankerr/2026-glados-checkin](https://github.com/lankerr/2026-glados-checkin)。感谢相关开源工作。

### 许可证说明

旧 README 标注为 MIT，但当前仓库未附独立的 `LICENSE` 文件。具体授权及上游版权信息需进一步核实、补齐，请勿把本说明视为新增的许可证授权。
